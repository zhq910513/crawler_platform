from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_tree_does_not_contain_local_database_files() -> None:
    ignored_dirs = {'.git', '.pytest_cache', '__pycache__', 'node_modules', 'dist'}
    offenders = []
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.suffix.lower() in {'.db', '.sqlite', '.sqlite3'}:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_gitignore_blocks_local_database_artifacts() -> None:
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for pattern in ('*.db', '*.sqlite', '*.sqlite3'):
        assert pattern in gitignore


def test_release_version_defaults_are_consistent() -> None:
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    env_example = (ROOT / '.env.example').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    frontend_package = (ROOT / 'frontend/package.json').read_text(encoding='utf-8')
    frontend_lock = (ROOT / 'frontend/package-lock.json').read_text(encoding='utf-8')

    assert f'APP_VERSION={version}' in env_example
    assert f'PLATFORM_IMAGE_TAG={version}' in env_example
    assert f'crawler_platform_api:${{PLATFORM_IMAGE_TAG:-{version}}}' in compose
    assert f'APP_VERSION: ${{APP_VERSION:-{version}}}' in compose
    assert f'crawler_platform_web:${{PLATFORM_IMAGE_TAG:-{version}}}' in compose
    assert f'"version": "{version}"' in frontend_package
    assert f'"version": "{version}"' in frontend_lock
