from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerSpiderEntry, CrawlerSpiderRelease

APP_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,100}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")


class ReleaseValidationError(ValueError):
    pass


def validate_manifest(manifest: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """Validate a spider project release manifest.

    app_name is no longer hard-coded to crawler_platform_spiders. A platform can
    now manage many company/customer spider projects; each project publishes its
    own immutable image releases and entry list.
    """
    if manifest.get("schema_version") != "1.0":
        raise ReleaseValidationError("仅支持 RELEASE_MANIFEST schema_version=1.0")
    app_name = str(manifest.get("app_name") or "crawler_platform_spiders")
    if not APP_NAME_RE.fullmatch(app_name):
        raise ReleaseValidationError("app_name 只能包含字母、数字、下划线、中划线和点，长度 2-100")
    version = str(manifest.get("version", ""))
    if not SEMVER_RE.fullmatch(version):
        raise ReleaseValidationError("version 必须是语义版本")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ReleaseValidationError("manifest.entries 不能为空")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ReleaseValidationError("entries 项必须是对象")
        task_name = str(raw.get("task_name", ""))
        if not TASK_NAME_RE.fullmatch(task_name):
            raise ReleaseValidationError(f"无效 task_name：{task_name}")
        if task_name in seen:
            raise ReleaseValidationError(f"重复 task_name：{task_name}")
        seen.add(task_name)
        profile = str(raw.get("image_profile", "api"))
        if profile not in {"api", "browser"}:
            raise ReleaseValidationError(f"无效 image_profile：{profile}")
        timeout = int(raw.get("default_timeout_seconds", 3600))
        if not 1 <= timeout <= 604800:
            raise ReleaseValidationError(f"无效默认超时：{task_name}")
        required = raw.get("required_resources", [])
        schema = raw.get("parameter_schema", {})
        if not isinstance(required, list) or not all(isinstance(x, str) and x for x in required):
            raise ReleaseValidationError(f"required_resources 无效：{task_name}")
        if not isinstance(schema, dict):
            raise ReleaseValidationError(f"parameter_schema 无效：{task_name}")
        normalized.append({
            "task_name": task_name,
            "display_name": str(raw.get("display_name") or raw.get("description") or task_name)[:200],
            "description": str(raw.get("description", ""))[:1000],
            "image_profile": profile,
            "parameter_schema": schema,
            "required_resources": required,
            "default_timeout_seconds": timeout,
        })
    return app_name, version, normalized


def latest_release_id(db: Session, *, app_name: str, image_repository: str) -> int | None:
    row = db.scalar(
        select(CrawlerSpiderRelease)
        .where(
            CrawlerSpiderRelease.app_name == app_name,
            CrawlerSpiderRelease.image_repository == image_repository,
            CrawlerSpiderRelease.status == "ACTIVE",
        )
        .order_by(CrawlerSpiderRelease.published_at.desc(), CrawlerSpiderRelease.release_id.desc())
        .limit(1)
    )
    return row.release_id if row else None


def is_latest_selectable_release(db: Session, release: CrawlerSpiderRelease) -> bool:
    if release.status != "ACTIVE":
        return False
    return latest_release_id(db, app_name=release.app_name, image_repository=release.image_repository) == release.release_id


def ensure_latest_selectable_release(db: Session, release: CrawlerSpiderRelease) -> None:
    if not is_latest_selectable_release(db, release):
        raise ReleaseValidationError("只能选择发布时间最新的镜像版本；历史镜像只读，如需回滚请重新发布旧代码生成新的最新版本")


def import_release(
    db: Session,
    *,
    image_repository: str,
    image_tag: str,
    image_digest: str,
    git_commit: str,
    manifest: dict[str, Any],
) -> CrawlerSpiderRelease:
    app_name, version, entries = validate_manifest(manifest)
    existing_version = db.scalar(
        select(CrawlerSpiderRelease).where(
            CrawlerSpiderRelease.app_name == app_name,
            CrawlerSpiderRelease.version == version,
        )
    )
    existing_digest = db.scalar(
        select(CrawlerSpiderRelease).where(
            CrawlerSpiderRelease.image_repository == image_repository,
            CrawlerSpiderRelease.image_digest == image_digest,
        )
    )
    for existing in (existing_version, existing_digest):
        if existing:
            if (
                existing.app_name != app_name
                or existing.image_repository != image_repository
                or existing.image_digest != image_digest
                or existing.git_commit != git_commit
                or existing.manifest_json != manifest
            ):
                raise ReleaseValidationError("相同版本或镜像摘要已登记为不同发布内容")
            return existing
    release = CrawlerSpiderRelease(
        app_name=app_name,
        version=version,
        image_repository=image_repository,
        image_tag=image_tag,
        image_digest=image_digest,
        git_commit=git_commit,
        manifest_json=manifest,
        status="ACTIVE",
    )
    db.add(release)
    db.flush()
    db.add_all([CrawlerSpiderEntry(release_id=release.release_id, **entry) for entry in entries])
    db.flush()
    return release
