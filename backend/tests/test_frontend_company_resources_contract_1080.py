from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANY_RESOURCES_PAGE = ROOT / 'frontend' / 'src' / 'views' / 'CompanyResourcesPage.vue'


def test_company_resources_page_defines_test_status_options_used_by_template() -> None:
    text = COMPANY_RESOURCES_PAGE.read_text(encoding='utf-8')
    assert 'v-for="item in testStatusOptions"' in text
    assert 'const testStatusOptions: Option[] = [' in text
    for status in [
        'NOT_TESTED',
        'CONFIG_INVALID',
        'CONFIG_VALID',
        'CONNECTION_FAILED',
        'CONNECTION_PASSED',
        'MANUAL_CONFIRMED',
    ]:
        assert status in text
