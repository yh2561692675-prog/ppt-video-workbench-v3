from __future__ import annotations

import argparse
import base64
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from peripheral_contracts import BusinessResultManifest, ErrorCategory, JobEnvelope

from workbench.business_modules.p04_extract.models import (
    DocumentExtractionParameters,
    DocumentExtractionPayload,
    ExtractedDocument,
    PreviewArtifact,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    BusinessModuleError,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AuditEvent, PageRecord, ProjectManifest
from workbench.ocr.paddle_adapter import OcrUnavailableError
from workbench.parsers.docx_parser import DocumentParseError, parse_docx
from workbench.parsers.image_parser import ImageParseError, parse_images
from workbench.parsers.pdf_parser import EncryptedPdfError, OcrPolicy, PdfParseError, parse_pdf
from workbench.parsers.pptx_parser import PresentationParseError, parse_pptx


class ExtractionRejected(ValueError):
    """The source cannot be extracted under the selected policy."""


def extract_document(
    source: Path, preview_dir: Path, ocr_policy: str = "auto"
) -> dict[str, object]:
    suffix = source.suffix.lower()
    preview_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".docx":
        outline = parse_docx(source)
        pages: list[PageExtraction] = []
        outline_payload: object = outline.model_dump(mode="json")
    elif suffix == ".pptx":
        pages = parse_pptx(source)
        outline_payload = {"source_name": source.name, "blocks": []}
    elif suffix == ".pdf":
        pages = parse_pdf(source, OcrPolicy(ocr_policy), preview_dir=preview_dir)
        outline_payload = {"source_name": source.name, "blocks": []}
    elif suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        pages = parse_images(
            [source],
            [uuid5(NAMESPACE_URL, f"image:{source.name}")],
            OcrPolicy(ocr_policy),
            preview_dir=preview_dir,
        )
        outline_payload = {"source_name": source.name, "blocks": []}
    else:
        raise ExtractionRejected(f"unsupported extraction type: {source.suffix}")
    return {
        "source_name": source.name,
        "outline": outline_payload,
        "pages": [page.model_dump(mode="json") for page in pages],
        "page_count": len(pages),
        "cache_key": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        parameters = DocumentExtractionParameters.model_validate(business_parameters(received))
        sources = _extraction_inputs(received, attempt_root, parameters)
        if not sources:
            raise ExtractionRejected("at least one extraction source is required")
        source_root = attempt_root / "sources"
        source_root.mkdir(parents=True, exist_ok=True)
        documents: list[ExtractedDocument] = []
        preview_artifacts: list[PreviewArtifact] = []
        staged_artifacts: list[StagedArtifact] = []
        for index, (name, content) in enumerate(sources):
            source = source_root / f"{index:04d}-{Path(name).name}"
            source.write_bytes(content)
            try:
                raw = extract_document(
                    source,
                    attempt_root / "previews",
                    parameters.ocr_policy,
                )
            except EncryptedPdfError as error:
                raise BusinessModuleError(
                    str(error),
                    category=ErrorCategory.INPUT,
                    code="PDF_ENCRYPTED",
                    retryable=False,
                ) from error
            except OcrUnavailableError as error:
                raise BusinessModuleError(
                    str(error),
                    category=ErrorCategory.ENVIRONMENT,
                    code="OCR_UNAVAILABLE",
                    retryable=False,
                ) from error
            except (
                DocumentParseError,
                PresentationParseError,
                PdfParseError,
                ImageParseError,
            ) as error:
                raise BusinessModuleError(
                    str(error),
                    category=ErrorCategory.INPUT,
                    code="DOCUMENT_PARSE_FAILED",
                    retryable=False,
                ) from error
            raw_pages = raw.get("pages", [])
            if not isinstance(raw_pages, list):
                raise ExtractionRejected("extracted pages payload is invalid")
            normalized_pages: list[PageExtraction] = []
            for page_index, item in enumerate(raw_pages, start=1):
                page = PageExtraction.model_validate(item)
                if page.preview_path is not None:
                    preview_path = page.preview_path.resolve()
                    if not preview_path.is_relative_to(attempt_root.resolve()):
                        raise ExtractionRejected("preview artifact escaped attempt root")
                    logical_name = f"preview-{index + 1:04d}-{page_index:04d}"
                    relative_path = (Path("02_页面预览") / preview_path.name).as_posix()
                    size = preview_path.stat().st_size
                    digest = hashlib.sha256(preview_path.read_bytes()).hexdigest()
                    preview_artifacts.append(
                        PreviewArtifact(
                            logical_name=logical_name,
                            relative_path=relative_path,
                            size_bytes=size,
                            sha256=digest,
                        )
                    )
                    staged_artifacts.append(StagedArtifact(logical_name, "png", preview_path))
                    page = page.model_copy(update={"preview_path": Path(relative_path)})
                normalized_pages.append(page)
            raw["pages"] = [item.model_dump(mode="json") for item in normalized_pages]
            raw["source_name"] = name
            outline = raw.get("outline")
            if isinstance(outline, dict):
                outline["source_name"] = name
            documents.append(ExtractedDocument.model_validate(raw))
        operation: Literal["extract", "ocr"] = (
            "ocr" if received.job_type == "document.ocr" else "extract"
        )
        payload = DocumentExtractionPayload(
            operation=operation,
            documents=tuple(documents),
            previews=tuple(preview_artifacts),
            page_count=sum(item.page_count for item in documents),
        )
        output = attempt_root / "extraction.json"
        output.write_text(
            payload.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        fingerprint = business_input_fingerprint(received)
        business = BusinessResultManifest(
            schema_version="1.0",
            module_id="P04",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=project_revision(received),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "document_extraction").encode()).hexdigest(),
            result_type="document_extraction",
            payload=payload.model_dump(mode="json"),
        )
        return BusinessExecution(
            business,
            (StagedArtifact("extraction", "json", output), *staged_artifacts),
        )

    execution = execute_business_handler(job, args.result.parent, args.result, "P04", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())


def project_document_extraction(result: BusinessResultManifest, project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    payload = DocumentExtractionPayload.model_validate(result.payload)
    extracted = [page for document in payload.documents for page in document.pages]
    by_id = {item.id: item for item in manifest.page_extractions}
    by_id.update({item.id: item for item in extracted})
    pages_by_id = {item.id: item for item in manifest.pages}
    for extraction in extracted:
        current = pages_by_id.get(extraction.id)
        if current is None:
            pages_by_id[extraction.id] = PageRecord(
                id=extraction.id, order=extraction.order, title=extraction.title
            )
        elif current.title is None and extraction.title:
            pages_by_id[extraction.id] = current.model_copy(update={"title": extraction.title})
    now = datetime.now(UTC)
    updated = manifest.model_copy(
        update={
            "pages": sorted(pages_by_id.values(), key=lambda item: item.order),
            "page_extractions": sorted(by_id.values(), key=lambda item: item.order),
            "outline_artifact_path": "03_文本识别/大纲结构.json",
            "material_cache_key": str(result.cache_key),
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="document_extraction_updated",
                    occurred_at=now,
                    details={"page_count": len(extracted)},
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest_path)


def _extraction_inputs(
    job: JobEnvelope,
    attempt_root: Path,
    parameters: DocumentExtractionParameters,
) -> list[tuple[str, bytes]]:
    inputs: list[tuple[str, bytes]] = []
    if job.inputs:
        names = parameters.input_names or tuple(Path(item.path).name for item in job.inputs)
        if len(names) != len(job.inputs):
            raise ExtractionRejected("input_names must match input artifacts")
        for name, reference in zip(names, job.inputs, strict=True):
            source = (attempt_root / reference.path).resolve()
            if not source.is_relative_to(attempt_root.resolve()) or not source.is_file():
                raise ExtractionRejected("extraction input escaped attempt root")
            content = source.read_bytes()
            if len(content) != reference.size_bytes:
                raise ExtractionRejected("extraction input size changed after staging")
            if hashlib.sha256(content).hexdigest() != reference.sha256:
                raise ExtractionRejected("extraction input hash changed after staging")
            inputs.append((name, content))
    for item in parameters.files:
        try:
            content = base64.b64decode(item.content_base64, validate=True)
        except ValueError as error:
            raise ExtractionRejected("extraction source is not valid base64") from error
        inputs.append((item.name, content))
    return inputs
