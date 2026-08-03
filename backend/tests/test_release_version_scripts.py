from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1].parent


def test_release_version_scripts_do_not_require_host_python_or_npm() -> None:
    for relative in [
        'deploy/scripts/resolve-release-version.sh',
        'deploy/scripts/sync-runtime-version.sh',
        'deploy/scripts/check-version-consistency.sh',
        'deploy/scripts/release-upgrade.sh',
    ]:
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert 'npm ' not in source
        assert 'python3 ' not in source
        assert 'jq ' not in source


def test_health_exposes_release_metadata() -> None:
    source = (ROOT / 'backend/app/main.py').read_text(encoding='utf-8')
    for field in ['gitCommit', 'buildTime', 'migrationVersion']:
        assert field in source
    assert 'SELECT *' not in source.upper()


def test_resolve_release_version_priority_is_documented_in_script() -> None:
    source = (ROOT / 'deploy/scripts/resolve-release-version.sh').read_text(encoding='utf-8')
    assert 'git tag --points-at HEAD' in source
    assert 'git log -1 --pretty=%s' in source
    assert 'VERSION' in source
    assert re.search(r'[0-9]\\+\\\\\\.[0-9]\\+\\\\\\.[0-9]\\+', source) or '([0-9]+\\.[0-9]+\\.[0-9]+)' in source
