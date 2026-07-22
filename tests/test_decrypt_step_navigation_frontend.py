import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_decrypt_page() -> str:
    return (ROOT / "frontend" / "pages" / "decrypt.vue").read_text(encoding="utf-8")


def test_every_decrypt_step_has_an_available_back_button():
    source = read_decrypt_page()

    back_button_tags = re.findall(
        r'<button\b(?=[^>]*data-testid="decrypt-step-back")[^>]*>',
        source,
        flags=re.DOTALL,
    )
    assert len(back_button_tags) == 4
    assert all(':disabled=' not in tag for tag in back_button_tags)
    assert source.count('@click="goBackFromCurrentStep"') == 4
    assert "返回账号选择" in source
    assert source.count("上一步") >= 3


def test_back_navigation_cancels_active_streams_before_leaving_the_step():
    source = read_decrypt_page()

    assert "const goBackFromCurrentStep = async () =>" in source
    assert "await confirmBackFromRunningStep()" in source
    assert "closeDbDecryptEventSource()" in source
    assert "cancelDbKeyAcquisition()" in source
    assert "invalidateImageKeyRequests()" in source
    assert "isGettingDbKey.value" in source
    assert "cancelMediaDecrypt()" in source
    assert "cancelEmojiDownload()" in source
    assert "await navigateTo('/detection-result')" in source
    assert "currentStep.value = Math.max(0, fromStep - 1)" in source


def test_closed_database_stream_and_key_request_cannot_apply_late_results():
    source = read_decrypt_page()

    assert source.count("if (dbDecryptEventSource !== eventSource) return") >= 2
    assert "const requestController = new AbortController()" in source
    assert "isDbKeyRequestActive(requestRevision, requestController)" in source
    assert "signal: requestController.signal" in source
