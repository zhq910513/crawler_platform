#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED", "TIMED_OUT", "LOST", "SKIPPED"}
DEFAULT_COMMAND_TIMEOUT = int(os.getenv("SMOKE_COMMAND_TIMEOUT_SECONDS", "600"))


def load_env(path):
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class ApiError(RuntimeError):
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload
        super().__init__(f"HTTP {status}: {payload}")


class PlatformClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def request(self, method, path, data=None, token=None, discovery_token=None):
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "crawler-platform-smoke-test/1.0"}
        bearer = token if token is not None else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
            headers["X-User-Active"] = "true"
        if discovery_token:
            headers["Authorization"] = f"Discovery {discovery_token}"
        req = urllib.request.Request(f"{self.base_url}{path}", data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw) if raw else {"code": 200, "data": None}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
            raise ApiError(exc.code, payload) from exc
        if not isinstance(payload, dict) or payload.get("code") != 200:
            raise ApiError(200, payload)
        return payload.get("data")

    def login(self, username, password):
        body = {"userName": username, "password": password}
        try:
            data = self.request("POST", "/sessions", body, token="")
        except ApiError as exc:
            payload = exc.payload if isinstance(exc.payload, dict) else {}
            if payload.get("code") == 40901 and payload.get("data", {}).get("forceLoginToken"):
                body["forceLoginToken"] = payload["data"]["forceLoginToken"]
                data = self.request("POST", "/sessions", body, token="")
            else:
                raise
        self.token = data["accessToken"]
        return data


def run(cmd, cwd=ROOT, check=True, timeout=None):
    timeout = DEFAULT_COMMAND_TIMEOUT if timeout is None else timeout
    print("$ " + " ".join(cmd), flush=True)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        if partial:
            print(partial.rstrip(), flush=True)
        raise RuntimeError(f"命令超时({timeout}s)：{' '.join(cmd)}") from exc
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"命令执行失败({proc.returncode})：{' '.join(cmd)}")
    return proc.stdout


def docker_available():
    try:
        run(["docker", "version"], check=True)
        return True
    except Exception:
        return False


def ensure_registry(name, port):
    existing = run(["docker", "ps", "-a", "--format", "{{.Names}}"], check=True).splitlines()
    if name in existing:
        running = run(["docker", "inspect", "-f", "{{.State.Running}}", name], check=True).strip()
        if running != "true":
            run(["docker", "start", name])
        return
    # 正式环境可能已经运行 crawler-platform-agent-registry；smoke 直接复用同一 registry，
    # 不再为了测试创建第二个容器抢占 5000/TCP。
    published = run(["docker", "ps", "--format", "{{.Names}} {{.Image}} {{.Ports}}"], check=True).splitlines()
    for line in published:
        if "registry:2" in line and (f"0.0.0.0:{port}->5000/tcp" in line or f":::{port}->5000/tcp" in line):
            print(f"复用已有 registry：{line.split()[0]}")
            return
    run(["docker", "run", "-d", "--name", name, "--restart=always", "-p", f"{port}:5000", "registry:2"])


def build_smoke_image(registry, tag, pip_index_url):
    image_repo = f"{registry}/crawler-platform-smoke-spider"
    image_tag = f"{image_repo}:{tag}"
    run(["docker", "build", "--build-arg", "PIP_INDEX_URL=" + pip_index_url, "-f", "examples/smoke_spider/Dockerfile", "-t", image_tag, "."])
    run(["docker", "push", image_tag])
    run(["docker", "pull", image_tag])
    inspect = run(["docker", "image", "inspect", image_tag])
    data = json.loads(inspect)
    repo_digests = data[0].get("RepoDigests") or []
    digest_ref = ""
    for item in repo_digests:
        if item.startswith(image_repo + "@"):
            digest_ref = item
            break
    if not digest_ref:
        raise RuntimeError(f"无法从 docker inspect 获取 RepoDigest：{repo_digests}")
    digest = digest_ref.split("@", 1)[1]
    print(f"SMOKE_IMAGE_REPOSITORY={image_repo}")
    print(f"SMOKE_IMAGE_DIGEST={digest}")
    return image_repo, digest


def start_agent_container(agent_token, agent_code, server_code, base_url, capabilities, image, container_name, max_slots, pip_index_url):
    run(["docker", "build", "--build-arg", "PIP_INDEX_URL=" + pip_index_url, "--build-arg", "AGENT_VERSION=smoke-test", "--build-arg", "APP_GIT_COMMIT=smoke-test", "--build-arg", "APP_BUILD_TIME=smoke-test", "-f", "agent/Dockerfile", "-t", image, "agent"])
    run(["docker", "rm", "-f", container_name], check=False)
    Path("/data/crawler-platform/projects").mkdir(parents=True, exist_ok=True)
    Path("/var/lib/crawler-agent/runs").mkdir(parents=True, exist_ok=True)
    run([
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", "unless-stopped",
        "--network", "host",
        "-e", f"AGENT_CONTROL_PLANE_URL={base_url}",
        "-e", "AGENT_VERIFY_TLS=false",
        "-e", f"AGENT_AGENT_TOKEN={agent_token}",
        "-e", f"AGENT_AGENT_CODE={agent_code}",
        "-e", f"AGENT_SERVER_CODE={server_code}",
        "-e", "AGENT_AGENT_VERSION=smoke-test",
        "-e", f"AGENT_MAX_SLOTS={max_slots}",
        "-e", "AGENT_POLL_INTERVAL_SECONDS=2",
        "-e", "AGENT_HEARTBEAT_INTERVAL_SECONDS=5",
        "-e", "AGENT_REQUEST_TIMEOUT_SECONDS=20",
        "-e", "AGENT_RUN_ROOT=/var/lib/crawler-agent/runs",
        "-e", "AGENT_PROJECT_DATA_ROOT=/data/crawler-platform/projects",
        "-e", f"AGENT_CAPABILITIES_JSON={json.dumps(capabilities, separators=(',', ':'))}",
        "-e", "AGENT_ENABLE_SHARED_PROJECT_CACHE=true",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", "/var/lib/crawler-agent:/var/lib/crawler-agent",
        "-v", "/data/crawler-platform/projects:/data/crawler-platform/projects",
        image,
    ])


def terminal_status(client, task_id, run_id, timeout_seconds):
    deadline = time.time() + timeout_seconds
    last = ""
    while time.time() < deadline:
        runs = client.request("GET", f"/runs?taskId={task_id}")
        target = None
        for item in runs:
            if int(item.get("runId")) == int(run_id):
                target = item
                break
        if target:
            status = str(target.get("runStatus"))
            routing = str(target.get("routingStatus"))
            server = target.get("serverId")
            msg = f"runId={run_id} runStatus={status} routingStatus={routing} serverId={server}"
            if msg != last:
                print(msg, flush=True)
                last = msg
            if status in TERMINAL:
                return status
        time.sleep(3)
    raise RuntimeError(f"等待 runId={run_id} 进入终态超时，最后状态：{last}")



def print_failure_diagnostics(agent_container):
    commands = [
        ["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"],
        ["docker", "logs", "--tail", "120", agent_container],
        ["docker", "compose", "ps"],
        ["docker", "compose", "logs", "--tail", "120", "api"],
        ["docker", "compose", "logs", "--tail", "120", "scheduler"],
    ]
    print("---- smoke-test diagnostics ----", file=sys.stderr)
    for cmd in commands:
        try:
            print("$ " + " ".join(cmd), file=sys.stderr)
            proc = subprocess.run(cmd, cwd=str(ROOT), universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            if proc.stdout:
                print(proc.stdout[-12000:], file=sys.stderr)
        except Exception as diag_exc:
            print("diagnostic command failed: %s" % diag_exc, file=sys.stderr)
    print("---- end diagnostics ----", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="爬虫管理平台零数据测试服端到端 smoke-test")
    parser.add_argument("--base-url", default=os.getenv("SMOKE_BASE_URL", "http://127.0.0.1"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--build-smoke-image", action="store_true")
    parser.add_argument("--registry", default=os.getenv("SMOKE_REGISTRY", "localhost:5000"))
    parser.add_argument("--registry-container", default="crawler-platform-smoke-registry")
    parser.add_argument("--registry-port", type=int, default=5000)
    parser.add_argument("--image-repository", default=os.getenv("SMOKE_IMAGE_REPOSITORY", ""))
    parser.add_argument("--image-digest", default=os.getenv("SMOKE_IMAGE_DIGEST", ""))
    parser.add_argument("--start-agent", action="store_true")
    parser.add_argument("--agent-image", default=os.getenv("SMOKE_AGENT_IMAGE", "crawler_platform_agent:smoke"))
    parser.add_argument("--agent-container", default=os.getenv("SMOKE_AGENT_CONTAINER", "crawler-agent-smoke"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-slots", type=int, default=2)
    args = parser.parse_args()

    env = load_env(ROOT / args.env_file)
    admin_user = env.get("ADMIN_USERNAME", "admin")
    admin_password = env.get("ADMIN_PASSWORD", "")
    if not admin_password:
        raise RuntimeError("未在 .env 中找到 ADMIN_PASSWORD")

    if args.build_smoke_image:
        if not docker_available():
            raise RuntimeError("当前服务器不可用 Docker，无法构建 smoke 镜像")
        ensure_registry(args.registry_container, args.registry_port)
        tag = datetime.now().strftime("%Y%m%d%H%M%S")
        args.image_repository, args.image_digest = build_smoke_image(args.registry, tag, env.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple"))
    if not args.image_repository or not args.image_digest:
        raise RuntimeError("必须提供 --image-repository / --image-digest，或使用 --build-smoke-image")

    api_base = args.base_url.rstrip("/") + "/api/v1"
    client = PlatformClient(api_base)
    print("检查健康接口...")
    health_req = urllib.request.Request(args.base_url.rstrip("/") + "/health", method="GET")
    with urllib.request.urlopen(health_req, timeout=15) as resp:
        print(resp.read().decode("utf-8")[:300])

    print("登录超级管理员...")
    client.login(admin_user, admin_password)

    suffix = datetime.now().strftime("%m%d%H%M%S")
    company_code = f"smoke-{suffix}"
    server_code = f"smoke-server-{suffix}"
    agent_code = f"smoke-agent-{suffix}"
    project_key = f"smoke-project-{suffix}"
    project_code = f"smoke_project_{suffix}"

    print("创建公司...")
    company = client.request("POST", "/companies", {"companyCode": company_code, "companyName": f"测试公司 {suffix}", "timezone": "Asia/Shanghai", "description": "smoke test"})
    company_id = int(company["companyId"])
    print(f"companyId={company_id}")

    print("注册 Agent 节点并生成 token...")
    agent_result = client.request("POST", "/agents", {"companyId": company_id, "serverCode": server_code, "serverName": f"测试服务器 {suffix}", "serverIp": "127.0.0.1", "agentCode": agent_code, "agentName": f"测试Agent {suffix}", "maxContainerSlots": args.max_slots})
    agent_token = agent_result["agentToken"]
    server_id = int(agent_result["server"]["serverId"])
    print(f"serverId={server_id} agentToken={agent_token[:8]}***")

    if args.start_agent:
        print("启动真实 Agent 容器...")
        start_agent_container(agent_token, agent_code, server_code, args.base_url.rstrip("/"), {"smoke": True, "browser": False, "proxy": False}, args.agent_image, args.agent_container, args.max_slots, env.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple"))

    print("创建公司级项目接入凭证...")
    discovery = client.request("POST", f"/companies/{company_id}/discovery-tokens")
    discovery_token = discovery["discoveryToken"]

    manifest = {
        "manifestVersion": "1",
        "companyCode": company_code,
        "projectKey": project_key,
        "projectName": "测试服链路验证项目",
        "projectCode": project_code,
        "repositoryUrl": "https://example.invalid/smoke.git",
        "imageRepository": args.image_repository,
        "imageDigest": args.image_digest,
        "gitBranch": "main",
        "gitCommit": suffix,
        "releaseVersion": f"smoke-{suffix}",
        "releaseChannel": "stable",
        "runtimeType": "python",
        "supportedArch": "linux/amd64",
        "requiredCapabilities": {"smoke": True},
        "taskDefinitions": [
            {
                "definitionKey": "smoke_success",
                "taskName": "测试服链路验证任务",
                "entryModule": "spiders.smoke_tasks",
                "entryFunction": "run",
                "defaultParams": {"message": "hello-crawler-platform"},
                "suggestedCron": "*/10 * * * *",
                "executionMode": "SINGLE",
                "idempotencyPolicy": "IDEMPOTENT",
                "requiredCapabilities": {"smoke": True},
                "runtimeMode": "SHARED_ENV_ISOLATED",
                "taskGroup": "smoke",
                "taskMaxConcurrency": 2,
                "groupMaxConcurrency": 4,
                "exclusiveMode": False,
                "ioClass": "LOW",
                "shmSizeMb": 64,
                "logLimitMb": 20,
                "resourceLocks": [],
                "resourceRequirements": {"cpu": 0.25, "memoryMb": 256},
            }
        ],
    }
    print("上报待接入项目...")
    discovered = client.request("POST", "/discovered-projects", {"companyId": company_id, "manifest": manifest}, token="", discovery_token=discovery_token)
    discovered_id = int(discovered["discoveredProjectId"])
    print(f"discoveredProjectId={discovered_id}")

    print("接入正式项目...")
    project = client.request("POST", "/projects", {"discoveredProjectId": discovered_id, "remark": "smoke test", "dispatchMode": "LOAD_BALANCE", "minAvailableServers": 1, "maxActiveServers": 2, "allowDeployedFallback": True, "allowCompanyPoolFallback": False})
    project_id = int(project["projectId"])
    print(f"projectId={project_id}")

    print("确认项目执行节点范围...")
    client.request("PUT", f"/projects/{project_id}/servers", {"servers": [{"serverId": server_id, "schedulingStatus": "ENABLED", "serverRole": "ACTIVE", "priority": 100, "weight": 100, "maxConcurrency": args.max_slots, "autoEjectEnabled": True, "autoRecoverEnabled": True}], "reason": "smoke test"})

    print("读取任务定义...")
    definitions = client.request("GET", f"/projects/{project_id}/task-definitions")
    if not definitions:
        raise RuntimeError("项目接入后没有任务定义")
    definition_id = int(definitions[0]["definitionId"])
    print(f"definitionId={definition_id}")

    print("创建正式任务...")
    task = client.request("POST", "/tasks", {"definitionId": definition_id, "taskCode": f"smoke_task_{suffix}", "taskName": "测试服链路验证任务", "parameters": {"message": "smoke-ok", "sleepSeconds": 0.2}, "status": "ENABLED", "imagePolicy": "RELEASE_CHANNEL", "releaseChannel": "stable", "cpuLimit": 0.25, "memoryLimitMb": 256, "timeoutSeconds": 120, "maxRetryCount": 0, "scheduleStatus": "PAUSED", "scheduleType": "MANUAL", "overlapPolicy": "QUEUE", "serverIds": [server_id], "runtimeMode": "SHARED_ENV_ISOLATED", "taskGroup": "smoke", "taskMaxConcurrency": 2, "groupMaxConcurrency": 4, "exclusiveMode": False, "ioClass": "LOW", "shmSizeMb": 64, "logLimitMb": 20, "resourceLocks": []})
    task_id = int(task["taskId"])
    print(f"taskId={task_id}")

    if args.start_agent:
        print("等待真实 Agent 心跳上线...")
        deadline = time.time() + 90
        while time.time() < deadline:
            servers = client.request("GET", f"/servers?companyId={company_id}")
            row = next((x for x in servers if int(x.get("serverId")) == server_id), None)
            if row and row.get("healthStatus") in {"HEALTHY", "DEGRADED"} and row.get("capacityStatus") in {"NORMAL", "PRESSURE"}:
                print(f"Agent 已上线：healthStatus={row.get('healthStatus')} capacityStatus={row.get('capacityStatus')}")
                break
            time.sleep(3)
        else:
            raise RuntimeError("等待 Agent 上线超时，请查看 agent 容器日志")

    print("创建手动运行实例...")
    run_data = client.request("POST", "/runs", {"taskId": task_id, "parameters": {"message": "manual-smoke", "sleepSeconds": 0.2}})
    run_id = int(run_data["runId"])
    print(f"runId={run_id}")

    if not args.start_agent:
        print("未启动真实 Agent，已完成 API 主链路 smoke。后续请启动 Agent 后观察 run 是否被领取。")
        return 0

    print("等待 Agent 拉取镜像、启动任务容器并回传终态...")
    final_status = terminal_status(client, task_id, run_id, args.timeout)
    if final_status != "SUCCEEDED":
        raise RuntimeError(f"Smoke run 未成功，最终状态：{final_status}")
    print("✅ 测试服端到端 smoke-test 通过。")
    print(f"companyId={company_id} projectId={project_id} taskId={task_id} runId={run_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"❌ smoke-test 失败：{exc}", file=sys.stderr)
        try:
            container = os.environ.get("SMOKE_AGENT_CONTAINER", "crawler-agent-smoke")
            print_failure_diagnostics(container)
        except Exception:
            pass
        raise
