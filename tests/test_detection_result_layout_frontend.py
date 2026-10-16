from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_detection_summary_uses_roomy_desktop_layout():
    source = (ROOT / "frontend" / "pages" / "detection-result.vue").read_text(encoding="utf-8")

    assert 'lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]' in source
    assert 'data-testid="detection-summary"' in source
    assert 'sm:grid-cols-3 lg:grid-cols-2' in source
    assert 'lg:col-span-2' in source
    assert 'data-testid="wechat-version-value"' in source
    assert 'data-testid="wechat-version-value" class="mt-1.5 truncate' not in source
    assert source.count('whitespace-nowrap text-[12px] font-medium text-[#5F6F66]') >= 3
