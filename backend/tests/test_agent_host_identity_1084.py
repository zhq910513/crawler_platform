from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_TEMPLATE = ROOT / 'backend' / 'app' / 'templates' / 'install-agent.sh'
AGENT_CONFIG = ROOT / 'agent' / 'crawler_agent' / 'config.py'
AGENT_MAIN = ROOT / 'agent' / 'crawler_agent' / 'main.py'
AGENT_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'agent_service.py'
SERVER_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'server_service.py'
PUBLISH_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue'
SERVERS_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'ServersPage.vue'
TYPES = ROOT / 'frontend' / 'src' / 'types' / 'api.ts'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_installer_collects_host_identity_and_persists_to_agent_env() -> None:
    text = _read(INSTALL_TEMPLATE)
    assert 'detect_hostname(){' in text
    assert 'detect_host_ip(){' in text
    assert 'ip route get 1.1.1.1' in text
    assert 'HOSTNAME_DETECTED="${AGENT_HOSTNAME:-$(detect_hostname)}"' in text
    assert 'HOST_IP_DETECTED="${AGENT_HOST_IP:-$(detect_host_ip || true)}"' in text
    assert 'append_host_identity_env "$ENV_FILE"' in text
    assert 'resume_url="$CONTROL_PLANE_URL/api/v1/agent-bootstrap/resume-env?joinToken=$JOIN_TOKEN&hostname=${HOSTNAME_DETECTED:-}&hostIp=${HOST_IP_DETECTED:-}&publicIp=${PUBLIC_IP_DETECTED:-}"' in text
    assert 'hostIp' in text and '$host_ip_json' in text
    assert 'AGENT_HOST_IP' in text


def test_agent_heartbeat_reports_host_identity_fields() -> None:
    config_text = _read(AGENT_CONFIG)
    main_text = _read(AGENT_MAIN)
    assert 'hostname: str = Field(default="")' in config_text
    assert 'host_ip: str = Field(default="")' in config_text
    assert 'public_ip: str = Field(default="")' in config_text
    assert '"hostname": config.hostname or socket.gethostname()' in main_text
    assert '"hostIp": config.host_ip' in main_text
    assert '"publicIp": config.public_ip' in main_text


def test_control_plane_saves_reported_host_identity_without_new_database_columns() -> None:
    service_text = _read(AGENT_SERVICE)
    model_text = _read(ROOT / 'backend' / 'app' / 'models.py')
    assert 'hostname = (payload.hostname or "").strip()' in service_text
    assert 'host_ip = (payload.host_ip or "").strip()' in service_text
    assert 'observed_remote_address = (observed_remote_address or "").strip()' in service_text
    assert 'reported_address = host_ip or public_ip or observed_remote_address or hostname or server.server_ip or ""' in service_text
    assert 'server.server_ip = reported_address' in service_text
    assert '"observedRemoteAddress": observed_remote_address or metrics.get("observedRemoteAddress") or ""' in service_text
    assert '"reportedAddress": host_ip or public_ip or observed_remote_address or hostname or server.server_ip or ""' in service_text
    assert 'server_ip: Mapped[str] = mapped_column(String(128)' in model_text
    assert 'hostname: Mapped[' not in model_text
    assert 'host_ip: Mapped[' not in model_text


def test_bootstrap_env_consumes_and_reemits_host_identity_contract() -> None:
    schemas_text = _read(ROOT / 'backend' / 'app' / 'schemas.py')
    service_text = _read(SERVER_SERVICE)
    assert 'host_ip: str = Field(default="", max_length=128)' in schemas_text
    assert 'public_ip: str = Field(default="", max_length=128)' in schemas_text
    assert 'detected_host_ip' in service_text
    assert 'server.server_ip = detected_host_ip or detected_public_ip or detected_hostname' in service_text
    assert 'hostname: str = Query("")' in _read(ROOT / 'backend' / 'app' / 'api' / 'agent_bootstrap.py')
    assert '"AGENT_HOST_IP": detected_host_ip or server.server_ip' in service_text
    assert '"AGENT_HOST_IP": dict(server.metrics or {}).get("hostIp") or server.server_ip' in service_text


def test_project_publish_blocks_nodes_before_first_heartbeat_and_displays_collected_address() -> None:
    text = _read(PUBLISH_PAGE)
    assert "{{ serverAddressText(server) }}" in text
    assert "'节点地址采集中'" in text
    assert "server.agentConnectionStatus !== 'ONLINE' || !server.agentLastHeartbeatAt" in text
    assert "'等待首次心跳'" in text
    assert "{{ serverDeployable(server) ? '可部署' : serverBlockReason(server) }}" in text
    assert "'未上报地址'" not in text


def test_servers_page_uses_reported_address_fallback_and_types_expose_identity_metrics() -> None:
    servers_text = _read(SERVERS_PAGE)
    types_text = _read(TYPES)
    assert 'function serverAddressText(row: ServerNode)' in servers_text
    assert 'row.metrics?.reportedAddress' in servers_text
    assert 'row.metrics?.observedRemoteAddress' in servers_text
    assert 'observedRemoteAddress?: string' in types_text
    assert 'hostIp?: string' in types_text
    assert 'publicIp?: string' in types_text
    assert 'reportedAddress?: string' in types_text
