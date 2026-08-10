from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image
from workbench.domain.source_file import SourceKind
from workbench.main import create_app
from workbench.services.import_service import ImportRejected, ImportService
from workbench.services.project_service import ProjectService


def image_bytes(format_name: str = "PNG", *, size: tuple[int, int] = (32, 24)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, "navy").save(stream, format=format_name)
    return stream.getvalue()


def outline_bytes() -> bytes:
    stream = BytesIO()
    document = Document()
    document.add_heading("大纲", level=1)
    document.save(stream)
    return stream.getvalue()


def test_import_copies_source_fingerprints_and_never_overwrites(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("材料测试")
    service = ImportService(projects)

    first = service.import_bytes(project.id, "课件.png", image_bytes())
    second = service.import_bytes(project.id, "课件.png", image_bytes(size=(40, 30)))

    assert first.kind is SourceKind.IMAGE
    assert first.safe_name == "课件.png"
    assert second.safe_name == "课件_2.png"
    assert first.sha256 != second.sha256
    assert (tmp_path / project.project_dir / first.copied_path).read_bytes() == image_bytes()


def test_import_rejects_spoofed_damaged_oversized_and_traversal_names(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("安全测试")
    service = ImportService(projects, max_file_bytes=1000, max_image_pixels=500)

    with pytest.raises(ImportRejected, match="文件类型"):
        service.import_bytes(project.id, "伪装.png", b"not-an-image")
    with pytest.raises(ImportRejected, match="损坏"):
        service.import_bytes(project.id, "损坏.png", b"\x89PNG\r\n\x1a\ninvalid")
    with pytest.raises(ImportRejected, match="像素"):
        service.import_bytes(project.id, "超大.png", image_bytes(size=(30, 20)))

    imported = service.import_bytes(project.id, "../../安全.png", image_bytes(size=(20, 20)))
    assert imported.safe_name == "安全.png"
    assert ".." not in imported.copied_path


def test_image_batch_natural_order_can_be_overridden_and_audited(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("图片批次")
    service = ImportService(projects)
    sources = service.import_batch(
        project.id,
        [
            ("第10页.png", image_bytes()),
            ("第2页.png", image_bytes()),
            ("第1页.jpg", image_bytes("JPEG")),
        ],
    )

    assert [item.original_name for item in sources] == ["第1页.jpg", "第2页.png", "第10页.png"]
    changed = service.reorder_images(project.id, [sources[2].id, sources[0].id, sources[1].id])
    assert [item.id for item in changed] == [sources[2].id, sources[0].id, sources[1].id]
    manifest = projects.get(project.id)
    assert manifest.audit_log[-1].action == "image_order_changed"


def test_api_imports_mixed_image_batch_and_eicar_is_never_executed(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "API导入"}).json()["data"]
        response = client.post(
            f"/api/projects/{project['id']}/sources",
            files=[
                ("files", ("2.png", image_bytes(), "image/png")),
                ("files", ("1.jpg", image_bytes("JPEG"), "image/jpeg")),
                ("files", ("eicar.txt", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", "text/plain")),
            ],
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "material_import_rejected"


def test_images_are_naturally_ordered_even_when_word_is_in_same_batch(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("混合批次")

    ImportService(projects).import_batch(
        project.id,
        [
            ("大纲.docx", outline_bytes()),
            ("第10页.png", image_bytes()),
            ("第2页.png", image_bytes()),
        ],
    )

    images = sorted(
        projects.get(project.id).source_files,
        key=lambda source: source.image_order or 0,
    )[1:]
    assert [source.original_name for source in images] == ["第2页.png", "第10页.png"]
