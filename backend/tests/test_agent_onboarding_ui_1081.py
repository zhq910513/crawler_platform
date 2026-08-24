from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVERS_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ServersPage.vue'
PUBLISH_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue'
INSTALL_TEMPLATE = ROOT / 'backend' / 'app' / 'templates' / 'install-agent.sh'
SERVER_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'server_service.py'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_servers_onboarding_scrolls_to_generated_commands_and_polls_heartbeat() -> None:
    text = _read(SERVERS_PAGE)
    assert "import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'" in text
    assert 'ref="installPanelRef" class="install-panel"' in text
    assert 'async function scrollInstallPanel()' in text
    assert 'installPanelRef.value?.scrollIntoView({ behavior: \'smooth\', block: \'start\' })' in text
    assert 'function startJoinPolling()' in text
    assert 'window.setInterval(async () => {' in text
    assert "ElMessage.success('节点已上线')" in text
    assert 'onboardingStepActive' in text


def test_project_publish_onboarding_scrolls_to_generated_commands_and_polls_heartbeat() -> None:
    text = _read(PUBLISH_PAGE)
    assert "import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'" in text
    assert 'ref="installPanelRef" class="install-panel"' in text
    assert 'async function scrollInstallPanel()' in text
    assert 'function startJoinPolling()' in text
    assert 'await refreshCompanyServers()' in text
    assert "ElMessage.success('节点已上线并自动选中')" in text
    assert 'serverDrawerStepActive' in text


def test_generated_command_does_not_show_backend_warning_toast_after_success() -> None:
    for path in [SERVERS_PAGE, PUBLISH_PAGE]:
        text = _read(path)
        assert 'const warning = joinResult.value.warnings?.[0]' not in text
        assert 'if (warning) ElMessage.warning(warning)' not in text


def test_installer_success_message_matches_auto_refresh_contract() -> None:
    install_text = _read(INSTALL_TEMPLATE)
    service_text = _read(SERVER_SERVICE)
    assert '控制台会自动刷新首轮心跳状态' in install_text
    assert '控制台会自动刷新首轮心跳状态' in service_text
