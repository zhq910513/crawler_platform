from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import CrawlerCompany, SysUser
from app.services.permissions import writable_company_id
from app.services.system_config_service import SystemConfigService

ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLACEHOLDER = "__CRAWLER_CONTROL_BASE_URL__"
PROVIDER_PLACEHOLDER = "__CRAWLER_CI_PROVIDER__"
COMPANY_PLACEHOLDER = "__CRAWLER_COMPANY_CODE__"


class CicdGuideService:
    def __init__(self, db: Session):
        self.db = db

    def spider_project_one_click_guide(self, user: SysUser, *, provider: str, company_id: int | None = None, detected_base_url: str = "") -> dict:
        scoped = writable_company_id(user, company_id)
        company = self.db.get(CrawlerCompany, scoped)
        company_code = company.company_code if company else "company_code"
        url_info = SystemConfigService(self.db).inspect_control_plane_public_base_url(detected_base_url)
        control_base_url = url_info["controlPlanePublicBaseUrl"] or "https://控制端公网回调地址"
        provider = provider.lower()
        if provider not in {"github", "gitlab"}:
            provider = "github"
        workflow_file = "github-actions-spider-release.yml" if provider == "github" else "gitlab-ci-spider-release.yml"
        workflow_path = ".github/workflows/crawler-platform-spider-release.yml" if provider == "github" else ".gitlab-ci.yml"
        init_url = f"{control_base_url.rstrip('/')}/api/v1/cicd/spider-project-init.sh?provider={provider}&companyCode={company_code}"
        return {
            "provider": provider,
            "mode": "PERSONAL_GIT_ACCOUNT_COMPANY_CODE_INIT",
            "controlPlanePublicBaseUrl": url_info["controlPlanePublicBaseUrl"],
            "controlPlanePublicBaseUrlSource": url_info["source"],
            "controlPlanePublicBaseUrlConfigured": bool(url_info["controlPlanePublicBaseUrl"]),
            "controlPlanePublicBaseUrlWarnings": url_info["warnings"],
            # 旧字段保留给旧前端兼容。
            "platformPublicUrl": url_info["controlPlanePublicBaseUrl"],
            "platformPublicUrlConfigured": bool(url_info["controlPlanePublicBaseUrl"]),
            "companyId": scoped,
            "companyCode": company_code,
            "globalVariables": self._global_variables(provider),
            "globalSecrets": self._global_secrets(provider),
            "projectDefaults": [
                {"name": "crawler_project.json.companyCode", "required": True, "value": company_code, "description": "项目所属公司编码；不同公司项目放在个人 GitHub 下时靠它区分公司"},
                {"name": "crawler_project.json.projectCode", "required": False, "description": "不配置时默认使用 Git 仓库名"},
                {"name": "crawler_project.json.projectName", "required": False, "description": "不配置时默认使用 Git 仓库名"},
                {"name": "CRAWLER_IMAGE_REPOSITORY", "required": False, "description": "不配置时由 registry host + namespace + 项目编码推导"},
            ],
            "workflowPath": workflow_path,
            "workflowContent": render_workflow_template(self._read(workflow_file), control_base_url),
            "helperScriptUrl": f"{control_base_url.rstrip('/')}/api/v1/cicd/spider-release-register.py",
            "initScriptUrl": init_url,
            "oneLineInitCommand": f"curl -fsSL '{init_url}' | sh",
            "commitCommand": "git add . && git commit -m '接入 crawler platform 自动构建发布' && git push",
            "notes": [
                "GitHub/GitLab 仓库不再配置平台链接；初始化脚本会把控制端公网回调地址写入 workflow。",
                "个人 GitHub 账号下混放不同公司项目时，不要把 companyId 配成个人账号全局变量；项目归属写进 crawler_project.json.companyCode。",
                "CRAWLER_PLATFORM_DISCOVERY_TOKEN 仍是公司级凭证；当前数据库没有全局多公司 discovery token，不能用 A 公司 token 注册 B 公司项目。",
                "同一公司部署多台服务器不影响 Git 配置；CI 只构建并注册一个 digest，平台一键部署时选择多台服务器，多个 Agent 各自拉同一个 digest。",
                "执行服务器 Agent 不拉 Git、不构建镜像，只拉取平台登记的 imageRepository@sha256:digest。",
            ],
        }

    @staticmethod
    def _read(name: str) -> str:
        return (ROOT / "cicd" / name).read_text(encoding="utf-8")

    @staticmethod
    def _global_variables(provider: str) -> list[dict]:
        registry_host = "ghcr.io" if provider == "github" else "GitLab 内置 CI_REGISTRY 或私有 registry host"
        namespace_hint = "默认 GitHub 用户名，可不配置" if provider == "github" else "默认 GitLab group / namespace，可不配置"
        return [
            {"name": "CRAWLER_REGISTRY_HOST", "value": registry_host, "scope": "repository variable，可选", "required": False},
            {"name": "CRAWLER_REGISTRY_NAMESPACE", "value": namespace_hint, "scope": "repository variable，可选", "required": False},
            {"name": "CRAWLER_RELEASE_CHANNEL", "value": "stable", "scope": "repository variable，可选", "required": False},
        ]

    @staticmethod
    def _global_secrets(provider: str) -> list[dict]:
        registry_note = "GitHub ghcr.io 默认使用 github.token；私有 registry 再配置" if provider == "github" else "GitLab 自带 registry 可使用 CI_REGISTRY_USER/CI_REGISTRY_PASSWORD，也可单独配置"
        return [
            {"name": "CRAWLER_PLATFORM_DISCOVERY_TOKEN", "scope": "repository secret；按公司使用对应公司的 token", "required": True, "description": "公司级项目发现 token，只能注册该公司项目；个人 GitHub 混放多公司时不能跨公司复用"},
            {"name": "CRAWLER_REGISTRY_USERNAME", "scope": "repository secret", "required": False, "description": registry_note},
            {"name": "CRAWLER_REGISTRY_PASSWORD", "scope": "repository secret", "required": False, "description": registry_note},
        ]


def render_workflow_template(template: str, control_base_url: str) -> str:
    return template.replace(CONTROL_PLACEHOLDER, control_base_url.rstrip("/"))


def render_init_script(template: str, *, control_base_url: str, provider: str, company_code: str) -> str:
    provider = provider if provider in {"github", "gitlab"} else "github"
    return (
        template
        .replace(CONTROL_PLACEHOLDER, control_base_url.rstrip("/"))
        .replace(PROVIDER_PLACEHOLDER, provider)
        .replace(COMPANY_PLACEHOLDER, company_code)
    )
