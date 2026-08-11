from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .hashing import sha256_file
from .models import RenderGraphV2

# Existing localized diagnostic messages are intentionally kept verbatim;
# their source encoding can make individual lines appear longer to Ruff.
# ruff: noqa: E501


class GraphPreflightIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    action: str
    severity: Literal["error", "warning"] = "error"
    blocking: bool = True


class GraphPreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    issues: list[GraphPreflightIssue] = Field(default_factory=list)
    graph_hash: str


class GraphPreflight:
    def check(
        self,
        graph: RenderGraphV2,
        project_root: Path,
        *,
        expected_delivery_at: datetime | None = None,
        strict_assets: bool = True,
        verify_hash: bool = True,
    ) -> GraphPreflightReport:
        root = project_root.resolve()
        issues: list[GraphPreflightIssue] = []
        if verify_hash:
            payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            from .hashing import sha256_json

            if sha256_json(payload) != graph.graph_hash:
                issues.append(
                    GraphPreflightIssue(
                        code="GRAPH_HASH_MISMATCH",
                        message="RenderGraph hash 与内容不一致",
                        action="重新编译并保存不可变 RenderGraph snapshot",
                    )
                )
        for asset in graph.assets:
            if asset.project_id is not None and asset.project_id != graph.project_id:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_PROJECT_SCOPE",
                        message=f"绱犳潗涓嶅睘浜庡綋鍓嶉」鐩細{asset.source_ref}",
                        action="灏嗙礌鏉愭敞鍐屽埌褰撳墠椤圭洰鍚庡啀缂栬瘹",
                    )
                )
            if (
                asset.license_snapshot is not None
                and asset.license_snapshot.project_ids
                and graph.project_id not in asset.license_snapshot.project_ids
            ):
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_LICENSE_SCOPE",
                        message=f"绱犳潗鎺堟潈鏈 覆盖当前项目：{asset.source_ref}",
                        action="补充项目授权范围或替换素材",
                    )
                )
            # Authorization is independent of file presence.  Report both
            # failures when a revoked asset is also missing so the operator
            # gets the complete remediation set in one preflight response.
            expiry = asset.license_expires_at
            if asset.license_status in {"expired", "blocked"}:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_LICENSE_BLOCKED",
                        message=f"素材授权不可用于导出：{asset.source_ref}",
                        action="更新授权记录或替换素材",
                    )
                )
            elif expiry is not None and expiry <= (expected_delivery_at or datetime.now(UTC)):
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_LICENSE_EXPIRED",
                        message=f"素材授权将在交付前失效：{asset.source_ref}",
                        action="更新授权有效期或替换素材",
                    )
                )
            elif strict_assets and asset.license_status == "unknown":
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_LICENSE_UNKNOWN",
                        message=f"素材缺少可验证授权信息：{asset.source_ref}",
                        action="补充授权记录后再导出",
                    )
                )
            if asset.media_probe_status == "failed":
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_MEDIA_PROBE_FAILED",
                        message=f"无法读取素材媒体元数据：{asset.source_ref}",
                        action="修复媒体文件或 FFprobe 运行时后重新编译 Graph",
                    )
                )
            elif strict_assets and asset.media_probe_status == "unavailable":
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_MEDIA_PROBE_UNAVAILABLE",
                        message=f"素材缺少可用的媒体探测结果：{asset.source_ref}",
                        action="安装或配置 FFprobe 后重新编译 Graph",
                    )
                )
            if asset.media_probe is not None:
                observed = asset.media_probe
                mismatches: list[str] = []
                for field in ("duration_us", "width", "height", "fps_num", "fps_den"):
                    expected = getattr(asset, field)
                    actual = getattr(observed, field)
                    if expected is not None and actual is not None and expected != actual:
                        mismatches.append(field)
                if mismatches:
                    issues.append(
                        GraphPreflightIssue(
                            code="ASSET_MEDIA_METADATA_MISMATCH",
                            message=(
                                "素材媒体元数据已变化（"
                                f"{', '.join(mismatches)}）：{asset.source_ref}"
                            ),
                            action="重新探测素材并生成新的 AssetRecord revision",
                        )
                    )
            relative_path = (
                asset.resolved_path or asset.object_relative_path or asset.proxy_relative_path
            )
            if not relative_path:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_MISSING",
                        message=f"素材未解析：{asset.source_ref}",
                        action="重新导入素材或修复素材引用",
                    )
                )
                continue
            path = (root / relative_path).resolve()
            if path == root or root not in path.parents:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_PATH_ESCAPE",
                        message=f"素材路径超出项目目录：{asset.source_ref}",
                        action="将素材复制到项目素材目录",
                    )
                )
                continue
            if not path.is_file() or not asset.exists:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_MISSING",
                        message=f"素材文件不存在：{asset.source_ref}",
                        action="恢复文件后重新执行预检",
                    )
                )
                continue
            if asset.size_bytes is not None and path.stat().st_size != asset.size_bytes:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_SIZE_MISMATCH",
                        message=f"素材文件大小已变化：{asset.source_ref}",
                        action="重新解析素材 revision 并重新编译 Graph",
                    )
                )
            if asset.content_hash and sha256_file(path) != asset.content_hash:
                issues.append(
                    GraphPreflightIssue(
                        code="ASSET_HASH_MISMATCH",
                        message=f"素材内容已变化：{asset.source_ref}",
                        action="重新解析素材 revision 并重新编译 Graph",
                    )
                )
        for node in graph.nodes:
            if node.end_us > graph.duration_us:
                issues.append(
                    GraphPreflightIssue(
                        code="NODE_OUT_OF_BOUNDS",
                        message=f"节点超出项目时长：{node.id}",
                        action="修正时间线范围或延长项目时长",
                    )
                )
        for edge in graph.transitions:
            if edge.end_us > graph.duration_us:
                issues.append(
                    GraphPreflightIssue(
                        code="TRANSITION_OUT_OF_BOUNDS",
                        message=f"转场超出项目时长：{edge.id}",
                        action="修正转场边界",
                    )
                )
        for clip in graph.audio.clips:
            if clip.timeline_end_us > graph.duration_us:
                issues.append(
                    GraphPreflightIssue(
                        code="AUDIO_OUT_OF_BOUNDS",
                        message=f"音频片段超出项目时长：{clip.id}",
                        action="修正 J/L Cut 或音频片段边界",
                    )
                )
            if (
                clip.source_duration_us is not None
                and clip.source_in_us + clip.timeline_end_us - clip.timeline_start_us
                > clip.source_duration_us
            ):
                issues.append(
                    GraphPreflightIssue(
                        code="AUDIO_SOURCE_OUT_OF_BOUNDS",
                        message=f"音频源范围越界：{clip.id}",
                        action="修正源入点或缩短片段",
                    )
                )
        for cue in graph.subtitles.cues:
            if cue.end_us > graph.duration_us or any(
                word.end_us > cue.end_us
                or word.start_us < cue.start_us
                or word.end_us > graph.duration_us
                for word in cue.words
            ):
                issues.append(
                    GraphPreflightIssue(
                        code="SUBTITLE_OUT_OF_BOUNDS",
                        message=f"字幕或逐词时间越界：{cue.id}",
                        action="修正字幕 cue/word 时间",
                    )
                )
        return GraphPreflightReport(
            allowed=not any(issue.blocking for issue in issues),
            issues=issues,
            graph_hash=graph.graph_hash,
        )
