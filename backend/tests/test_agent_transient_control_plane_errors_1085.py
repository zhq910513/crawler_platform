from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_MAIN = ROOT / 'agent' / 'crawler_agent' / 'main.py'
AGENT_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'agent_service.py'
SERVERS_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ServersPage.vue'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_agent_does_not_persist_transient_control_plane_connection_refused_as_last_error() -> None:
    text = _read(AGENT_MAIN)
    assert 'from crawler_agent.api import PlatformAPI, PlatformUnavailable, UnauthorizedError' in text
    assert 'except PlatformUnavailable as exc:' in text
    assert 'control plane temporarily unavailable' in text
    assert '不把 HTTPConnectionPool/Connection refused 这类瞬时网络错误写入 lastError' in text
    platform_block = text.split('except PlatformUnavailable as exc:', 1)[1].split('except UnauthorizedError as exc:', 1)[0]
    assert 'self.last_error =' not in platform_block


def test_control_plane_scrubs_stale_transient_agent_network_errors_after_successful_heartbeat() -> None:
    text = _read(AGENT_SERVICE)
    assert 'def _is_transient_control_plane_error(message: str) -> bool:' in text
    assert 'def _normalize_agent_last_error(cls, message: str) -> str:' in text
    assert 'HTTPConnectionPool'.lower() in text.lower()
    assert '/api/v1/agent-heartbeats' in text
    assert '/api/v1/agent-run-claims' in text
    assert 'normalized_last_error = self._normalize_agent_last_error(payload.last_error)' in text
    assert 'agent.last_error = normalized_last_error' in text
    assert '"lastError": self._normalize_agent_last_error(payload.last_error) if normalized_last_error is None else normalized_last_error' in text


def test_servers_page_hides_recovered_transient_connection_refused_noise_for_online_nodes() -> None:
    text = _read(SERVERS_PAGE)
    assert '<el-table-column label="最近异常" min-width="220" show-overflow-tooltip>' in text
    assert 'function isTransientControlPlaneError(value?: string | null)' in text
    assert "text.includes('httpconnectionpool')" in text
    assert "text.includes('/api/v1/agent-heartbeats')" in text
    assert "if (row.agentConnectionStatus === 'ONLINE' && isTransientControlPlaneError(text)) return '-'" in text
    assert '{{ recentErrorText(s.row) }}' in text
