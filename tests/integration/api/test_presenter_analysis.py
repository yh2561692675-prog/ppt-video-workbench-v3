from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.audio.models import RecognizedSegment, RecognizedWord
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import PageRecord, ProjectManifest
from workbench.main import create_app
from workbench.media.presenter_audio import AnalysisAudio
from workbench.media.presenter_probe import PresenterMediaInfo


class FixedBackend:
    def transcribe(self, _: Path, **__: object):
        return (
            [
                RecognizedSegment(
                    start=0,
                    end=1,
                    text="专业概览",
                    words=[RecognizedWord("专业概览", 0, 1, 0.99)],
                ),
                RecognizedSegment(
                    start=1.5,
                    end=2.5,
                    text="就业方向",
                    words=[RecognizedWord("就业方向", 1.5, 2.5, 0.99)],
                ),
            ],
            "zh",
        )


def _probe(path: Path) -> PresenterMediaInfo:
    return PresenterMediaInfo(
        path=str(path),
        sha256="a" * 64,
        duration_ms=3_000,
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        width=1920,
        height=1080,
        fps=30,
        sample_rate=48_000,
        channels=2,
    )


def _extract(_: Path, output: Path) -> AnalysisAudio:
    return AnalysisAudio(
        source_path="presenter.mp4",
        wav_path=str(output),
        duration_ms=3_000,
        sample_rate=16_000,
        channels=1,
        sha256="b" * 64,
        cache_key="analysis-v1",
    )


def test_presenter_analysis_api_builds_and_persists_full_timeline(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        presenter_probe=_probe,
        transcription_backend=FixedBackend(),
        presenter_audio_extractor=_extract,
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "presenter-analysis"}).json()["data"]
        uploaded = client.post(
            f"/api/projects/{project['id']}/presenter-source",
            files={"file": ("presenter.mp4", b"video", "video/mp4")},
        ).json()["data"]
        manifest = ProjectManifest.model_validate(uploaded)
        page_ids = [uuid4(), uuid4()]
        payload = manifest.model_dump(mode="python")
        payload["pages"] = [
            PageRecord(id=page_ids[0], order=1, title="专业概览"),
            PageRecord(id=page_ids[1], order=2, title="就业方向"),
        ]
        payload["page_extractions"] = [
            PageExtraction(
                id=uuid4(),
                order=1,
                text="专业介绍",
                title="专业概览",
                extraction_method="pptx",
                source_ref="deck.pptx",
                preview_path=Path("02_页面预览/page-0001.png"),
            ),
            PageExtraction(
                id=uuid4(),
                order=2,
                text="就业与发展",
                title="就业方向",
                extraction_method="pptx",
                source_ref="deck.pptx",
                preview_path=Path("02_页面预览/page-0002.png"),
            ),
        ]
        app.state.project_service.save(ProjectManifest.model_validate(payload))

        response = client.post(f"/api/projects/{project['id']}/presenter-analysis")

        assert response.status_code == 200
        result = response.json()["data"]
        timeline = result["project"]["presenter_timeline"]
        assert [item["page_id"] for item in timeline["anchors"]] == [str(item) for item in page_ids]
        assert timeline["segments"]
        assert len(timeline["timeline_hash"]) == 64
        root = tmp_path / str(project["project_dir"]) / "03_文字识别" / "presenter"
        assert {path.name for path in root.iterdir()} == {
            "transcript.json",
            "matches.json",
            "timeline.json",
        }
        subtitle_root = tmp_path / str(project["project_dir"]) / "06_字幕"
        assert {path.name for path in subtitle_root.iterdir()} == {
            "字幕.srt",
            "字幕时间轴.json",
        }
        assert result["project"]["subtitle_artifact"]["srt_sha256"]
        preview = client.get(f"/api/projects/{project['id']}/video/preview")
        assert preview.status_code == 200
        preview_data = preview.json()["data"]
        assert preview_data["allowed"] is True
        assert [item["audio_path"] for item in preview_data["props"]["pages"]] == [
            result["project"]["presenter_source"]["relative_path"],
            result["project"]["presenter_source"]["relative_path"],
        ]
        assert [item["start_ms"] for item in preview_data["props"]["pages"]] == [
            item["start_ms"] for item in timeline["anchors"]
        ]
        reloaded = client.get(f"/api/projects/{project['id']}").json()["data"]
        assert reloaded["presenter_timeline"]["timeline_hash"] == timeline["timeline_hash"]
