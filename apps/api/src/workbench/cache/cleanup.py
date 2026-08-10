from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.issues import CleanupPlanRecord
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.services.project_service import ProjectService


class CleanupError(RuntimeError):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class CleanupPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    relative_paths: list[str] = Field(default_factory=list)
    bytes_reclaimable: int = Field(ge=0)
    affected_nodes: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    confirmation_token: str
    created_at: datetime


class CleanupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    deleted_paths: list[str] = Field(default_factory=list)
    bytes_reclaimed: int = Field(ge=0)
    affected_nodes: list[str] = Field(default_factory=list)


_CACHE_PREFIXES = (
    Path("02_页面预览"),
    Path("03_文字识别"),
    Path("05_音频/缓存"),
    Path("05_音频/中间"),
    Path("05_音频/合成"),
    Path("05_音频/HeyGen"),
    Path("06_字幕"),
    Path("07_视频工程/缓存"),
    Path("07_视频工程/segments"),
    Path("07_视频工程/临时"),
    Path("09_日志/预检"),
    Path("09_日志/检查点"),
)


def estimate_cleanup(
    project: ProjectManifest,
    project_root: Path,
    selection: Iterable[str] | None = None,
) -> CleanupPlan:
    root = project_root.resolve()
    if selection is None:
        candidates = _discover_candidates(project, root)
    else:
        candidates = [_selected_path(root, item) for item in selection]
    candidates = sorted({path for path in candidates}, key=lambda path: path.as_posix())
    relative_paths = [path.relative_to(root).as_posix() for path in candidates]
    protected = _protected_paths(project, root)
    token = secrets.token_urlsafe(24)
    return CleanupPlan(
        id=uuid4(),
        project_id=project.id,
        relative_paths=relative_paths,
        bytes_reclaimable=sum(path.stat().st_size for path in candidates),
        affected_nodes=_affected_nodes(relative_paths),
        protected_paths=sorted(protected),
        confirmation_token=token,
        created_at=datetime.now(UTC),
    )


class CleanupService:
    def __init__(
        self,
        projects: ProjectService,
        *,
        move: Callable[[Path, Path], None] = os.replace,
    ) -> None:
        self.projects = projects
        self.move = move

    def estimate(self, project_id: UUID, selection: Iterable[str] | None = None) -> CleanupPlan:
        project = self.projects.get(project_id)
        root = self._root(project)
        plan = estimate_cleanup(project, root, selection)
        record = CleanupPlanRecord(
            id=plan.id,
            project_id=project.id,
            relative_paths=plan.relative_paths,
            bytes_reclaimable=plan.bytes_reclaimable,
            affected_nodes=plan.affected_nodes,
            confirmation_token_digest=_digest(plan.confirmation_token),
            created_at=plan.created_at,
        )
        updated = project.model_copy(
            update={
                "cleanup_plans": [*project.cleanup_plans, record],
                "audit_log": [
                    *project.audit_log,
                    AuditEvent(
                        action="cleanup_estimated",
                        occurred_at=datetime.now(UTC),
                        details={
                            "plan_id": str(plan.id),
                            "bytes_reclaimable": plan.bytes_reclaimable,
                            "path_count": len(plan.relative_paths),
                        },
                    ),
                ],
            }
        )
        self.projects.save(updated)
        return plan

    def execute(
        self,
        project_id: UUID,
        plan_id: UUID,
        confirmation_token: str,
    ) -> CleanupResult:
        project = self.projects.get(project_id)
        record = next((item for item in project.cleanup_plans if item.id == plan_id), None)
        if record is None or record.status != "estimated":
            raise CleanupError(
                "cleanup_plan_stale",
                "清理计划不存在或已执行",
                "重新估算缓存后再执行清理",
            )
        if record.confirmation_token_digest != _digest(confirmation_token):
            raise CleanupError(
                "cleanup_confirmation_required",
                "清理需要对当前估算计划进行二次确认",
                "使用当前计划返回的确认令牌重试",
            )
        root = self._root(project)
        transaction = root / "09_日志" / "清理事务" / str(plan_id)
        moved: list[tuple[Path, Path]] = []
        deleted_paths: list[str] = []
        try:
            for relative_path in record.relative_paths:
                source = _selected_path(root, relative_path)
                target = transaction / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                self.move(source, target)
                moved.append((source, target))
                deleted_paths.append(relative_path)
            updated_record = record.model_copy(update={"status": "executed"})
            updated_project = project.model_copy(
                update={
                    "cleanup_plans": [
                        updated_record if item.id == plan_id else item
                        for item in project.cleanup_plans
                    ],
                    "audit_log": [
                        *project.audit_log,
                        AuditEvent(
                            action="cleanup_executed",
                            occurred_at=datetime.now(UTC),
                            details={
                                "plan_id": str(plan_id),
                                "deleted_paths": deleted_paths,
                                "bytes_reclaimed": record.bytes_reclaimable,
                            },
                        ),
                    ],
                }
            )
            self.projects.save(updated_project)
        except Exception as error:
            self._rollback(moved)
            raise CleanupError(
                "cleanup_interrupted",
                "清理被中断，项目清单与缓存已回滚",
                "检查磁盘权限后重新估算并执行清理",
            ) from error
        finally:
            shutil.rmtree(transaction, ignore_errors=True)
        return CleanupResult(
            plan_id=plan_id,
            deleted_paths=deleted_paths,
            bytes_reclaimed=record.bytes_reclaimable,
            affected_nodes=record.affected_nodes,
        )

    def _root(self, project: ProjectManifest) -> Path:
        return (self.projects.workspace_root / project.project_dir).resolve()

    def _rollback(self, moved: list[tuple[Path, Path]]) -> None:
        for source, temporary in reversed(moved):
            if temporary.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, source)


def _discover_candidates(project: ProjectManifest, root: Path) -> list[Path]:
    current_checkpoints = _current_checkpoints(root)
    current_report = project.preflight_report.snapshot_path if project.preflight_report else None
    candidates: list[Path] = []
    for prefix in _CACHE_PREFIXES:
        directory = root / prefix
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in current_checkpoints or relative == current_report:
                continue
            if _safe_resolved(root, path) is not None:
                candidates.append(path.resolve())
    return candidates


def _selected_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise CleanupError(
            "cleanup_path_invalid",
            "清理路径不在项目白名单内",
            "只选择项目缓存目录中的可重建文件",
        )
    candidate = _safe_resolved(root, root / relative)
    if candidate is None or not candidate.is_file() or not _is_cache_path(relative):
        raise CleanupError(
            "cleanup_path_protected",
            f"路径受保护或不可清理：{relative_path}",
            "不要选择源文件、确认内容、最终包或项目元数据",
        )
    return candidate


def _is_cache_path(relative: Path) -> bool:
    return any(relative == prefix or prefix in relative.parents for prefix in _CACHE_PREFIXES)


def _safe_resolved(root: Path, path: Path) -> Path | None:
    resolved = path.resolve()
    if root not in resolved.parents:
        return None
    return resolved


def _protected_paths(project: ProjectManifest, root: Path) -> set[str]:
    protected = {"project.json", "project.json.bak", "workspace.db"}
    for prefix in (Path("01_源文件"), Path("04_旁白"), Path("08_输出")):
        directory = root / prefix
        if directory.exists():
            protected.update(
                path.relative_to(root).as_posix() for path in directory.rglob("*") if path.is_file()
            )
    protected.update(_current_checkpoints(root))
    if project.preflight_report and project.preflight_report.snapshot_path:
        protected.add(project.preflight_report.snapshot_path)
    return protected


def _current_checkpoints(root: Path) -> set[str]:
    directory = root / "09_日志" / "检查点"
    if not directory.exists():
        return set()
    pattern = re.compile(r"^(?P<job>[0-9a-f-]{36})-(?P<sequence>[0-9]+)\.json$")
    latest: dict[str, tuple[int, Path]] = {}
    for path in directory.glob("*.json"):
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match is None:
            continue
        job = match.group("job")
        sequence = int(match.group("sequence"))
        if job not in latest or sequence > latest[job][0]:
            latest[job] = (sequence, path)
    return {path.relative_to(root).as_posix() for _, path in latest.values()}


def _affected_nodes(paths: list[str]) -> list[str]:
    nodes: set[str] = set()
    for path in paths:
        parts = Path(path).parts
        if parts[0] == "02_页面预览":
            nodes.add("page_preview")
        elif parts[0] == "03_文字识别":
            nodes.add("extraction")
        elif parts[0] == "05_音频":
            nodes.add("audio")
        elif parts[0] == "06_字幕":
            nodes.add("subtitle")
        elif parts[0] == "07_视频工程":
            nodes.add("segment")
        elif parts[:2] == ("09_日志", "预检"):
            nodes.add("preflight_report")
        elif parts[:2] == ("09_日志", "检查点"):
            nodes.add("checkpoint")
    if nodes:
        nodes.add("final")
    return sorted(nodes)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
