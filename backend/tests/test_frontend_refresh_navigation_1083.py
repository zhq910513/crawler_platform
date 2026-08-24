from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / 'frontend' / 'src' / 'layouts' / 'MainLayout.vue'
CLIENT = ROOT / 'frontend' / 'src' / 'api' / 'client.ts'
SERVERS_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ServersPage.vue'
AGENT_MAIN = ROOT / 'agent' / 'crawler_agent' / 'main.py'
AGENT_CONFIG = ROOT / 'agent' / 'crawler_agent' / 'config.py'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_navigation_recreates_pages_instead_of_keepalive_stale_views() -> None:
    text = _read(LAYOUT)
    assert '<KeepAlive' not in text
    assert '@select="handleMenuSelect"' in text
    assert 'const viewReloadKey = ref(0)' in text
    assert ':key="`${route.fullPath}:${viewReloadKey}`"' in text
    assert 'function handleMenuSelect(path: string)' in text


def test_get_requests_are_cache_busted_for_refresh_buttons() -> None:
    text = _read(CLIENT)
    assert "(config.method || 'get').toLowerCase() === 'get'" in text
    assert "config.headers['Cache-Control'] = 'no-cache'" in text
    assert "config.headers.Pragma = 'no-cache'" in text
    assert "_t: Date.now()" in text


def test_servers_page_refresh_and_pending_onboarding_polling_contract() -> None:
    text = _read(SERVERS_PAGE)
    assert '<el-button :loading="loading" @click="refreshPage">刷新</el-button>' in text
    assert 'const loading = ref(false)' in text
    assert 'function hasPendingOnboarding()' in text
    assert 'function ensureServerPolling()' in text
    assert "window.setInterval(() => { void load(true) }, 10000)" in text
    assert "ElMessage.success('已刷新')" in text
    assert '容器启动后会立即心跳，默认每 10 秒一次' in text
    assert 'onUnmounted(() => { stopJoinPolling(); stopServerPolling() })' in text


def test_agent_heartbeat_trigger_contract_is_visible_in_code() -> None:
    main_text = _read(AGENT_MAIN)
    config_text = _read(AGENT_CONFIG)
    assert 'last_heartbeat = 0.0' in main_text
    assert 'if now - last_heartbeat >= config.heartbeat_interval_seconds:' in main_text
    assert 'self.api.heartbeat(self.heartbeat_payload())' in main_text
    assert 'heartbeat_interval_seconds: int = Field(default=10' in config_text
