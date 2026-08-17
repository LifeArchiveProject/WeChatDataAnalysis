from __future__ import annotations

import io
import logging
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.voice_transcription import (  # noqa: E402
    VoiceTranscriptionBatchManager,
    VoiceTranscriptionConfig,
    VoiceTranscriptionError,
    VoiceModelDownloadManager,
    VoiceTranscriptionService,
    _download_voice_model_snapshot,
    _list_realtime_native_voice_transcripts,
    acquire_voice_model_activity,
    delete_voice_model,
    get_legacy_voice_model_storage_root,
    get_voice_model_catalog,
    get_voice_model_storage_root,
    inspect_model_readiness,
    list_native_voice_transcripts,
    list_voice_server_ids,
    release_voice_model_activity,
    resolve_voice_transcription_batch_concurrency,
    set_voice_transcription_model,
)
import wechat_decrypt_tool.voice_transcription as voice_transcription_module  # noqa: E402


def _seed_voice_db(path: Path, rows: list[tuple[int, int, bytes]]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE VoiceInfo (svr_id INTEGER, create_time INTEGER, voice_data BLOB)")
        conn.executemany("INSERT INTO VoiceInfo VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


class TestVoiceModelCatalog(unittest.TestCase):
    def test_catalog_lists_multilingual_models_and_local_readiness(self):
        with patch(
            "wechat_decrypt_tool.voice_transcription.inspect_model_readiness",
            side_effect=lambda model: {
                "ready": model in {"small", "medium"},
                "downloadable": True,
                "source": "huggingface-cache",
                "reason": "",
            },
        ):
            models = get_voice_model_catalog(selected_model="medium")

        self.assertEqual([item["id"] for item in models], ["tiny", "base", "small", "medium", "large-v3", "turbo"])
        selected = next(item for item in models if item["id"] == "medium")
        self.assertTrue(selected["selected"])
        self.assertTrue(selected["downloaded"])
        self.assertTrue(all(not item["id"].endswith(".en") for item in models))

    def test_catalog_exposes_latest_download_progress(self):
        job = {
            "jobId": "model-small-test",
            "status": "running",
            "percent": 37,
            "downloadedBytes": 370,
            "totalBytes": 1000,
            "stage": "downloading",
            "error": "",
        }
        with (
            patch(
                "wechat_decrypt_tool.voice_transcription.inspect_model_readiness",
                return_value={"ready": False, "downloadable": True},
            ),
            patch(
                "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER.latest_by_model",
                return_value={"small": job},
            ),
        ):
            model = next(item for item in get_voice_model_catalog() if item["id"] == "small")

        self.assertEqual(model["downloadPercent"], 37)
        self.assertEqual(model["downloadedBytes"], 370)
        self.assertEqual(model["totalBytes"], 1000)
        self.assertEqual(model["downloadStage"], "downloading")


class TestVoiceBatchManager(unittest.TestCase):
    def test_voice_ids_are_collected_from_all_decrypted_media_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            _seed_voice_db(account_dir / "media_0.db", [(3, 30, b"c"), (1, 10, b"a")])
            _seed_voice_db(account_dir / "media_1.db", [(2, 20, b"b"), (3, 31, b"new-c")])

            with patch("wechat_decrypt_tool.voice_transcription._list_realtime_voice_server_ids", return_value=[]):
                self.assertEqual(list_voice_server_ids(account_dir), [1, 2, 3])

    def test_batch_job_reports_cached_success_failure_and_completion(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small")
        service.transcribe_voice.side_effect = [
            {"cached": True, "text": "one"},
            {"cached": False, "text": "two"},
            RuntimeError("broken"),
        ]
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=[1, 2, 3],
        ):
            job = manager.start(account="wxid_demo", account_dir=Path(tmp))
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["total"], 3)
        self.assertEqual(job["completed"], 3)
        self.assertEqual(job["success"], 2)
        self.assertEqual(job["cached"], 1)
        self.assertEqual(job["failed"], 1)
        self.assertEqual(job["percent"], 100)

    def test_only_one_account_batch_can_run_at_a_time(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small")
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)

        entered = threading.Event()
        release = threading.Event()

        def blocked_scan(*_args, **_kwargs):
            entered.set()
            release.wait(2)
            return []

        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            side_effect=blocked_scan,
        ):
            first = manager.start(account="wxid_a", account_dir=Path(tmp) / "a")
            self.assertTrue(entered.wait(1))
            try:
                same = manager.start(account="wxid_a", account_dir=Path(tmp) / "a")
                self.assertEqual(same["jobId"], first["jobId"])
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    manager.start(account="wxid_b", account_dir=Path(tmp) / "b")
            finally:
                manager.cancel(first["jobId"])
                release.set()
                deadline = time.time() + 2
                while time.time() < deadline:
                    if manager.get(first["jobId"])["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

        self.assertEqual(raised.exception.code, "batch_busy")

    def test_forget_finished_clears_latest_pointer_but_keeps_job_history(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        manager._jobs["finished"] = {
            "jobId": "finished",
            "account": "wxid_finished",
            "status": "done",
        }
        manager._latest_by_account["wxid_finished"] = "finished"

        self.assertTrue(manager.forget_finished("wxid_finished"))
        self.assertIsNone(manager.latest("wxid_finished"))
        self.assertEqual(manager.get("finished")["status"], "done")

    def test_forget_finished_rejects_active_account(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        manager._jobs["active"] = {
            "jobId": "active",
            "account": "wxid_active",
            "status": "running",
        }
        manager._latest_by_account["wxid_active"] = "active"

        with self.assertRaises(VoiceTranscriptionError) as raised:
            manager.forget_finished("wxid_active")

        self.assertEqual(raised.exception.code, "batch_busy")
        self.assertEqual(manager.latest("wxid_active")["jobId"], "active")

    def test_delete_cache_if_idle_deletes_and_forgets_finished_job_atomically(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        manager._jobs["finished"] = {
            "jobId": "finished",
            "account": "wxid_finished",
            "status": "done",
        }
        manager._latest_by_account["wxid_finished"] = "finished"
        deleted = {
            "status": "success",
            "account": "wxid_finished",
            "deletedRows": 2,
            "deletedMessages": 1,
            "nativeDeleted": 0,
        }
        with patch(
            "wechat_decrypt_tool.voice_transcription.delete_voice_transcript_cache",
            return_value=deleted,
        ) as delete:
            result = manager.delete_cache_if_idle(
                account="wxid_finished",
                account_dir=Path("wxid_finished"),
            )

        self.assertEqual(result, deleted)
        delete.assert_called_once_with(Path("wxid_finished"))
        self.assertIsNone(manager.latest("wxid_finished"))

    def test_global_delete_rejects_any_active_batch_before_mutation(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        manager._jobs["active"] = {
            "jobId": "active",
            "account": "wxid_other",
            "status": "queued",
        }
        manager._latest_by_account["wxid_other"] = "active"
        with patch(
            "wechat_decrypt_tool.voice_transcription._delete_all_voice_transcript_caches_with_accounts"
        ) as delete:
            with self.assertRaises(VoiceTranscriptionError) as raised:
                manager.delete_all_caches_if_idle()

        self.assertEqual(raised.exception.code, "batch_busy")
        delete.assert_not_called()
        self.assertEqual(manager.latest("wxid_other")["jobId"], "active")

    def test_global_delete_clears_all_finished_latest_jobs(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        for account in ("wxid_first", "wxid_second"):
            job_id = f"finished-{account}"
            manager._jobs[job_id] = {
                "jobId": job_id,
                "account": account,
                "status": "done",
            }
            manager._latest_by_account[account] = job_id
        result = {
            "status": "success",
            "deletedRows": 3,
            "deletedMessages": 2,
            "accountsScanned": 2,
            "accountsChanged": 2,
            "nativeDeleted": 0,
        }
        with patch(
            "wechat_decrypt_tool.voice_transcription._delete_all_voice_transcript_caches_with_accounts",
            return_value=(result, ["wxid_first", "wxid_second"]),
        ) as delete:
            deleted = manager.delete_all_caches_if_idle()

        self.assertEqual(deleted, result)
        delete.assert_called_once_with()
        self.assertIsNone(manager.latest("wxid_first"))
        self.assertIsNone(manager.latest("wxid_second"))

    def test_partial_global_delete_keeps_failed_account_latest_job(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock())
        for account in ("wxid_good", "wxid_failed"):
            job_id = f"finished-{account}"
            manager._jobs[job_id] = {
                "jobId": job_id,
                "account": account,
                "status": "done",
            }
            manager._latest_by_account[account] = job_id
        result = {
            "status": "partial",
            "deletedRows": 1,
            "deletedMessages": 1,
            "accountsScanned": 2,
            "accountsChanged": 1,
            "nativeDeleted": 0,
            "failures": [{"account": "wxid_failed", "code": "cache_delete_failed"}],
        }
        with patch(
            "wechat_decrypt_tool.voice_transcription._delete_all_voice_transcript_caches_with_accounts",
            return_value=(result, ["wxid_good"]),
        ):
            deleted = manager.delete_all_caches_if_idle()

        self.assertEqual(deleted, result)
        self.assertIsNone(manager.latest("wxid_good"))
        self.assertEqual(manager.latest("wxid_failed")["status"], "done")

    def test_batch_concurrency_auto_and_explicit_values_are_resolved_without_fixed_cap(self):
        self.assertEqual(
            resolve_voice_transcription_batch_concurrency(
                None,
                VoiceTranscriptionConfig(model="small", device="cuda"),
            ),
            (0, 2),
        )
        self.assertEqual(
            resolve_voice_transcription_batch_concurrency(
                0,
                VoiceTranscriptionConfig(model="medium", device="cuda"),
            ),
            (0, 1),
        )
        self.assertEqual(
            resolve_voice_transcription_batch_concurrency(
                0,
                VoiceTranscriptionConfig(model="small", device="cpu"),
            ),
            (0, 1),
        )
        self.assertEqual(
            resolve_voice_transcription_batch_concurrency(
                99,
                VoiceTranscriptionConfig(model="small", device="cpu"),
            ),
            (99, 99),
        )

    def test_batch_concurrency_rejects_negative_or_non_integer_values(self):
        config = VoiceTranscriptionConfig(model="small", device="cpu")
        for concurrency in (-1, True, 1.5, "5"):
            with self.subTest(concurrency=concurrency):
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    resolve_voice_transcription_batch_concurrency(concurrency, config)
                self.assertEqual(raised.exception.code, "invalid_concurrency")

    def test_batch_concurrency_is_naturally_limited_by_work_item_count(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small", device="cpu")
        service.configure_inference_concurrency.return_value = 3
        service.transcribe_voice.return_value = {"cached": False, "text": "ok"}
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=[1, 2, 3],
        ), patch(
            "wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts",
            return_value={},
        ), patch(
            "wechat_decrypt_tool.voice_transcription.capture_voice_transcript_cache_generation",
            return_value=77,
        ):
            job = manager.start(account="wxid_large_request", account_dir=Path(tmp), concurrency=99)
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["requestedConcurrency"], 99)
        self.assertEqual(job["concurrency"], 3)
        service.configure_inference_concurrency.assert_called_once_with(3, cancel_event=ANY)

    def test_empty_batch_preserves_request_but_uses_no_workers(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small", device="cpu")
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=[],
        ), patch(
            "wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts",
            return_value={},
        ):
            job = manager.start(account="wxid_empty", account_dir=Path(tmp), concurrency=99)
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["requestedConcurrency"], 99)
        self.assertEqual(job["concurrency"], 0)
        service.configure_inference_concurrency.assert_not_called()

    def test_batch_runs_multiple_voice_transcriptions_in_parallel(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small", device="cpu")
        service.configure_inference_concurrency.return_value = 2
        state_lock = threading.Lock()
        both_entered = threading.Event()
        release = threading.Event()
        active = 0
        maximum_active = 0

        def transcribe(**_kwargs):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
                if active >= 2:
                    both_entered.set()
            try:
                release.wait(2)
                return {"cached": False, "text": "ok"}
            finally:
                with state_lock:
                    active -= 1

        service.transcribe_voice.side_effect = transcribe
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=[1, 2, 3],
        ), patch(
            "wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts",
            return_value={},
        ), patch(
            "wechat_decrypt_tool.voice_transcription.capture_voice_transcript_cache_generation",
            return_value=77,
        ):
            job = manager.start(account="wxid_parallel", account_dir=Path(tmp), concurrency=2)
            try:
                self.assertTrue(both_entered.wait(1), "two inference workers did not overlap")
            finally:
                release.set()
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["requestedConcurrency"], 2)
        self.assertEqual(job["concurrency"], 2)
        self.assertEqual(maximum_active, 2)
        self.assertEqual(job["completed"], 3)
        self.assertEqual(job["completed"], job["success"] + job["failed"])
        self.assertTrue(
            all(call.kwargs["cache_generation"] == 77 for call in service.transcribe_voice.call_args_list)
        )
        service.configure_inference_concurrency.assert_called_once_with(2, cancel_event=ANY)

    def test_batch_cancel_stops_dispatching_new_voice_items(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small", device="cpu")
        service.configure_inference_concurrency.return_value = 2
        entered_lock = threading.Lock()
        two_entered = threading.Event()
        release = threading.Event()
        entered = 0

        def transcribe(**_kwargs):
            nonlocal entered
            with entered_lock:
                entered += 1
                if entered >= 2:
                    two_entered.set()
            release.wait(2)
            return {"cached": False, "text": "ok"}

        service.transcribe_voice.side_effect = transcribe
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=list(range(1, 9)),
        ), patch(
            "wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts",
            return_value={},
        ):
            job = manager.start(account="wxid_cancel", account_dir=Path(tmp), concurrency=2)
            try:
                self.assertTrue(two_entered.wait(1), "initial bounded workers did not start")
                manager.cancel(job["jobId"])
            finally:
                release.set()
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(entered, 2)
        self.assertEqual(service.transcribe_voice.call_count, 2)
        self.assertEqual(job["completed"], 2)
        self.assertEqual(job["completed"], job["success"] + job["failed"])

    def test_batch_segment_cancellation_is_not_counted_as_failure(self):
        inference_entered = threading.Event()
        release_segment = threading.Event()

        class BlockingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    inference_entered.set()
                    release_segment.wait(2)
                    yield SimpleNamespace(text="不应写入")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=lambda _config: BlockingModel(),
        )
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription.list_voice_server_ids",
            return_value=[1],
        ), patch(
            "wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts",
            return_value={},
        ), patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ), patch(
            "wechat_decrypt_tool.voice_transcription.load_voice_data",
            return_value=b"SILK",
        ), patch.object(
            service,
            "ensure_available",
            return_value={"available": True},
        ):
            job = manager.start(account="wxid_cancel_segment", account_dir=Path(tmp))
            self.assertTrue(inference_entered.wait(1))
            manager.cancel(job["jobId"])
            release_segment.set()
            deadline = time.time() + 2
            while time.time() < deadline:
                job = manager.get(job["jobId"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(job["completed"], 0)
        self.assertEqual(job["failed"], 0)

    def test_running_batch_progress_stays_below_100_until_done(self):
        manager = VoiceTranscriptionBatchManager(service_getter=Mock)
        manager._jobs["job"] = {
            "completed": 198,
            "success": 198,
            "native": 0,
            "cached": 0,
            "failed": 0,
            "percent": 99,
            "currentServerId": "",
            "error": "",
            "status": "running",
        }
        outcome = {"success": 1, "native": 0, "cached": 0, "failed": 0, "error": ""}

        manager._record_batch_result("job", 199, outcome, 200)
        self.assertEqual(manager.get("job")["percent"], 99)
        manager._record_batch_result("job", 200, outcome, 200)
        self.assertEqual(manager.get("job")["percent"], 99)
        manager._update("job", status="done", percent=100)
        self.assertEqual(manager.get("job")["percent"], 100)

    def test_batch_holds_service_generation_lease_until_worker_finishes(self):
        inference_entered = threading.Event()
        release_inference = threading.Event()
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small", device="cpu")
        service.ensure_available.return_value = {"available": True}
        service.configure_inference_concurrency.return_value = 1

        def transcribe(**_kwargs):
            inference_entered.set()
            release_inference.wait(2)
            return {"cached": False, "text": "完成"}

        service.transcribe_voice.side_effect = transcribe
        replacement = Mock(spec=VoiceTranscriptionService)
        replacement.config = VoiceTranscriptionConfig(model="small", device="cpu")
        module = voice_transcription_module
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE", service),
                patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE_RESETTING", False),
                patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE_LEASES", 0),
                patch.object(module, "VoiceTranscriptionService", return_value=replacement),
                patch("wechat_decrypt_tool.voice_transcription.list_voice_server_ids", return_value=[1]),
                patch("wechat_decrypt_tool.voice_transcription.list_native_voice_transcripts", return_value={}),
            ):
                manager = VoiceTranscriptionBatchManager()
                job = manager.start(account="wxid_generation", account_dir=Path(tmp))
                self.assertTrue(inference_entered.wait(1))
                with ThreadPoolExecutor(max_workers=1) as executor:
                    resetting = executor.submit(module._reset_voice_transcription_service)
                    deadline = time.time() + 1
                    while time.time() < deadline:
                        with module._VOICE_TRANSCRIPTION_SERVICE_CONDITION:
                            if module._VOICE_TRANSCRIPTION_SERVICE_RESETTING:
                                break
                        time.sleep(0.01)
                    self.assertTrue(module._VOICE_TRANSCRIPTION_SERVICE_RESETTING)
                    self.assertFalse(resetting.done())
                    service.retire.assert_not_called()
                    release_inference.set()
                    deadline = time.time() + 2
                    while time.time() < deadline:
                        job = manager.get(job["jobId"])
                        if job["status"] not in {"queued", "running"}:
                            break
                        time.sleep(0.01)
                    self.assertEqual(job["status"], "done")
                    self.assertIs(resetting.result(timeout=2), replacement)

        service.retire.assert_called_once_with()

    def test_realtime_native_transcript_is_reused_in_direct_mode(self):
        packed = bytes.fromhex(
            "084310042A2508021221E8BF99E698AFE4B880E69DA1E59088E68890E6B58BE8AF95E8BDACE58699E38082"
        )
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "raw"
            message_dir = storage / "message"
            message_dir.mkdir(parents=True)
            (message_dir / "message_0.db").touch()
            realtime = Mock(db_storage_dir=storage, handle=1, lock=threading.Lock())

            def exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertTrue(str(path).endswith("message_0.db"))
                if "sqlite_master" in sql:
                    return [{"name": "Msg_demo"}]
                return [
                    {"server_id": 123, "packed_info_data": packed.hex()},
                    {"server_id": 124, "packed_info_data": None},
                ]

            with (
                patch(
                    "wechat_decrypt_tool.wcdb_realtime.WCDB_REALTIME.ensure_connected",
                    return_value=realtime,
                ),
                patch(
                    "wechat_decrypt_tool.wcdb_realtime.exec_query",
                    side_effect=exec_query,
                ),
            ):
                voice_ids: set[int] = set()
                result = _list_realtime_native_voice_transcripts(
                    Path(tmp) / "account",
                    voice_server_ids=voice_ids,
                )

        self.assertEqual(result, {123: "这是一条合成测试转写。"})
        self.assertEqual(voice_ids, {123, 124})

    def test_batch_counts_voice_message_without_audio_as_failed(self):
        service = Mock(spec=VoiceTranscriptionService)
        service.config = VoiceTranscriptionConfig(model="small")
        service.transcribe_voice.side_effect = VoiceTranscriptionError("voice_not_found", "未找到语音数据。")
        manager = VoiceTranscriptionBatchManager(service_getter=lambda: service)

        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            conn = sqlite3.connect(str(account_dir / "message_0.db"))
            try:
                conn.execute(
                    "CREATE TABLE Msg_synthetic (server_id INTEGER, local_type INTEGER, packed_info_data BLOB)"
                )
                conn.execute("INSERT INTO Msg_synthetic VALUES (321, 34, NULL)")
                conn.commit()
            finally:
                conn.close()

            with (
                patch("wechat_decrypt_tool.voice_transcription._list_realtime_voice_server_ids", return_value=[]),
                patch(
                    "wechat_decrypt_tool.voice_transcription._list_realtime_native_voice_transcripts",
                    return_value={},
                ),
            ):
                job = manager.start(account="wxid_synthetic", account_dir=account_dir)
                deadline = time.time() + 2
                while time.time() < deadline:
                    job = manager.get(job["jobId"])
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["total"], 1)
        self.assertEqual(job["completed"], 1)
        self.assertEqual(job["failed"], 1)
        service.transcribe_voice.assert_called_once()
        call = service.transcribe_voice.call_args.kwargs
        self.assertEqual(call["account_dir"], account_dir)
        self.assertEqual(call["server_id"], 321)
        self.assertFalse(call["force"])
        self.assertIsInstance(call["cancel_event"], threading.Event)


class TestVoiceModelDeletion(unittest.TestCase):
    def test_model_storage_uses_stable_data_dir_and_legacy_output_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir = base / "data"
            output_dir = base / "migrated-output"
            legacy = output_dir / "voice_models" / "small"
            legacy.mkdir(parents=True)
            for filename in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
                (legacy / filename).write_bytes(b"ready")

            with (
                patch("wechat_decrypt_tool.voice_transcription.get_data_dir", return_value=data_dir),
                patch("wechat_decrypt_tool.voice_transcription.get_output_dir", return_value=output_dir),
            ):
                self.assertEqual(get_voice_model_storage_root(), data_dir / "voice_models")
                self.assertEqual(get_legacy_voice_model_storage_root(), output_dir / "voice_models")
                readiness = inspect_model_readiness("small")

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["source"], "legacy-output-cache")
        self.assertFalse(readiness["deletable"])

    def test_download_writes_to_application_owned_model_directory(self):
        calls = []

        def fake_download(model, *, output_dir, progress_callback):
            calls.append((model, Path(output_dir)))
            progress_callback(
                stage="downloading",
                downloaded_bytes=25,
                total_bytes=100,
                force=True,
            )
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
                (target / filename).write_bytes(b"ready")
            return target

        with tempfile.TemporaryDirectory() as tmp:
            managed_root = Path(tmp) / "voice_models"
            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=fake_download,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=managed_root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                manager = VoiceModelDownloadManager()
                job = manager.start("small")
                deadline = time.time() + 2
                while time.time() < deadline:
                    job = manager.get(job["jobId"])
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

            final_ready = (managed_root / "small" / "model.bin").is_file()
            stages_left = list(managed_root.glob(".small.download-*"))

        self.assertEqual(job["status"], "done")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "small")
        self.assertEqual(calls[0][1].parent, managed_root)
        self.assertTrue(calls[0][1].name.startswith(".small.download-"))
        self.assertTrue(final_ready)
        self.assertEqual(stages_left, [])
        self.assertEqual(job["stage"], "done")
        self.assertEqual(job["percent"], 100)

    def test_snapshot_download_reports_huggingface_aggregate_bytes(self):
        calls = []
        progress = []
        from huggingface_hub import constants as hf_constants
        from huggingface_hub.utils._runtime import is_xet_available

        def fake_snapshot(repo_id, **kwargs):
            calls.append((repo_id, dict(kwargs)))
            self.assertTrue(hf_constants.HF_HUB_DISABLE_XET)
            self.assertFalse(is_xet_available())
            self.assertEqual(hf_constants.DOWNLOAD_CHUNK_SIZE, 256 * 1024)
            self.assertEqual(kwargs["max_workers"], 1)
            if kwargs.get("dry_run"):
                return [SimpleNamespace(file_size=40), SimpleNamespace(file_size=60)]

            from huggingface_hub.utils.tqdm import _create_progress_bar

            progress_class = kwargs["tqdm_class"]
            transfer_bar = _create_progress_bar(
                cls=progress_class,
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download.transfer",
                total=0,
                desc="Downloading bytes",
                unit="B",
            )
            reconstruction_bar = _create_progress_bar(
                cls=progress_class,
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download",
                total=0,
                desc="Reconstructing (incomplete total...)",
                unit="B",
            )
            transfer_bar.total += 100
            reconstruction_bar.total += 100
            transfer_bar.refresh()
            reconstruction_bar.refresh()
            transfer_bar.update(10)
            reconstruction_bar.update(5)
            transfer_bar.update(20)
            reconstruction_bar.update(15)
            # Xet transfer bytes are not guaranteed to equal logical file bytes.
            transfer_bar.update(100)
            reconstruction_bar.update(80)
            transfer_bar.close()
            reconstruction_bar.close()
            target = Path(kwargs["local_dir"])
            target.mkdir(parents=True, exist_ok=True)
            return str(target)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "huggingface_hub.snapshot_download",
            side_effect=fake_snapshot,
        ):
            target = Path(tmp) / "stage"
            result = _download_voice_model_snapshot(
                "small",
                output_dir=target,
                progress_callback=lambda **value: progress.append(value),
            )

        self.assertEqual(result, target)
        self.assertEqual(calls[0][0], "Systran/faster-whisper-small")
        self.assertTrue(calls[0][1]["dry_run"])
        self.assertNotIn("dry_run", calls[1][1])
        byte_updates = [item for item in progress if item["stage"] == "downloading"]
        downloaded_values = [item["downloaded_bytes"] for item in byte_updates]
        positive_values = list(dict.fromkeys(value for value in downloaded_values if value > 0))
        self.assertEqual(positive_values, [10, 30, 100])
        self.assertEqual(downloaded_values, sorted(downloaded_values))
        self.assertTrue(all(item["total_bytes"] == 100 for item in byte_updates))
        # This is intentionally a one-way process setting. Restoring Xet here
        # would let a concurrent Hugging Face call bypass cancellation again.
        self.assertTrue(hf_constants.HF_HUB_DISABLE_XET)
        self.assertEqual(hf_constants.DOWNLOAD_CHUNK_SIZE, 256 * 1024)

    def test_snapshot_download_keeps_stage_progress_when_total_bytes_are_unknown(self):
        progress = []
        calls = 0

        def fake_snapshot(_repo_id, **kwargs):
            nonlocal calls
            calls += 1
            if kwargs.get("dry_run"):
                raise OSError("metadata unavailable")

            from huggingface_hub.utils.tqdm import _create_progress_bar

            progress_class = kwargs["tqdm_class"]
            transfer_bar = _create_progress_bar(
                cls=progress_class,
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download.transfer",
                total=0,
                desc="Downloading bytes",
                unit="B",
            )
            reconstruction_bar = _create_progress_bar(
                cls=progress_class,
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download",
                total=0,
                desc="Reconstructing (incomplete total...)",
                unit="B",
            )
            transfer_bar.update(10)
            reconstruction_bar.update(5)
            transfer_bar.update(20)
            reconstruction_bar.update(40)
            transfer_bar.close()
            reconstruction_bar.close()
            target = Path(kwargs["local_dir"])
            target.mkdir(parents=True, exist_ok=True)
            return str(target)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "huggingface_hub.snapshot_download",
            side_effect=fake_snapshot,
        ):
            _download_voice_model_snapshot(
                "small",
                output_dir=Path(tmp) / "stage",
                progress_callback=lambda **value: progress.append(value),
            )

        self.assertEqual(calls, 2)
        self.assertTrue(any(item["stage"] == "preparing" for item in progress))
        byte_updates = [item for item in progress if item["stage"] == "downloading"]
        downloaded_values = [item["downloaded_bytes"] for item in byte_updates]
        positive_values = list(dict.fromkeys(value for value in downloaded_values if value > 0))
        self.assertEqual(positive_values, [10, 30, 45])
        self.assertEqual(downloaded_values, sorted(downloaded_values))
        self.assertTrue(all(item["total_bytes"] == 0 for item in byte_updates))

    def test_snapshot_progress_close_propagates_callback_error_only_once(self):
        class ExpectedCancellation(RuntimeError):
            pass

        from tqdm.auto import tqdm as base_tqdm

        bars = []
        close_calls = 0
        cancellation_reports = 0
        original_close = base_tqdm.close

        def counted_close(instance):
            nonlocal close_calls
            close_calls += 1
            return original_close(instance)

        def fake_snapshot(_repo_id, **kwargs):
            if kwargs.get("dry_run"):
                return [SimpleNamespace(file_size=100)]

            from huggingface_hub.utils.tqdm import _create_progress_bar

            bar = _create_progress_bar(
                cls=kwargs["tqdm_class"],
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download.transfer",
                total=100,
                desc="Downloading bytes",
                unit="B",
            )
            bars.append(bar)
            bar.update(10)
            bar.close()
            return str(kwargs["local_dir"])

        def on_progress(**value):
            nonlocal cancellation_reports
            if (
                value["stage"] == "downloading"
                and value["force"]
                and value["downloaded_bytes"] > 0
            ):
                cancellation_reports += 1
                raise ExpectedCancellation()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "huggingface_hub.snapshot_download",
            side_effect=fake_snapshot,
        ), patch.object(base_tqdm, "close", new=counted_close):
            with self.assertRaises(ExpectedCancellation):
                _download_voice_model_snapshot(
                    "small",
                    output_dir=Path(tmp) / "stage",
                    progress_callback=on_progress,
                )

            self.assertEqual(close_calls, 1)
            self.assertEqual(cancellation_reports, 1)
            bars[0].__del__()
            self.assertEqual(close_calls, 1)
            self.assertEqual(cancellation_reports, 1)

    def test_snapshot_progress_update_error_is_not_repeated_during_destruction(self):
        class ExpectedCancellation(RuntimeError):
            pass

        from tqdm.auto import tqdm as base_tqdm

        bars = []
        close_calls = 0
        cancellation_reports = 0
        original_close = base_tqdm.close

        def counted_close(instance):
            nonlocal close_calls
            close_calls += 1
            return original_close(instance)

        def fake_snapshot(_repo_id, **kwargs):
            if kwargs.get("dry_run"):
                return [SimpleNamespace(file_size=100)]

            from huggingface_hub.utils.tqdm import _create_progress_bar

            transfer_bar = _create_progress_bar(
                cls=kwargs["tqdm_class"],
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download.transfer",
                total=100,
                desc="Downloading bytes",
                unit="B",
            )
            reconstruction_bar = _create_progress_bar(
                cls=kwargs["tqdm_class"],
                log_level=logging.WARNING,
                name="huggingface_hub.snapshot_download",
                total=100,
                desc="Reconstructing (incomplete total...)",
                unit="B",
            )
            bars.extend((transfer_bar, reconstruction_bar))
            transfer_bar.update(10)
            return str(kwargs["local_dir"])

        def on_progress(**value):
            nonlocal cancellation_reports
            if value["stage"] == "downloading" and value["downloaded_bytes"] > 0:
                cancellation_reports += 1
                raise ExpectedCancellation()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "huggingface_hub.snapshot_download",
            side_effect=fake_snapshot,
        ), patch.object(base_tqdm, "close", new=counted_close):
            with self.assertRaises(ExpectedCancellation):
                _download_voice_model_snapshot(
                    "small",
                    output_dir=Path(tmp) / "stage",
                    progress_callback=on_progress,
                )

            self.assertEqual(close_calls, 0)
            self.assertEqual(cancellation_reports, 1)
            stderr = io.StringIO()
            with patch("sys.stderr", new=stderr):
                for bar in bars:
                    bar.__del__()
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(close_calls, 2)
            self.assertEqual(cancellation_reports, 1)

    def test_download_progress_is_monotonic_and_reaches_100_only_after_install(self):
        entered = threading.Event()
        release = threading.Event()

        def fake_download(model, *, output_dir, progress_callback):
            progress_callback(
                stage="downloading",
                downloaded_bytes=100,
                total_bytes=100,
                force=True,
            )
            progress_callback(
                stage="downloading",
                downloaded_bytes=30,
                total_bytes=100,
                force=True,
            )
            entered.set()
            release.wait(2)
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
                (target / filename).write_bytes(b"ready")
            return target

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=fake_download,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=Path(tmp) / "voice_models",
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                manager = VoiceModelDownloadManager()
                job = manager.start("small")
                self.assertTrue(entered.wait(1))
                active = manager.get(job["jobId"])
                self.assertEqual(active["status"], "running")
                self.assertEqual(active["stage"], "downloading")
                self.assertEqual(active["downloadedBytes"], 100)
                self.assertEqual(active["totalBytes"], 100)
                self.assertEqual(active["percent"], 99)
                release.set()
                deadline = time.time() + 2
                while time.time() < deadline:
                    job = manager.get(job["jobId"])
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["stage"], "done")
        self.assertEqual(job["percent"], 100)

    def test_only_one_model_download_runs_globally(self):
        entered = threading.Event()
        release = threading.Event()

        def fake_download(model, *, output_dir, progress_callback):
            entered.set()
            release.wait(2)
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
                (target / filename).write_bytes(b"ready")
            return target

        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
            side_effect=fake_download,
        ), patch(
            "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
            return_value=Path(tmp) / "voice_models",
        ), patch(
            "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
            return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
        ):
            manager = VoiceModelDownloadManager()
            first = manager.start("small")
            self.assertTrue(entered.wait(1))
            try:
                self.assertEqual(manager.start("small")["jobId"], first["jobId"])
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    manager.start("base")
            finally:
                release.set()
                deadline = time.time() + 2
                while time.time() < deadline:
                    if manager.get(first["jobId"])["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

        self.assertEqual(raised.exception.code, "download_busy")

    def test_incomplete_managed_download_is_deletable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            target = root / "small"
            stage = root / ".small.download-interrupted"
            target.mkdir(parents=True)
            stage.mkdir()
            (target / "model.bin").write_bytes(b"partial")
            (stage / "model.bin").write_bytes(b"stage")

            with (
                patch("wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root", return_value=root),
                patch("wechat_decrypt_tool.voice_transcription.get_legacy_voice_model_storage_root", return_value=Path(tmp) / "legacy"),
                patch("faster_whisper.utils.download_model", side_effect=RuntimeError("cache miss")),
                patch("wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER.latest_by_model", return_value={}),
                patch("wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model", return_value=False),
                patch("wechat_decrypt_tool.voice_transcription.get_voice_transcription_service", return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium"))),
            ):
                readiness = inspect_model_readiness("small")
                deleted = delete_voice_model("small")

        self.assertFalse(readiness["ready"])
        self.assertTrue(readiness["deletable"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["freedBytes"], 12)
        self.assertFalse(target.exists())
        self.assertFalse(stage.exists())

    def test_delete_preempts_running_download_and_prevents_model_resurrection(self):
        entered = threading.Event()
        allow_download_to_return = threading.Event()

        def fake_download(model, *, output_dir, progress_callback):
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            (target / "model.bin").write_bytes(b"partial")
            entered.set()
            allow_download_to_return.wait(2)
            for filename in ("config.json", "tokenizer.json", "vocabulary.json"):
                (target / filename).write_bytes(b"ready")
            return target

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            manager = VoiceModelDownloadManager()
            delete_result = []
            delete_errors = []

            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=fake_download,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER",
                    manager,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model",
                    return_value=False,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                job = manager.start("small")
                self.assertTrue(entered.wait(1))

                def delete_model():
                    try:
                        delete_result.append(delete_voice_model("small"))
                    except Exception as exc:  # pragma: no cover - asserted below
                        delete_errors.append(exc)

                delete_thread = threading.Thread(target=delete_model)
                delete_thread.start()
                time.sleep(0.05)

                # Deletion must wait for the worker to leave its download call.
                self.assertTrue(delete_thread.is_alive())
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    manager.start("small")
                self.assertEqual(raised.exception.code, "model_busy")
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    acquire_voice_model_activity("small")
                self.assertEqual(raised.exception.code, "model_busy")

                allow_download_to_return.set()
                delete_thread.join(2)

                final_job = manager.get(job["jobId"])
                stages_left = list(root.glob(".small.download-*"))
                target_exists = (root / "small").exists()

        self.assertFalse(delete_thread.is_alive())
        self.assertEqual(delete_errors, [])
        self.assertEqual(len(delete_result), 1)
        self.assertTrue(delete_result[0]["deleted"])
        self.assertEqual(final_job["status"], "cancelled")
        self.assertEqual(final_job["stage"], "cancelled")
        self.assertEqual(stages_left, [])
        self.assertFalse(target_exists)

    def test_delete_interrupts_download_at_progress_callback(self):
        entered = threading.Event()
        finished_normally = threading.Event()

        def fake_download(model, *, output_dir, progress_callback):
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            (target / "model.bin").write_bytes(b"partial")
            entered.set()
            for downloaded in range(1, 501):
                progress_callback(
                    stage="downloading",
                    downloaded_bytes=downloaded,
                    total_bytes=500,
                    force=True,
                )
                time.sleep(0.005)
            finished_normally.set()
            return target

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            manager = VoiceModelDownloadManager()
            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=fake_download,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER",
                    manager,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model",
                    return_value=False,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                job = manager.start("small")
                self.assertTrue(entered.wait(1))
                result = delete_voice_model("small")
                final_job = manager.get(job["jobId"])
                target_exists = (root / "small").exists()
                stages_left = list(root.glob(".small.download-*"))

        self.assertTrue(result["deleted"])
        self.assertFalse(finished_normally.is_set())
        self.assertEqual(final_job["status"], "cancelled")
        self.assertFalse(target_exists)
        self.assertEqual(stages_left, [])

    def test_delete_preempts_download_while_job_is_still_queued(self):
        worker_entered = threading.Event()
        allow_worker_to_run = threading.Event()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            manager = VoiceModelDownloadManager()
            original_run = manager._run
            delete_result = []

            def delayed_run(*args):
                worker_entered.set()
                allow_worker_to_run.wait(2)
                return original_run(*args)

            with (
                patch.object(manager, "_run", side_effect=delayed_run),
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=AssertionError("cancelled queued job must not enter download"),
                ) as download,
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER",
                    manager,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model",
                    return_value=False,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                job = manager.start("small")
                self.assertTrue(worker_entered.wait(1))
                self.assertEqual(manager.get(job["jobId"])["status"], "queued")

                delete_thread = threading.Thread(
                    target=lambda: delete_result.append(delete_voice_model("small"))
                )
                delete_thread.start()
                time.sleep(0.05)
                self.assertTrue(delete_thread.is_alive())

                allow_worker_to_run.set()
                delete_thread.join(2)
                final_job = manager.get(job["jobId"])

            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(final_job["status"], "cancelled")
            self.assertEqual(final_job["stage"], "cancelled")
            self.assertEqual(len(delete_result), 1)
            self.assertTrue(delete_result[0]["deleted"])
            self.assertFalse(root.exists())
            download.assert_not_called()

    def test_delete_waits_for_replace_race_and_removes_installed_model(self):
        replace_entered = threading.Event()
        allow_replace = threading.Event()
        real_replace = os.replace

        def fake_download(model, *, output_dir, progress_callback):
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
                (target / filename).write_bytes(b"ready")
            return target

        def blocking_replace(source, destination):
            replace_entered.set()
            allow_replace.wait(2)
            return real_replace(source, destination)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            manager = VoiceModelDownloadManager()
            delete_result = []

            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription._download_voice_model_snapshot",
                    side_effect=fake_download,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.os.replace",
                    side_effect=blocking_replace,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER",
                    manager,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model",
                    return_value=False,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="medium")),
                ),
            ):
                job = manager.start("small")
                self.assertTrue(replace_entered.wait(1))

                delete_thread = threading.Thread(
                    target=lambda: delete_result.append(delete_voice_model("small"))
                )
                delete_thread.start()
                time.sleep(0.05)
                self.assertTrue(delete_thread.is_alive())

                allow_replace.set()
                delete_thread.join(2)
                final_job = manager.get(job["jobId"])

            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(final_job["status"], "cancelled")
            self.assertEqual(len(delete_result), 1)
            self.assertTrue(delete_result[0]["deleted"])
            self.assertFalse((root / "small").exists())
            self.assertEqual(list(root.glob(".small.download-*")), [])

    def test_download_rejects_linked_model_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            root = base / "voice_models"
            try:
                root.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")

            with patch(
                "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                return_value=root,
            ):
                manager = VoiceModelDownloadManager()
                job = manager.start("small")
                deadline = time.time() + 2
                while time.time() < deadline:
                    job = manager.get(job["jobId"])
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.01)

            self.assertEqual(job["status"], "error")
            self.assertFalse((outside / "small").exists())

    def test_delete_refuses_while_model_has_active_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            target = root / "small"
            target.mkdir(parents=True)
            (target / "model.bin").write_bytes(b"model")
            activity_key = acquire_voice_model_activity("small")
            try:
                with (
                    patch("wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root", return_value=root),
                    patch("wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER.latest_by_model", return_value={}),
                    patch("wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model", return_value=False),
                ):
                    with self.assertRaises(VoiceTranscriptionError) as raised:
                        delete_voice_model("small")
            finally:
                release_voice_model_activity(activity_key)

            target_still_exists = target.exists()

        self.assertEqual(raised.exception.code, "model_busy")
        self.assertTrue(target_still_exists)

    def test_model_setting_refuses_while_current_model_has_active_lease(self):
        current = SimpleNamespace(config=VoiceTranscriptionConfig(model="small"))
        activity_key = acquire_voice_model_activity("small")
        try:
            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription.read_effective_voice_transcription_model",
                    return_value=("small", "user"),
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_transcription_service",
                    return_value=current,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.write_voice_transcription_model_setting"
                ) as write_setting,
                patch("wechat_decrypt_tool.voice_transcription._reset_voice_transcription_service") as reset,
            ):
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    set_voice_transcription_model("base")
        finally:
            release_voice_model_activity(activity_key)

        self.assertEqual(raised.exception.code, "model_busy")
        write_setting.assert_not_called()
        reset.assert_not_called()

    def test_delete_removes_only_application_owned_model_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "voice_models"
            target = root / "small"
            target.mkdir(parents=True)
            (target / "model.bin").write_bytes(b"model")
            outside = Path(tmp) / "shared-cache.bin"
            outside.write_bytes(b"keep")

            with (
                patch(
                    "wechat_decrypt_tool.voice_transcription.get_voice_model_storage_root",
                    return_value=root,
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_MODEL_DOWNLOAD_MANAGER.latest_by_model",
                    return_value={},
                ),
                patch(
                    "wechat_decrypt_tool.voice_transcription.VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model",
                    return_value=False,
                ),
                patch("wechat_decrypt_tool.voice_transcription._reset_voice_transcription_service"),
            ):
                result = delete_voice_model("small")

            self.assertTrue(result["deleted"])
            self.assertEqual(result["freedBytes"], 5)
            self.assertFalse(target.exists())
            self.assertEqual(outside.read_bytes(), b"keep")


class TestVoiceExportModelActivity(unittest.TestCase):
    def test_export_claims_model_before_worker_start(self):
        from wechat_decrypt_tool import chat_export_service

        manager = chat_export_service.ChatExportManager()
        events = []
        worker = Mock()
        worker.start.side_effect = lambda: events.append("start")

        def acquire(_model):
            events.append("acquire")
            return "small"

        with (
            patch.object(chat_export_service, "_resolve_account_dir", return_value=Path("synthetic-account")),
            patch.object(
                chat_export_service,
                "get_voice_transcription_service",
                return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="small")),
            ),
            patch.object(chat_export_service, "acquire_voice_model_activity", side_effect=acquire),
            patch.object(chat_export_service, "capture_voice_transcript_cache_generation", return_value=73),
            patch.object(chat_export_service.threading, "Thread", return_value=worker) as thread_type,
        ):
            job = manager.create_job(
                account="wxid_synthetic",
                source="decrypted",
                scope="selected",
                usernames=["synthetic-contact"],
                export_format="json",
                start_time=None,
                end_time=None,
                include_hidden=False,
                include_official=False,
                include_media=False,
                media_kinds=[],
                message_types=[],
                output_dir=None,
                allow_process_key_extract=False,
                download_remote_media=False,
                privacy_mode=False,
                file_name=None,
                transcribe_voice=True,
            )

        self.assertEqual(events, ["acquire", "start"])
        self.assertEqual(job.voice_cache_generation, 73)
        self.assertEqual(thread_type.call_args.kwargs["kwargs"]["voice_activity_key"], "small")

    def test_export_with_voice_transcription_holds_model_activity(self):
        from wechat_decrypt_tool import chat_export_service

        manager = chat_export_service.ChatExportManager()
        job = chat_export_service.ExportJob(
            export_id="synthetic-export",
            account="wxid_synthetic",
            options={"transcribeVoice": True, "privacyMode": False},
        )

        def finish_export(current_job, _account_dir):
            current_job.status = "done"

        with (
            patch.object(
                chat_export_service,
                "get_voice_transcription_service",
                return_value=SimpleNamespace(config=VoiceTranscriptionConfig(model="small")),
            ),
            patch.object(chat_export_service, "acquire_voice_model_activity", return_value="small") as acquire,
            patch.object(chat_export_service, "release_voice_model_activity") as release,
            patch.object(manager, "_run_job", side_effect=finish_export),
        ):
            manager._run_job_safe(job, Path("synthetic-account"), report_outcome=False)

        acquire.assert_called_once_with("small")
        release.assert_called_once_with("small")


if __name__ == "__main__":
    unittest.main()
