from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_decrypt_page() -> str:
    return (ROOT / "frontend" / "pages" / "decrypt.vue").read_text(encoding="utf-8")


def read_use_api() -> str:
    return (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")


def test_auto_fetch_only_skips_a_complete_valid_image_key_pair():
    source = read_decrypt_page()

    assert "const existingKeys = normalizeCompleteImageKeys(manualKeys.xor_key, manualKeys.aes_key)" in source
    assert "if (imageKeyInputOrigin.value === 'manual')" in source
    assert "if (existingKeys.ok && imageKeysVerified.value)" in source
    assert "imageKeysVerified.value = keys.image_key_verified === true" in source
    assert "String(manualKeys.xor_key || '').trim() || String(manualKeys.aes_key || '').trim()" not in source
    assert "ok: xor.ok && aes.ok && !!aes.value" in source


def test_auto_fetch_validates_and_assigns_the_complete_response_atomically():
    source = read_decrypt_page()

    assert "const fetchedKeys = normalizeCompleteImageKeys(" in source
    assert "imgRes?.data?.verified === true && fetchedKeys.ok" in source
    assert "manualKeys.xor_key = fetchedKeys.xor.value" in source
    assert "manualKeys.aes_key = fetchedKeys.aes.value" in source
    assert "if (imgRes.data?.xor_key) manualKeys.xor_key" not in source
    assert "if (imgRes.data?.aes_key) manualKeys.aes_key" not in source


def test_auto_fetch_reports_local_parsing_outcomes():
    source = read_decrypt_page()

    assert "正在自动解析并校验图片密钥" in source
    assert "已通过本地解析成功获取图片密钥" in source
    assert "本地解析图片密钥失败" in source
    assert "云端获取图片密钥失败" not in source
    assert "网络请求失败，请手动填写图片密钥" not in source


def test_complete_manual_image_keys_are_not_overwritten_by_auto_fetch():
    source = read_decrypt_page()

    assert source.count('@input="markImageKeysManual"') == 2
    assert "const imageKeyInputOrigin = ref('empty')" in source
    assert "imageKeyInputOrigin.value = 'manual'" in source
    assert "imageKeyInputOrigin.value = 'prefill'" in source
    assert "imageKeyInputOrigin.value = 'auto'" in source
    assert "invalidateImageKeyRequests()" in source
    assert "if (!isCurrentImageKeyRequest(context) || imageKeyInputOrigin.value === 'manual')" in source
    assert "if (imageKeyInputOrigin.value !== 'manual')" in source


def test_prefill_applies_cached_image_keys_as_one_record_after_await():
    source = read_decrypt_page()

    assert "const cachedPair = normalizeCompleteImageKeys(xorKey, aesKey)" in source
    assert "manualKeys.xor_key = cachedPair.xor.value" in source
    assert "manualKeys.aes_key = cachedPair.aes.value" in source
    assert "manualKeys.xor_key = cachedXor.ok ? cachedXor.value : ''" in source
    assert "manualKeys.aes_key = cachedAes.ok ? cachedAes.value : ''" in source
    assert "!String(manualKeys.xor_key || '').trim()" not in source


def test_verified_image_keys_are_not_downgraded_by_legacy_save_calls():
    source = read_decrypt_page()

    assert source.count("mediaKeys.xor_key && !imageKeysVerified.value") == 2
    assert "media-step:skip-save-verified" in source
    assert "skip-chat:skip-save-verified" in source


def test_memory_scan_button_has_explicit_progress_and_result_states():
    source = read_decrypt_page()

    assert '@click="scanImageKeyMemory"' in source
    assert ':disabled="isImageKeyAcquisitionPending"' in source
    assert "扫描微信内存" in source
    assert "正在扫描微信进程内存" in source
    assert "内存扫描完成，图片密钥已通过本地图片校验" in source
    assert "内存扫描未找到可验证的图片密钥" in source


def test_memory_scan_only_applies_a_complete_verified_pair():
    source = read_decrypt_page()

    assert "const scannedKeys = normalizeCompleteImageKeys(" in source
    assert "response?.data?.verified === true && scannedKeys.ok" in source
    assert "manualKeys.xor_key = scannedKeys.xor.value" in source
    assert "manualKeys.aes_key = scannedKeys.aes.value" in source
    assert "imageKeysVerified.value = true" in source
    assert "imageKeyInputOrigin.value = 'memory'" in source


def test_image_key_requests_reject_stale_or_cross_account_responses():
    source = read_decrypt_page()

    assert "const imageKeyPendingCount = ref(0)" in source
    assert "let imageKeyRequestRevision = 0" in source
    assert "const isCurrentImageKeyRequest = (context)" in source
    assert "/^(wxid_[^_\\s]+)_[0-9a-f]{4}$/i" in source
    assert "imageKeyResponseMatchesContext(response?.data?.account, context)" in source
    assert "imageKeyResponseMatchesContext(imgRes?.data?.account, context)" in source
    assert "image-memory-scan:stale-response" in source
    assert "auto-fetch:stale-response" in source
    assert source.count("if (isImageKeyAcquisitionPending.value) return") >= 3


def test_old_account_prefill_cannot_start_a_new_auto_fetch_after_account_switch():
    source = read_decrypt_page()

    assert "let ensureKeysRevision = 0" in source
    assert "const ensureRevision = ++ensureKeysRevision" in source
    assert "const ensureContext = { account: acc, dbStoragePath:" in source
    assert "ensureRevision !== ensureKeysRevision || activeKeyAccount.value !== acc" in source
    assert "activeKeyAccount.value !== acc || !imageKeyContextStillSelected(ensureContext)" in source
    assert "ensure-keys:stale-after-prefill" in source
    stale_guard = source.index("ensure-keys:stale-after-prefill")
    auto_fetch = source.index("await tryAutoFetchImageKeys(acc)", stale_guard)
    assert stale_guard < auto_fetch


def test_memory_scan_api_uses_post_with_account_and_source_paths():
    source = read_use_api()

    assert "const getImageKeyMemory = async (params = {})" in source
    assert "request('/get_image_key_memory'" in source
    assert "method: 'POST'" in source
    assert "db_storage_path: params.db_storage_path || null" in source
    assert "wxid_dir: params.wxid_dir || null" in source
    assert "getImageKeyMemory," in source
