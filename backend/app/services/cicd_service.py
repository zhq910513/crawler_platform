from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import CrawlerCompany, SysUser
from app.services.permissions import writable_company_id
from app.services.system_config_service import SystemConfigService

ROOT = Path(__file__).resolve().parents[3]


class CicdGuideService:
    def __init__(self, db: Session):
        self.db = db

    def spider_project_one_click_guide(self, user: SysUser, *, provider: str, company_id: int | None = None) -> dict:
        scoped = writable_company_id(user, company_id)
        company = self.db.get(CrawlerCompany, scoped)
        company_code = company.company_code if company else "company_code"
        platform_url = SystemConfigService(self.db).resolve_platform_public_url()
        placeholder_url = platform_url or "https://你的爬虫平台访问地址"
        provider = provider.lower()
        if provider not in {"github", "gitlab"}:
            provider = "github"
        workflow_file = "github-actions-spider-release.yml" if provider == "github" else "gitlab-ci-spider-release.yml"
        workflow_path = ".github/workflows/crawler-platform-spider-release.yml" if provider == "github" else ".gitlab-ci.yml"
        return {
            "provider": provider,
            "mode": "PERSONAL_GIT_ACCOUNT_COMPANY_CODE_INIT",
            "platformPublicUrl": platform_url,
            "platformPublicUrlConfigured": bool(platform_url),
            "companyId": scoped,
            "companyCode": company_code,
            "globalVariables": self._global_variables(provider, placeholder_url),
            "globalSecrets": self._global_secrets(provider),
            "projectDefaults": [
                {"name": "crawler_project.json.companyCode", "required": True, "value": company_code, "description": "项目所属公司编码；不同公司项目放在个人 GitHub 下时必须靠它区分公司"},
                {"name": "crawler_project.json.projectCode", "required": False, "description": "不配置时默认使用 Git 仓库名"},
                {"name": "crawler_project.json.projectName", "required": False, "description": "不配置时默认使用 Git 仓库名"},
                {"name": "CRAWLER_IMAGE_REPOSITORY", "required": False, "description": "不配置时由 registry host + namespace + 项目编码推导"},
                {"name": "CRAWLER_SERVER_CODES", "required": False, "description": "通常不要在 CI 配；同一 release 要部署到多台服务器，应在平台一键部署时选择服务器"},
            ],
            "workflowPath": workflow_path,
            "workflowContent": self._read(workflow_file),
            "helperScriptUrl": f"{placeholder_url.rstrip('/')}/api/v1/cicd/spider-release-register.py",
            "initScriptUrl": f"{placeholder_url.rstrip('/')}/api/v1/cicd/spider-project-init.sh",
            "oneLineInitCommand": f"curl -fsSL {placeholder_url.rstrip('/')}/api/v1/cicd/spider-project-init.sh | CRAWLER_PLATFORM_URL={placeholder_url.rstrip('/')} CRAWLER_COMPANY_CODE={company_code} sh -s -- {provider}",
            "commitCommand": "git add . && git commit -m '接入 crawler platform 自动构建发布' && git push",
            "notes": [
                "个人 GitHub 账号下混放不同公司项目时，不要把 companyId 配成个人账号全局变量；项目归属写进 crawler_project.json.companyCode。",
                "CRAWLER_PLATFORM_DISCOVERY_TOKEN 仍是公司级凭证；当前数据库没有全局多公司 discovery token，不能用 A 公司 token 注册 B 公司项目。",
                "同一公司部署多台服务器不影响 Git 配置；CI 只构建并注册一个 digest，平台一键部署时选择多台服务器，多个 Agent 各自拉同一个 digest。",
                "平台当前不会直接修改远端 Git 仓库，因为没有 GitHub App、GitLab PAT 或 OAuth 写入契约。",
                "执行服务器 Agent 不拉 Git、不构建镜像，只拉取平台登记的 imageRepository@sha256:digest。",
            ],
        }

    @staticmethod
    def _read(name: str) -> str:
        return (ROOT / "cicd" / name).read_text(encoding="utf-8")

    @staticmethod
    def _global_variables(provider: str, platform_url: str) -> list[dict]:
        registry_host = "ghcr.io" if provider == "github" else "registry.example.com"
        namespace_hint = "GitHub 用户名；个人仓库建议固定为你的 GitHub 用户名" if provider == "github" else "GitLab group / namespace"
        return [
            {"name": "CRAWLER_PLATFORM_URL", "value": platform_url, "scope": "repository 或个人统一复制", "required": True},
            {"name": "CRAWLER_PLATFORM_REGISTRY_HOST", "value": registry_host, "scope": "repository 或个人统一复制", "required": True},
            {"name": "CRAWLER_PLATFORM_REGISTRY_NAMESPACE", "value": namespace_hint, "scope": "repository 或个人统一复制", "required": True},
            {"name": "CRAWLER_PLATFORM_RELEASE_CHANNEL", "value": "stable", "scope": "repository 或个人统一复制", "required": False},
        ]

    @staticmethod
    def _global_secrets(provider: str) -> list[dict]:
        registry_note = "GitHub ghcr.io 可用 GITHUB_TOKEN；私有仓库建议单独配置" if provider == "github" else "GitLab 自带 registry 可使用 CI_REGISTRY_USER/CI_REGISTRY_PASSWORD，也可单独配置"
        return [
            {"name": "CRAWLER_PLATFORM_DISCOVERY_TOKEN", "scope": "repository secret；按公司使用对应公司的 token", "required": True, "description": "公司级项目发现 token，只能注册该公司项目；个人 GitHub 混放多公司时不能跨公司复用"},
            {"name": "CRAWLER_REGISTRY_USERNAME", "scope": "repository secret", "required": False, "description": registry_note},
            {"name": "CRAWLER_REGISTRY_PASSWORD", "scope": "repository secret", "required": False, "description": registry_note},
        ]
