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
    assert len(back_button_tags) == 5
    assert all(':disabled=' not in tag for tag in back_button_tags)
    assert source.count('@click="goBackFromCurrentStep"') == 5
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
    assert "cancelVoiceOnboardingBatch()" in source
    assert "await navigateTo('/detection-result')" in source
    assert "currentStep.value = Math.max(0, fromStep - 1)" in source


def test_closed_database_stream_and_key_request_cannot_apply_late_results():
    source = read_decrypt_page()

    assert source.count("if (dbDecryptEventSource !== eventSource) return") >= 2
    assert "const requestController = new AbortController()" in source
    assert "isDbKeyRequestActive(requestRevision, requestController)" in source
    assert "signal: requestController.signal" in source


def test_voice_onboarding_preserves_download_errors_and_locks_model_actions():
    source = read_decrypt_page()

    assert "refreshVoiceOnboarding({ preserveError: !!downloadError })" in source
    assert "if (!preserveError) voiceOnboardingError.value = ''" in source
    assert ':disabled="voiceOnboardingModelDisabled(model)"' in source
    assert "voiceBatchRunning.value" in source
    assert "model?.downloadable === false" in source
    assert "voiceOnboardingModelLocked.value && !model?.selected" in source
    assert "voiceOnboardingModelDisabled(model)) return" in source


def test_voice_onboarding_restores_and_renders_real_model_download_progress():
    source = read_decrypt_page()

    assert 'data-testid="voice-onboarding-model-progress"' in source
    assert "model?.downloadedBytes" in source
    assert "model?.totalBytes" in source
    assert "model?.downloadStage" in source
    assert "voiceModelDownloadProgressText(model)" in source
    assert "voiceModelDownloadPercent(model)" in source
    assert ':aria-valuetext="voiceModelDownloadProgressText(model)"' in source
    assert "getVoiceTranscriptionModelDownload(model.downloadJobId)" in source
    assert "scheduleVoiceModelPoll()" in source
    assert "if (stage === 'cancelling') return '正在停止'" in source
    assert "await refreshVoiceOnboarding({ preserveError: true })" in source
    assert "bg-[var(--app-accent)]" in source
    assert "bg-[var(--app-surface-muted)]" in source


def test_voice_onboarding_delete_supersedes_stale_start_and_poll_results():
    source = read_decrypt_page()

    assert "deleteVoiceTranscriptionModel," in source
    assert '@click="removeVoiceOnboardingModel(model)"' in source
    assert ':disabled="isVoiceModelDeleting(model)"' in source
    assert "voiceModelDownloadGenerations" in source
    assert "voiceModelDownloadStartPromises" in source
    assert "voiceOnboardingRefreshRevision" in source
    assert "invalidateVoiceModelDownload(model.id)" in source
    assert "isVoiceModelDeletePending(model.id)" in source
    assert "generation !== voiceModelDownloadGeneration(model.id)" in source
    assert "const pendingStart = voiceModelDownloadStartPromises.get(model.id)" in source
    assert "await pendingStart" in source
    assert "await deleteVoiceTranscriptionModel(model.id)" in source
    assert "clearVoiceOnboardingModelDownloadState(model.id)" in source
    assert "voiceModelBusy.value =" not in source

    remove_block = source[source.index("const removeVoiceOnboardingModel = async"):source.index("const startVoiceOnboardingBatch = async")]
    assert remove_block.index("const pendingStart = voiceModelDownloadStartPromises.get(model.id)") < remove_block.index("await pendingStart")
    assert remove_block.index("await pendingStart") < remove_block.index("await deleteVoiceTranscriptionModel(model.id)")


def test_voice_onboarding_orders_poll_and_refresh_observations_per_model():
    source = read_decrypt_page()

    assert "const voiceModelObservationEpochs = new Map()" in source
    assert "const invalidateVoiceModelObservation = (modelId) =>" in source
    assert "const observationEpochs = beginVoiceModelRefreshObservations()" in source
    assert "applyVoiceOnboardingStatus(status, { observationEpochs })" in source
    assert "expectedObservationEpoch !== voiceModelObservationEpoch(id)" in source

    poll_block = source[source.index("const pollVoiceModelDownload = async"):source.index("const prepareVoiceOnboardingModel = async")]
    assert poll_block.index("const observationEpoch = invalidateVoiceModelObservation(model.id)") < poll_block.index("await getVoiceTranscriptionModelDownload(model.downloadJobId)")
    assert poll_block.index("observationEpoch !== voiceModelObservationEpoch(model.id)") < poll_block.index("updateVoiceOnboardingModelDownload(model.id, job)")

    prepare_block = source[source.index("const prepareVoiceOnboardingModel = async"):source.index("const removeVoiceOnboardingModel = async")]
    assert prepare_block.count("voiceOnboardingRefreshRevision += 1") == 2
    assert prepare_block.count("voiceOnboardingLoading.value = false") == 2
    assert prepare_block.index("voiceOnboardingRefreshRevision += 1") < prepare_block.index("applyVoiceOnboardingStatus(response?.configuration || response)")


def test_voice_onboarding_treats_server_cancelling_as_delete_in_progress():
    source = read_decrypt_page()

    assert "const isVoiceModelServerDeleting = (model)" in source
    assert "=== 'cancelling'" in source
    assert "const isVoiceModelDeleting = (model)" in source
    assert 'v-if="!model.downloaded && !isVoiceModelDeleting(model)"' in source
    assert ':disabled="isVoiceModelDeleting(model)"' in source
    assert "|| isVoiceModelDeleting(model)" in source
    assert "|| isVoiceModelDeleting(model)\n  ) return" in source

    schedule_block = source[source.index("function scheduleVoiceModelPoll()"):source.index("const clearVoiceBatchPoll = () =>")]
    assert "isVoiceModelDownloading(item)" in schedule_block
    assert "!isVoiceModelDeletePending(item.id)" in schedule_block
    assert "!isVoiceModelDeleting(item)" not in schedule_block


def test_voice_onboarding_unmount_invalidates_async_continuations_and_timers():
    source = read_decrypt_page()

    assert "let voiceOnboardingLifecycleEpoch = 0" in source
    assert "let voiceOnboardingDisposed = false" in source
    assert "const isVoiceOnboardingLifecycleActive = (epoch) =>" in source
    assert "if (voiceOnboardingDisposed || voiceModelPollTimer || currentStep.value !== 4) return" in source

    unmount_block = source[source.index("onBeforeUnmount(() => {"):source.index("const resetDbDecryptProgress = () =>")]
    assert "voiceOnboardingDisposed = true" in unmount_block
    assert "voiceOnboardingLifecycleEpoch += 1" in unmount_block
    assert "voiceOnboardingRefreshRevision += 1" in unmount_block
    assert "invalidateVoiceModelDownload(modelId)" in unmount_block
    assert "invalidateVoiceModelObservation(modelId)" in unmount_block
    assert unmount_block.index("voiceOnboardingDisposed = true") < unmount_block.index("clearVoiceModelPoll()")

    refresh_block = source[source.index("const refreshVoiceOnboarding = async"):source.index("const pollVoiceModelDownload = async")]
    assert refresh_block.count("isVoiceOnboardingLifecycleActive(lifecycleEpoch)") >= 4
    assert "refreshRevision !== voiceOnboardingRefreshRevision" in refresh_block


def test_voice_onboarding_selected_model_is_explicit_and_accessible():
    source = read_decrypt_page()

    assert ':aria-current="model.selected ? \'true\' : undefined"' in source
    assert 'v-if="model.selected"' in source
    assert ">已选择</span>" in source


def test_voice_onboarding_can_select_cpu_or_available_cuda():
    source = read_decrypt_page()

    assert "setVoiceTranscriptionDevice," in source
    assert 'data-testid="voice-onboarding-device-cpu"' in source
    assert 'data-testid="voice-onboarding-device-cuda"' in source
    assert "@click=\"setVoiceOnboardingDevice('cpu')\"" in source
    assert "@click=\"setVoiceOnboardingDevice('cuda')\"" in source
    assert "voiceOnboardingStatus.value?.cuda?.available === true" in source
    assert "voiceOnboardingStatus.value?.deviceSource || '') === 'env'" in source
    assert "await setVoiceTranscriptionDevice(next)" in source
    assert "applyVoiceOnboardingStatus(response?.configuration || response)" in source


def test_five_step_header_stays_within_narrow_viewports():
    source = (ROOT / "frontend" / "components" / "Stepper.vue").read_text(encoding="utf-8")

    assert "hidden whitespace-nowrap text-[13px] transition-colors duration-200 sm:block" in source
    assert "mx-1.5 h-px flex-1 transition-colors duration-200 sm:mx-3" in source
    assert ':aria-label="`${index + 1}. ${step.title}`"' in source
