from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from workbench.audio.models import Transcript, TranscriptSegment, TranscriptWord
from workbench.services.project_service import ProjectService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject a deterministic transcript for a known acceptance recording"
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-id", type=UUID, required=True)
    args = parser.parse_args()

    projects = ProjectService(args.workspace)
    try:
        project = projects.get(args.project_id)
        if project.audio_import is None:
            raise RuntimeError("acceptance_audio_missing")
        pages = sorted(project.pages, key=lambda item: item.order)
        if not pages:
            raise RuntimeError("acceptance_pages_missing")
        page_duration = project.audio_import.duration_ms // len(pages)
        words: list[TranscriptWord] = []
        segments: list[TranscriptSegment] = []
        for index, page in enumerate(pages):
            if page.narration is None or not page.narration.text.strip():
                raise RuntimeError(f"acceptance_narration_missing:{page.order}")
            start_ms = index * page_duration + 400
            end_ms = min((index + 1) * page_duration - 400, project.audio_import.duration_ms)
            word = TranscriptWord(
                text=page.narration.text,
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=1,
            )
            words.append(word)
            segments.append(
                TranscriptSegment(
                    text=page.narration.text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    words=[word],
                )
            )
        projects.save(
            project.model_copy(
                update={
                    "transcript": Transcript(
                        segments=segments,
                        words=words,
                        detected_language="zh",
                        model="acceptance-known-audio",
                        device="cpu",
                        created_at=datetime.now(UTC),
                    )
                }
            )
        )
    finally:
        projects.close()
    print(f"ACCEPTANCE_TRANSCRIPT=PASS project_id={args.project_id} pages={len(pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
