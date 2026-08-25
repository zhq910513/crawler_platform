from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class BuildCenterReadiness:
    enabled: bool
    implemented: bool
    mode: str
    blocked_reason_code: str
    missing_items: tuple[str, ...]
    message: str
    next_actions: tuple[str, ...]

    def asdict(self) -> dict:
        return {
            "enabled": self.enabled,
            "implemented": self.implemented,
            "mode": self.mode,
            "supportedReleasePath": "PLATFORM_MANAGED_BUILD_RELEASE_REGISTRATION",
            "blockedReasonCode": self.blocked_reason_code,
            "missingItems": list(self.missing_items),
            "message": self.message,
            "nextActions": list(self.next_actions),
            "buildContractScript": "scripts/platform_build_contract.sh",
            "manifestOutput": ".release/crawler_manifest.json",
            "releaseOwnership": "crawler_platform",
        }


class BuildCenterService:
    """Readiness contract for platform-driven spider project builds.

    This service intentionally does not pretend the build center is implemented.
    The current codebase has no real build executor, repository credential model,
    or registry push credential model, so the only safe answer is fail-closed.
    """

    def __init__(self, db: Session):
        self.db = db

    def spider_project_readiness(self) -> BuildCenterReadiness:
        missing = ("平台构建执行器", "代码仓库读取凭据", "镜像仓库推送凭据")
        return BuildCenterReadiness(
            enabled=False,
            implemented=False,
            mode="PLATFORM_BUILD_CENTER_REQUIRED",
            blocked_reason_code="PLATFORM_BUILD_CENTER_NOT_READY",
            missing_items=missing,
            message="平台构建中心未就绪：" + "、".join(missing) + " 尚未完成。未登记 Release 不能发布；后续应由平台构建中心拉取源码、执行被动构建契约、构建镜像、登记 Release，而不是要求爬虫项目主动 CI/CD。",
            next_actions=(
                "完善平台构建执行器，由平台创建 Build Job 并在隔离环境拉取代码。",
                "在平台侧维护代码仓库读取凭据，不把读取凭据写入爬虫项目。",
                "在平台侧维护镜像仓库推送凭据，不把推送凭据写入爬虫项目。",
                "构建器调用爬虫项目 scripts/platform_build_contract.sh 生成 manifest，再由平台登记 Release。",
            ),
        )
