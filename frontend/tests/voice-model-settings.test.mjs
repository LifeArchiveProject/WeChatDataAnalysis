import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const useApiSource = await readFile(new URL('../composables/useApi.js', import.meta.url), 'utf8')
const settingsSource = await readFile(new URL('../components/SettingsDialog.vue', import.meta.url), 'utf8')
const voiceSectionStart = settingsSource.indexOf('<section ref="voiceSectionRef">')
const voiceSectionEnd = settingsSource.indexOf('<section ref="mcpSectionRef">', voiceSectionStart)
const voiceSectionSource = settingsSource.slice(voiceSectionStart, voiceSectionEnd)

test('voice model API exposes selection, download polling, and deletion contracts', () => {
  assert.match(useApiSource, /const setVoiceTranscriptionModel = async \(model\)/)
  assert.match(useApiSource, /models\/\$\{modelId\}\/download/)
  assert.match(useApiSource, /models\/downloads\/\$\{id\}/)
  assert.match(useApiSource, /method: 'DELETE'/)
  for (const method of [
    'setVoiceTranscriptionModel',
    'downloadVoiceTranscriptionModel',
    'getVoiceTranscriptionModelDownload',
    'deleteVoiceTranscriptionModel',
  ]) {
    assert.match(useApiSource, new RegExp(`\\n\\s+${method},`))
  }
})

test('settings renders model cards and keeps active downloads observable', () => {
  assert.match(settingsSource, /v-for="model in voiceModels"/)
  assert.match(settingsSource, /@click="selectVoiceModel\(model\)"/)
  assert.match(settingsSource, /@click="startVoiceModelDownload\(model\)"/)
  assert.match(settingsSource, /@click="removeVoiceModel\(model\)"/)
  assert.match(settingsSource, /v-if="canDeleteVoiceModel\(model\)"/)
  assert.match(settingsSource, /共享缓存可直接使用，但不会由本应用删除/)
  assert.match(settingsSource, /api\.getVoiceTranscriptionModelDownload\(model\.downloadJobId\)/)
  assert.match(settingsSource, /clearVoiceModelDownloadPolling\(\)/)
})

test('download-time deletion stays available and supersedes stale download work', () => {
  assert.match(voiceSectionSource, /v-if="canDeleteVoiceModel\(model\)"/)
  assert.match(voiceSectionSource, /:disabled="isVoiceModelDeletePending\(model\.id\)"/)
  assert.match(voiceSectionSource, /v-if="!model\.downloaded && !isVoiceModelDeletePending\(model\.id\)"/)
  assert.match(voiceSectionSource, /停止并删除/)

  const deleteButtonStart = voiceSectionSource.indexOf('v-if="canDeleteVoiceModel(model)"')
  const deleteButtonEnd = voiceSectionSource.indexOf('</button>', deleteButtonStart)
  const deleteButtonSource = voiceSectionSource.slice(deleteButtonStart, deleteButtonEnd)
  assert.ok(deleteButtonStart >= 0 && deleteButtonEnd > deleteButtonStart)
  assert.doesNotMatch(deleteButtonSource, /:disabled="isVoiceModelActionBusy/)

  const canDeleteStart = settingsSource.indexOf('const canDeleteVoiceModel')
  const canDeleteEnd = settingsSource.indexOf('const applyVoiceTranscriptionStatus', canDeleteStart)
  const canDeleteSource = settingsSource.slice(canDeleteStart, canDeleteEnd)
  assert.match(canDeleteSource, /isVoiceModelDownloading\(model\)/)
  assert.match(canDeleteSource, /isVoiceModelActionBusy\(model\.id, 'download'\)/)

  const removeStart = settingsSource.indexOf('const removeVoiceModel')
  const removeEnd = settingsSource.indexOf('const refreshVoiceTranscriptionStatus', removeStart)
  const removeSource = settingsSource.slice(removeStart, removeEnd)
  const invalidateIndex = removeSource.indexOf('invalidateVoiceModelDownload(model.id)')
  const clearPollingIndex = removeSource.indexOf('clearVoiceModelDownloadPolling()')
  const clearStateIndex = removeSource.indexOf('clearVoiceModelDownloadState(model.id)')
  const awaitStartIndex = removeSource.indexOf('await pendingStart')
  const deleteRequestIndex = removeSource.indexOf('api.deleteVoiceTranscriptionModel(model.id)')
  assert.ok(invalidateIndex >= 0)
  assert.ok(clearPollingIndex > invalidateIndex)
  assert.ok(clearStateIndex > clearPollingIndex)
  assert.ok(awaitStartIndex > clearStateIndex)
  assert.ok(deleteRequestIndex > awaitStartIndex)

  assert.match(settingsSource, /voiceModelDownloadStartPromises\.set\(model\.id, startRequest\)/)
  assert.match(settingsSource, /voiceModelDownloadStartPromises\.delete\(model\.id\)/)
  assert.match(settingsSource, /generation !== voiceModelDownloadGeneration\(model\.id\) \|\| isVoiceModelDeletePending\(model\.id\)/)
  assert.match(settingsSource, /&& !isVoiceModelDeletePending\(model\.id\)/)
})

test('settings shows inference device before the model catalog', () => {
  assert.ok(voiceSectionStart >= 0 && voiceSectionEnd > voiceSectionStart)
  assert.ok(voiceSectionSource.indexOf('>推理设备<') < voiceSectionSource.indexOf('>Whisper 模型<'))
})

test('settings keeps device and model selection feedback compact', () => {
  assert.match(settingsSource, /const voiceCudaDeviceLabels = computed/)
  assert.match(settingsSource, /实际：\{\{ voiceActiveDeviceLabel \}\}/)
  assert.doesNotMatch(voiceSectionSource, /已检测到 NVIDIA GPU/)
  assert.doesNotMatch(settingsSource, /下一次语音识别会尝试 CUDA/)
  assert.doesNotMatch(settingsSource, /后续语音识别将使用该模型/)
  assert.doesNotMatch(settingsSource, /return '尚未加载'/)
})

test('voice model cards use app theme tokens and determinate download progress', () => {
  assert.match(voiceSectionSource, /bg-\[var\(--app-accent\)\]/)
  assert.match(voiceSectionSource, /hover:bg-\[var\(--app-accent-hover\)\]/)
  assert.match(voiceSectionSource, /text-\[var\(--app-text-muted\)\]/)
  assert.match(voiceSectionSource, /text-\[var\(--danger-color\)\]/)
  assert.doesNotMatch(voiceSectionSource, /animate-pulse|bg-\[#222\]|hover:bg-black/)

  assert.match(voiceSectionSource, /role="progressbar"/)
  assert.match(voiceSectionSource, /:aria-label="`\$\{model\.name\} 模型下载进度`"/)
  assert.match(voiceSectionSource, /:aria-valuenow="voiceModelDownloadPercent\(model\)"/)
  assert.match(voiceSectionSource, /:aria-valuetext="voiceModelDownloadProgressText\(model\)"/)
  assert.match(voiceSectionSource, /width: `\$\{voiceModelDownloadPercent\(model\)\}%`/)
  assert.match(voiceSectionSource, /voiceModelDownloadProgressText\(model\)/)
  assert.match(voiceSectionSource, /voiceModelDownloadButtonText\(model\)/)

  for (const field of ['downloadPercent', 'downloadedBytes', 'totalBytes', 'downloadStage']) {
    assert.match(settingsSource, new RegExp(`${field}:`))
  }
  for (const field of ['job?.percent', 'job?.downloadedBytes', 'job?.totalBytes', 'job?.stage']) {
    assert.ok(settingsSource.includes(field))
  }
})

test('poll responses continuously feed transfer bytes and cancelled jobs become inactive', () => {
  const progressTextStart = settingsSource.indexOf('const voiceModelDownloadProgressText')
  const progressTextEnd = settingsSource.indexOf('const voiceModelDownloadButtonText', progressTextStart)
  const progressTextSource = settingsSource.slice(progressTextStart, progressTextEnd)
  assert.match(progressTextSource, /model\?\.downloadedBytes/)
  assert.match(progressTextSource, /model\?\.totalBytes/)
  assert.match(progressTextSource, /formatBytes\(downloadedBytes\)/)

  const updateStart = settingsSource.indexOf('const updateVoiceModelDownload')
  const updateEnd = settingsSource.indexOf('const clearVoiceModelDownloadState', updateStart)
  const updateSource = settingsSource.slice(updateStart, updateEnd)
  assert.match(updateSource, /downloadedBytes: normalizeVoiceModelDownloadBytes\(job\?\.downloadedBytes\)/)
  assert.match(updateSource, /totalBytes: normalizeVoiceModelDownloadBytes\(job\?\.totalBytes\)/)
  assert.match(updateSource, /const active = \['queued', 'running'\]\.includes\(status\)/)

  assert.match(settingsSource, /const isVoiceModelDownloading = \(model\) => \['queued', 'running'\]\.includes/)
  assert.match(settingsSource, /downloadJobId: active \?[^:]+: ''/s)
  assert.match(settingsSource, /updateVoiceModelDownload\(model\.id, job\)/)
})

test('voice settings controls stay within narrow layouts', () => {
  assert.match(settingsSource, /<aside class="hidden[^\"]*sm:flex"/)
  assert.match(voiceSectionSource, /w-full[^\"]*sm:w-auto" role="radiogroup"/)
  assert.match(voiceSectionSource, /flex-1[^\"]*sm:flex-none/)
  assert.match(voiceSectionSource, /flex flex-wrap items-center justify-end/)
  assert.match(voiceSectionSource, /voice-setting-focus/)
  assert.match(settingsSource, /\.voice-setting-focus:focus-visible\s*\{[^}]*var\(--app-accent\)/s)
})

test('settings derives model state from current files and retires stale download jobs', () => {
  assert.match(settingsSource, /\(!downloaded && downloadStatus === 'done'\)/)
  assert.match(settingsSource, /\(downloaded && downloadStatus === 'error'\)/)
  assert.match(settingsSource, /downloadJobId: \['queued', 'running'\]\.includes\(downloadStatus\)/)
  assert.match(settingsSource, /updateVoiceModelDownload\(model\.id, \{ status: 'error', error: message \}\)/)

  const stateTextStart = settingsSource.indexOf('const voiceModelStateText')
  const downloadedCheck = settingsSource.indexOf('if (model?.downloaded)', stateTextStart)
  const errorCheck = settingsSource.indexOf("if (status === 'error')", stateTextStart)
  assert.ok(stateTextStart >= 0 && downloadedCheck > stateTextStart && errorCheck > downloadedCheck)
})

test('chat model-management link focuses the voice settings section', () => {
  assert.match(settingsSource, /if \(focusTarget === 'voice'\)/)
  assert.match(settingsSource, /scrollToSection\('voice'\)/)
})
