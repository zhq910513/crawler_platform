from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate


def test_cicd_one_click_guide_and_public_templates() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'hc_cicd_1031', 'companyName': 'H公司CI1031'}).json()['data']
    client.patch('/api/v1/system-settings', headers=headers, json={'platformPublicUrl': 'https://platform.example.com'})

    guide = client.get('/api/v1/cicd/spider-projects/one-click-guide', headers=headers, params={'companyId': company['companyId'], 'provider': 'github'}).json()['data']
    assert guide['mode'] == 'PERSONAL_GIT_ACCOUNT_COMPANY_CODE_INIT'
    assert guide['companyCode'] == 'hc_cicd_1031'
    assert guide['platformPublicUrlConfigured'] is True
    assert 'CRAWLER_COMPANY_CODE=hc_cicd_1031' in guide['oneLineInitCommand']
    assert '.github/workflows/crawler-platform-spider-release.yml' == guide['workflowPath']
    assert 'CRAWLER_PLATFORM_COMPANY_ID' not in guide['workflowContent']
    assert 'CRAWLER_PLATFORM_DISCOVERY_TOKEN' in str(guide['globalSecrets'])
    assert 'crawler_project.json.companyCode' in str(guide['projectDefaults'])
    assert 'docker/build-push-action' in guide['workflowContent']
    assert 'Validate project ownership' in guide['workflowContent']

    script = client.get('/api/v1/cicd/spider-release-register.py')
    assert script.status_code == 200
    assert 'def build_payload' in script.text
    init_script = client.get('/api/v1/cicd/spider-project-init.sh')
    assert init_script.status_code == 200
    assert 'crawler_project.json' in init_script.text


def test_spider_release_register_helper_builds_payload_from_crawler_project_json(tmp_path, monkeypatch) -> None:
    helper_path = Path(__file__).resolve().parents[2] / 'cicd' / 'spider_release_register.py'
    spec = importlib.util.spec_from_file_location('spider_release_register_1031', helper_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    (tmp_path / 'VERSION').write_text('1.0.31\n', encoding='utf-8')
    (tmp_path / 'crawler_project.json').write_text('{"companyCode":"company_a","projectCode":"demo_project","projectName":"演示项目","releaseChannel":"stable"}\n', encoding='utf-8')
    (tmp_path / 'sch.py').write_text('TASKS = [{"definitionKey":"demo","taskName":"示例","entryModule":"spiders.demo","entryFunction":"main"}]\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('IMAGE_DIGEST', 'sha256:' + 'a' * 64)
    monkeypatch.setenv('CRAWLER_PLATFORM_URL', 'https://platform.example.com')
    monkeypatch.setenv('CRAWLER_PLATFORM_DISCOVERY_TOKEN', 'token')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'org/source_repo_name')
    monkeypatch.setenv('GITHUB_REPOSITORY_OWNER', 'org')
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://github.com')
    monkeypatch.setenv('GITHUB_REF_NAME', 'main')
    monkeypatch.setenv('GITHUB_SHA', 'abc123')

    payload = module.build_payload()
    assert 'companyId' not in payload
    assert payload['manifest']['companyCode'] == 'company_a'
    assert payload['manifest']['projectCode'] == 'demo_project'
    assert payload['manifest']['projectName'] == '演示项目'
    assert payload['manifest']['releaseVersion'] == '1.0.31'
    assert payload['manifest']['imageRepository'] == 'ghcr.io/org/demo_project'
    assert payload['manifest']['taskDefinitions'][0]['entryFunction'] == 'main'


def test_discovered_project_can_resolve_company_by_company_code() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company_a = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'company_a_1031', 'companyName': '公司A1031'}).json()['data']
    company_b = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'company_b_1031', 'companyName': '公司B1031'}).json()['data']
    token_a = client.post(f"/api/v1/companies/{company_a['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    token_b = client.post(f"/api/v1/companies/{company_b['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1',
        'companyCode': 'company_a_1031',
        'projectKey': 'project-company-code',
        'projectName': '公司编码项目',
        'projectCode': 'project_company_code',
        'repositoryUrl': 'git@example/project-company-code',
        'imageRepository': 'repo/project-company-code',
        'imageDigest': 'sha256:' + 'b' * 64,
        'releaseVersion': '1.0.31',
        'releaseChannel': 'stable',
        'taskDefinitions': [{'definitionKey': 'task_company_code', 'taskName': '任务', 'entryModule': 'spiders.task', 'entryFunction': 'run'}],
    }
    ok = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + token_a}, json={'manifest': manifest})
    assert ok.status_code == 200
    assert ok.json()['data']['companyId'] == company_a['companyId']
    bad = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + token_b}, json={'manifest': manifest})
    assert bad.status_code == 401
    assert bad.json()['code'] == 40151


def test_spider_release_templates_do_not_depend_on_legacy_server_bootstrap() -> None:
    root = Path(__file__).resolve().parents[2]
    cicd_dir = root / 'cicd'
    for name in ['github-actions-spider-release.yml', 'gitlab-ci-spider-release.yml']:
        text = (cicd_dir / name).read_text(encoding='utf-8')
        assert 'ssh-action' not in text
        assert 'DEPLOY_HOST' not in text
        assert 'CRAWLER_PLATFORM_SERVER_CODE' not in text
        assert 'CRAWLER_PLATFORM_COMPANY_ID' not in text
        assert 'bootstrap.sh' not in text
        assert 'spider-release-register.py' in text
        assert 'missing crawler_project.json.companyCode' in text
    gitlab = (cicd_dir / 'gitlab-ci-spider-release.yml').read_text(encoding='utf-8')
    assert 'CI_REGISTRY_USER' in gitlab
    assert 'CI_REGISTRY_PASSWORD' in gitlab
