from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerSpiderEntry, CrawlerSpiderRelease

APP_NAME = "crawler_platform_spiders"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")


class ReleaseValidationError(ValueError):
    pass


def validate_manifest(manifest: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if manifest.get("schema_version") != "1.0":
        raise ReleaseValidationError("仅支持 RELEASE_MANIFEST schema_version=1.0")
    if manifest.get("app_name") != APP_NAME:
        raise ReleaseValidationError(f"app_name 必须为 {APP_NAME}")
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
    return version, normalized


def import_release(
    db: Session,
    *,
    image_repository: str,
    image_tag: str,
    image_digest: str,
    git_commit: str,
    manifest: dict[str, Any],
) -> CrawlerSpiderRelease:
    version, entries = validate_manifest(manifest)
    existing_version = db.scalar(
        select(CrawlerSpiderRelease).where(
            CrawlerSpiderRelease.app_name == APP_NAME,
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
                existing.image_repository != image_repository
                or existing.image_digest != image_digest
                or existing.git_commit != git_commit
                or existing.manifest_json != manifest
            ):
                raise ReleaseValidationError("相同版本或镜像摘要已登记为不同发布内容")
            return existing
    release = CrawlerSpiderRelease(
        app_name=APP_NAME,
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
