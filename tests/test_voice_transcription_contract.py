from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestVoiceTranscriptionContract(unittest.TestCase):
    def test_chat_api_exposes_status_and_transcription_endpoints(self):
        source = (ROOT / "src" / "wechat_decrypt_tool" / "routers" / "chat_media.py").read_text(encoding="utf-8")
        self.assertIn('/api/chat/media/voice/transcription/status', source)
        self.assertIn('/api/chat/media/voice/transcription', source)
        self.assertIn('/api/chat/media/voice/transcription/settings', source)
        self.assertIn('set_voice_transcription_device', source)
        self.assertIn('await asyncio.to_thread(', source)

    def test_settings_ui_exposes_cpu_and_nvidia_gpu_selection(self):
        settings = (ROOT / "frontend" / "components" / "SettingsDialog.vue").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")
        self.assertIn("语音转文字", settings)
        self.assertIn("NVIDIA GPU", settings)
        self.assertIn("setVoiceTranscriptionDevice", settings)
        self.assertIn("voiceFallbackReason", settings)
        self.assertIn("/chat/media/voice/transcription/settings", api)

    def test_chat_ui_keeps_audio_and_adds_transcription_states(self):
        content = (ROOT / "frontend" / "components" / "chat" / "MessageContent.vue").read_text(encoding="utf-8")
        messages = (ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js").read_text(encoding="utf-8")
        self.assertIn(':src="message.voiceUrl"', content)
        self.assertIn("message.voiceTranscriptStatus === 'loading'", content)
        self.assertIn("message.voiceTranscriptStatus === 'success'", content)
        self.assertIn("transcribeVoice(message)", content)
        self.assertNotIn("transcribeVoice(message, { force: true })", content)
        self.assertIn("const transcribeVoice = async", messages)
        self.assertIn("api.triggerNativeVoiceTranscription", messages)

    def test_export_option_is_wired_from_dialog_to_backend(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")
        export_state = (ROOT / "frontend" / "composables" / "chat" / "useChatExport.js").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")
        router = (ROOT / "src" / "wechat_decrypt_tool" / "routers" / "chat_export.py").read_text(encoding="utf-8")
        service = (ROOT / "src" / "wechat_decrypt_tool" / "chat_export_service.py").read_text(encoding="utf-8")

        self.assertIn('v-model="exportTranscribeVoice"', dialog)
        self.assertIn("selectedTypeSet.has('voice')", export_state)
        self.assertIn("transcribe_voice:", export_state)
        self.assertIn("transcribe_voice: !!data.transcribe_voice", api)
        self.assertIn("transcribe_voice: bool = Field(False", router)
        self.assertGreaterEqual(service.count("_attach_voice_transcript("), 4)
        self.assertIn('"transcribeVoice": transcribe_voice', service)

    def test_privacy_mode_disables_export_transcription(self):
        service = (ROOT / "src" / "wechat_decrypt_tool" / "chat_export_service.py").read_text(encoding="utf-8")
        export_state = (ROOT / "frontend" / "composables" / "chat" / "useChatExport.js").read_text(encoding="utf-8")
        self.assertIn('bool(opts.get("transcribeVoice")) and not privacy_mode', service)
        self.assertIn("!privacyMode.value", export_state)

    def test_desktop_backend_build_includes_optional_runtime(self):
        package = (ROOT / "desktop" / "package.json").read_text(encoding="utf-8")
        build = (ROOT / "desktop" / "scripts" / "build-backend.cjs").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("--no-editable --extra build --extra voice-transcription", package)
        self.assertIn('"faster_whisper"', build)
        self.assertIn('"ctranslate2"', build)
        self.assertIn('"av"', build)
        self.assertIn('"opencc"', build)
        self.assertIn('const os = require("os");', build)
        self.assertIn('"--smoke-opencc"', build)
        self.assertNotIn("windowsNativeCandidates", build)
        self.assertIn("buildIntegrityNativeBinary()", build)
        self.assertIn("runIntegrityPreflight(process.env, integrityNativeBinary)", build)
        self.assertIn('spawnSync("uv", args', build)
        self.assertIn("runPackagedOpenccSmoke(packagedBackend)", build)


if __name__ == "__main__":
    unittest.main()
