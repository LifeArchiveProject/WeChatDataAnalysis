from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .core import (
    DEFAULT_WECHAT_APP,
    account_label,
    cancel_capture,
    capture_status,
    confirm_manual_launch,
    default_backup_root,
    discover_default_probe_databases,
    finish_capture,
    inspect_environment,
    load_preferences,
    mask_database_key,
    prepare_capture,
    preflight_capture,
    prefer_active_probe_database,
    resolve_probe_database,
    save_preferences,
    validate_database_key,
)


_CAPTURE_CLOSE_NOTICE = (
    "捕获值通过校验后，工具会自动关闭临时微信并恢复腾讯原签名版本；"
    "这是正常流程，并非闪退，无需重新登录。请等待工具显示最终结果。"
)
_CAPTURE_PHASE_ORDER = {
    "waiting_authorization": 0,
    "monitoring": 1,
    # Native and LLDB report capture/validation in different valid orders.
    "captured": 2,
    "validating": 2,
    "restoring": 3,
}


class KeyExtractorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WeData 密钥提取器 · 1.1.11")
        self.root.geometry("760x760")
        self.root.minsize(700, 720)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._dark = self._system_uses_dark_mode()
        self._configure_style()
        preferences = load_preferences()
        self.wechat_var = tk.StringVar(value=preferences["wechat_app"])
        self.database_var = tk.StringVar(value=preferences["database_path"])
        self.work_root_var = tk.StringVar(value=preferences["work_root"])
        self.status_var = tk.StringVar(value="等待检查本机环境")
        self.detail_var = tk.StringVar(value="本次不会读取旧密钥缓存；只有重新捕获并校验成功才会显示结果。")
        self.key_var = tk.StringVar(value="尚未提取")
        self.stage = "idle"
        self.db_choices: dict[str, str] = {}
        self.database_choice_var = tk.StringVar()
        self.current_key = ""
        self.last_error = ""
        self._busy = False
        self._closing_after_cleanup = False
        self._closed = False
        self._capture_waiting_for_ready = False
        self._capture_ready_deadline = 0.0
        self._capture_transaction_id = ""
        self._capture_poll_generation = 0
        self._capture_poll_active = False
        self._capture_poll_after_id = None
        self._tasks: queue.Queue[tuple[bool, Any, Callable[[Any], None] | None]] = queue.Queue()
        self._prepared_health_results = queue.Queue()
        self._prepared_health_inflight = False
        self._prepared_exit_attempted_transaction = ""

        self._build_ui()
        self._discover_accounts()
        self.root.after(100, self._drain_tasks)
        self.root.after(250, self._check_pending_capture)
        self.root.after(1000, self._poll_prepared_health)

    def _poll_prepared_health(self) -> None:
        """Detect late startup rejection without blocking Tk or touching capture."""
        if self._closed:
            return
        try:
            transaction_id, status = self._prepared_health_results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._prepared_health_inflight = False
            self._apply_prepared_health(transaction_id, status)
        if (not self._busy and self.stage in {"prepared", "preflight"}
                and self._capture_transaction_id and not self._prepared_health_inflight):
            self._prepared_health_inflight = True
            transaction_id = self._capture_transaction_id
            wechat_app = self.wechat_var.get()
            results = self._prepared_health_results

            def read_health() -> None:
                try:
                    status = capture_status(wechat_app)
                except Exception:
                    status = {}
                results.put((transaction_id, status))

            threading.Thread(target=read_health, daemon=True).start()
        self.root.after(1000, self._poll_prepared_health)

    def _apply_prepared_health(self, transaction_id: str, status: dict[str, Any]) -> None:
        if (self._busy or self._closed or self._closing_after_cleanup
                or self.stage not in {"prepared", "preflight"}
                or not transaction_id or transaction_id != self._capture_transaction_id
                or transaction_id == self._prepared_exit_attempted_transaction
                or status.get("transaction_id") != transaction_id
                or status.get("stage") not in {"launched", "preflight_passed"}
                or status.get("prepared_process_exited") is not True):
            return
        self._prepared_exit_attempted_transaction = transaction_id
        self.last_error = "临时微信已退出或启动被中止，本次未完成提取。请勿反复登录或绕过系统安全提示。"
        self.detail_var.set(self.last_error)
        # Run the existing serialized, identity-checked recovery. Never swap
        # bundles from a status reader or while another operation is active.
        self._run_task(
            lambda: cancel_capture(self.wechat_var.get(), self.work_root_var.get()),
            self._prepared_exit_recovered,
            status="临时微信已退出，正在检查并恢复官方原版…",
        )

    def _prepared_exit_recovered(self, result: dict[str, Any]) -> None:
        self._cancelled(result)
        if result.get("official_wechat_verified") is True and not self._closed:
            self.status_var.set("本次提取已停止，官方微信已恢复" if result.get("official_wechat_restored")
                                else "本次提取已停止，当前官方微信已确认")

    @staticmethod
    def _system_uses_dark_mode() -> bool:
        result = subprocess.run(
            ["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and "dark" in result.stdout.lower()

    def _configure_style(self) -> None:
        self.colors = (
            {
                "bg": "#181818",
                "surface": "#252525",
                "soft": "#2E2E2E",
                "text": "#F5F5F5",
                "muted": "#C7C7C7",
                "border": "#3D3D3D",
                "accent": "#07C160",
                "danger": "#FF7373",
            }
            if self._dark
            else {
                "bg": "#F4FAF6",
                "surface": "#FFFFFF",
                "soft": "#F1F8F3",
                "text": "#18201B",
                "muted": "#66736B",
                "border": "#D8E8DD",
                "accent": "#07C160",
                "danger": "#C43A3A",
            }
        )
        self.root.configure(bg=self.colors["bg"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["surface"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Card.TLabel", background=self.colors["surface"], foreground=self.colors["text"])
        style.configure("Muted.TLabel", background=self.colors["surface"], foreground=self.colors["muted"])
        style.configure(
            "TEntry",
            fieldbackground=self.colors["soft"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            insertcolor=self.colors["text"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.colors["soft"],
            foreground=self.colors["text"],
            background=self.colors["soft"],
            bordercolor=self.colors["border"],
            arrowcolor=self.colors["muted"],
        )
        style.map("TCombobox", fieldbackground=[("readonly", self.colors["soft"])])
        style.configure(
            "TButton",
            padding=(12, 8),
            background=self.colors["soft"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
        )
        style.map("TButton", background=[("active", self.colors["border"])])
        style.configure(
            "Accent.TButton",
            padding=(14, 9),
            background=self.colors["accent"],
            foreground="#FFFFFF",
            bordercolor=self.colors["accent"],
        )
        style.map("Accent.TButton", background=[("active", "#06AD56"), ("disabled", self.colors["border"])])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="本机工具 · 不联网", foreground=self.colors["accent"]).pack(anchor="w")
        ttk.Label(outer, text="WeData 密钥提取器", font=("SF Pro Display", 26, "bold")).pack(anchor="w", pady=(4, 2))

        settings = ttk.Frame(outer, style="Card.TFrame", padding=16)
        settings.pack(fill="x", pady=(10, 0))
        settings.columnconfigure(1, weight=1)

        self._field_row(settings, 0, "微信应用", self.wechat_var, self._pick_wechat_app)
        ttk.Label(settings, text="微信账号", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.account_combo = ttk.Combobox(settings, textvariable=self.database_choice_var, state="readonly")
        self.account_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.account_combo.bind("<<ComboboxSelected>>", self._on_account_selected)
        ttk.Button(settings, text="重新扫描", command=self._discover_accounts).grid(row=1, column=2, padx=(8, 0), pady=6)

        self._field_row(settings, 2, "数据库", self.database_var, self._pick_database)
        self._field_row(settings, 3, "备份根目录", self.work_root_var, self._pick_work_root)

        status = ttk.Frame(outer, style="Card.TFrame", padding=16)
        status.pack(fill="x", pady=(12, 0))
        ttk.Label(status, textvariable=self.status_var, style="Card.TLabel", font=("SF Pro Text", 16, "bold")).pack(anchor="w")
        ttk.Label(
            status,
            textvariable=self.detail_var,
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(7, 12))
        self.progress = ttk.Progressbar(status, mode="indeterminate")
        self.progress.pack(fill="x")

        key_card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        key_card.pack(fill="x", pady=(12, 0))
        ttk.Label(key_card, text="数据库密钥", style="Card.TLabel").pack(anchor="w")
        ttk.Label(key_card, textvariable=self.key_var, style="Card.TLabel", font=("SF Mono", 15, "bold")).pack(anchor="w", pady=(7, 10))
        key_actions = ttk.Frame(key_card, style="Card.TFrame")
        key_actions.pack(fill="x")
        self.copy_button = ttk.Button(key_actions, text="复制密钥", command=self._copy_key, state="disabled")
        self.copy_button.pack(side="left")
        ttk.Button(key_actions, text="打开缓存位置", command=self._open_key_location).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(14, 0))
        self.primary_button = ttk.Button(actions, text="检查环境并开始", style="Accent.TButton", command=self._start)
        self.primary_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消并恢复微信", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="完全磁盘访问设置", command=self._open_full_disk_access).pack(side="right")
        ttk.Button(actions, text="显示微信窗口", command=self._show_wechat).pack(side="right", padx=(0, 8))
        ttk.Button(outer, text="打开系统设置（安全授权需本人确认）", command=self._open_security_settings).pack(anchor="e", pady=(6, 0))

        ttk.Label(
            outer,
            text="仅供处理你本人有权访问的微信数据。提取期间会临时重签默认路径微信，并在结束时恢复腾讯原签名版本。",
            foreground=self.colors["muted"],
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(14, 0))

    def _field_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="选择", command=command).grid(row=row, column=2, padx=(8, 0), pady=6)

    def _discover_accounts(self) -> None:
        current = self.database_var.get().strip()
        databases = []
        current_path = Path(current).expanduser() if current else None
        try:
            current_is_usable = bool(
                current_path
                and current_path.is_file()
                and current_path.stat().st_size >= 4096
            )
        except OSError:
            current_is_usable = False
        if current_is_usable:
            try:
                databases = [
                    Path(prefer_active_probe_database(
                        current,
                        wechat_app=self.wechat_var.get(),
                    ))
                ]
            except (FileNotFoundError, PermissionError, OSError):
                databases = []
        if not databases:
            databases = [
                Path(prefer_active_probe_database(path, wechat_app=self.wechat_var.get()))
                for path in discover_default_probe_databases()
            ]
        self.db_choices = {
            f"{account_label(path)} · {path.name}": str(path)
            for path in databases
        }
        selected = next((label for label, path in self.db_choices.items() if path == current), "")
        if current and not selected:
            # An updated ad-hoc application can temporarily lose its macOS
            # Full Disk Access grant.  Do not silently replace the saved
            # app_data database with a visible but stale legacy duplicate;
            # preserve the explicit path so environment inspection reports
            # the permission problem to the user.
            saved_label = f"{account_label(current)} · {Path(current).name} · 已保存路径"
            while saved_label in self.db_choices:
                saved_label += "*"
            self.db_choices[saved_label] = current
            selected = saved_label
        elif not selected and self.db_choices:
            selected = next(iter(self.db_choices))
            self.database_var.set(self.db_choices[selected])
        self.account_combo["values"] = list(self.db_choices)
        self.database_choice_var.set(selected or "未自动找到账号，请手动选择数据库")

    def _on_account_selected(self, _event: object = None) -> None:
        selected = self.db_choices.get(self.database_choice_var.get())
        if selected:
            self.database_var.set(selected)

    def _pick_wechat_app(self) -> None:
        selected = filedialog.askdirectory(initialdir="/Applications", title="选择 WeChat.app")
        if selected:
            self.wechat_var.set(selected)

    def _pick_database(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择任意加密微信数据库",
            filetypes=[("微信数据库", "*.db"), ("所有文件", "*")],
        )
        if selected:
            self.database_var.set(selected)

    def _pick_work_root(self) -> None:
        selected = filedialog.askdirectory(title="选择原版微信备份根目录")
        if selected:
            self.work_root_var.set(selected)

    def _persist(self) -> None:
        save_preferences(
            {
                "wechat_app": self.wechat_var.get().strip() or str(DEFAULT_WECHAT_APP),
                "database_path": self.database_var.get().strip(),
                "work_root": self.work_root_var.get().strip(),
            }
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.progress.start(10)
            self.primary_button.configure(state="disabled")
            self.cancel_button.configure(state="disabled")
        else:
            self.progress.stop()
            self.primary_button.configure(state="normal")
            self.cancel_button.configure(state="normal" if self.stage in {"system_approval", "prepared", "preflight"} else "disabled")

    def _run_task(
        self,
        operation: Callable[[], Any],
        success: Callable[[Any], None],
        *,
        status: str,
    ) -> None:
        if self._busy:
            return
        self.status_var.set(status)
        self._set_busy(True)

        def worker() -> None:
            try:
                self._tasks.put((True, operation(), success))
            except Exception as exc:
                self._tasks.put((False, exc, None))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_tasks(self) -> None:
        if self._closed:
            return
        try:
            while True:
                ok, value, callback = self._tasks.get_nowait()
                self._set_busy(False)
                if ok and callback is not None:
                    callback(value)
                elif not ok:
                    self._handle_error(value)
                if self._closed:
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._drain_tasks)

    def _start(self) -> None:
        if self.stage == "system_approval":
            self._run_task(
                lambda: confirm_manual_launch(self.wechat_var.get(), self.work_root_var.get(), self._capture_transaction_id),
                self._manual_launch_checked,
                status="正在检查你手动打开的微信；不会自动授权或启动监测…",
            )
            return
        if self.stage == "prepared":
            self._run_preflight()
            return
        if self.stage == "preflight":
            self._run_capture()
            return
        if self.stage == "success":
            self._copy_key()
            return

        self._persist()
        self._run_task(
            lambda: inspect_environment(
                self.wechat_var.get(),
                self.database_var.get(),
                self.work_root_var.get(),
            ),
            self._environment_ready,
            status="正在检查微信、数据库和备份目录…",
        )

    def _environment_ready(self, result: dict[str, Any]) -> None:
        if result.get("errors"):
            self._handle_error(RuntimeError("\n".join(result["errors"])))
            return
        self.database_var.set(str(result["database"]))
        self._persist()
        self.detail_var.set("环境检查通过。本次不会读取旧密钥缓存，将直接开始全新捕获。")
        self._confirm_fresh_capture()

    def _confirm_fresh_capture(self) -> None:
        restarting = self.stage == "external_install_conflict"
        confirmed = messagebox.askokcancel(
            "以当前版本重新开始" if restarting else "开始全新提取",
            ("将重新验证当前腾讯官方微信，并以当前版本建立新事务。旧备份和原版保护副本会保留，"
             "不会用旧版本覆盖当前安装。\n\n" if restarting else "")
            + "本次将忽略已有密钥缓存。接下来会先在所选备份目录保存并验证腾讯原版微信，"
            "然后临时重签 /Applications/WeChat.app。\n\n"
            "准备完成后，请点击“显示微信窗口”手动打开。若系统提示无法验证，你可以自行决定是否在"
            "系统设置中为该应用授权；工具不会关闭安全保护，也不会代替你确认。\n\n"
            + _CAPTURE_CLOSE_NOTICE + "\n\n是否继续？",
        )
        if not confirmed:
            self.status_var.set("已取消")
            return
        self._run_task(
            lambda: prepare_capture(self.wechat_var.get(), self.work_root_var.get()),
            self._prepared,
            status="正在验证原版备份并准备临时微信…",
        )

    def _prepared(self, result: dict[str, Any]) -> None:
        self._capture_transaction_id = str(result.get("transaction_id") or "")
        if result.get("requires_manual_launch") is True:
            self.stage = "system_approval"
            self.status_var.set("等待你手动打开微信；尚未启动监测")
            self.detail_var.set(
                "先点击“显示微信窗口”。若仅提示“Apple 无法验证”，且你确认来源可信，可自行在"
                "系统设置 → 隐私与安全性中查看该微信的“仍要打开”。这是单应用授权，不是 Apple 公证。\n"
                "若提示含恶意软件、会损害电脑，或没有允许入口，请取消并恢复，不要继续。\n"
                "微信正常打开后点击下方“检查启动”；未能打开也可随时取消并恢复。"
            )
            self.primary_button.configure(text="我已手动打开，检查启动")
            self.cancel_button.configure(state="normal")
            return
        self.stage = "prepared"
        self.status_var.set("第一步：先登录临时微信")
        self.detail_var.set(
            "请只使用系统自动打开的微信窗口，完成扫码、手机确认和验证码，直到进入聊天主界面；"
            "然后点击“我已登录，检查断点”。此时监测尚未启动。"
        )
        self.primary_button.configure(text="我已登录，检查断点")
        self.cancel_button.configure(state="normal")
        self.root.after(150, self._show_wechat)

    def _manual_launch_checked(self, result: dict[str, Any]) -> None:
        if not self._capture_transaction_id or result.get("transaction_id") != self._capture_transaction_id:
            self._handle_error(RuntimeError("启动确认不属于本次事务，请先取消并恢复微信。"))
            return
        if result.get("ready_for_preflight") is not True:
            self.status_var.set("尚未检测到稳定运行的临时微信")
            self.detail_var.set("系统可能仍在等待你的决定，也可能启动失败。工具未启动监测、未重新签名。"
                                "请先处理系统提示；若仍打不开，请取消并恢复微信。")
            return
        self._prepared(result)

    def _run_preflight(self) -> None:
        self._run_task(
            lambda: preflight_capture(self.wechat_var.get(), self.work_root_var.get()),
            self._preflight_ready,
            status="正在检查可用断点；授权后会立即分离…",
        )

    def _preflight_ready(self, result: dict[str, Any]) -> None:
        self._capture_transaction_id = str(result.get("transaction_id") or "")
        self.stage = "preflight"
        self.status_var.set("第二步：退出账号，再启动监测")
        method = str(result.get("method") or "")
        check_label = (
            "低内存原生断点检查通过"
            if "native" in method
            else "断点检查通过"
        )
        self.detail_var.set(
            f"{check_label}。现在请在当前微信里打开设置并退出账号，"
            "等到显示二维码登录界面后，不要先扫码；"
            "回到这里点击“已退出，启动监测”。"
        )
        self.primary_button.configure(text="已退出，启动监测")
        self.cancel_button.configure(state="normal")

    def _run_capture(self) -> None:
        if self._busy:
            return
        confirmed = messagebox.askokcancel(
            "确认已退出账号",
            "请确认临时微信现在停留在二维码登录界面。点击继续后允许管理员授权，"
            "等待工具明确显示“监测已就绪，可以重新登录”后，再登录同一个微信账号。\n\n"
            + _CAPTURE_CLOSE_NOTICE,
        )
        if not confirmed:
            return
        hidden = self._hide_wechat()
        self._stop_capture_polling()
        self._capture_poll_active = True
        self._capture_waiting_for_ready = True
        self._capture_ready_deadline = time.monotonic() + 60.0
        self._capture_phase_order = -1
        self._capture_ready_shown = False
        self._capture_status_inflight = False
        self._capture_status_results: queue.Queue[dict[str, Any]] = queue.Queue()
        generation = self._capture_poll_generation
        self.detail_var.set(
            ("微信登录窗口已暂时隐藏。请先完成管理员授权；只有界面提示“监测已就绪”后，"
            "微信才会重新显示，此时再登录同一个账号。"
            if hidden
            else "正在安装登录监测。请先完成管理员授权；监测就绪前不要扫码或登录微信。")
            + "\n" + _CAPTURE_CLOSE_NOTICE
        )
        self._run_task(
            lambda: finish_capture(
                self.wechat_var.get(),
                self.database_var.get(),
                self.work_root_var.get(),
            ),
            lambda result: self._capture_finished(result, generation),
            status="等待管理员授权并安装登录监测…",
        )
        self._capture_poll_after_id = self.root.after(250, lambda: self._wait_for_monitor_ready(generation))

    def _wait_for_monitor_ready(self, generation: int | None = None) -> None:
        """Keep polling through restore; filesystem/signature reads never run on Tk."""
        if generation is not None and generation != self._capture_poll_generation:
            return
        if not self._capture_poll_active or getattr(self, "_closed", False):
            return
        self._capture_poll_after_id = None
        if not self._busy or self._closing_after_cleanup:
            self._stop_capture_polling()
            return
        generation = self._capture_poll_generation
        try:
            status = self._capture_status_results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._capture_status_inflight = False
            self._apply_capture_status(status)
        if self._capture_waiting_for_ready and time.monotonic() >= self._capture_ready_deadline:
            self.detail_var.set(
                "仍在等待管理员授权或登录监测安装完成；监测就绪前不要扫码或登录。\n"
                + _CAPTURE_CLOSE_NOTICE
            )
        if not self._capture_status_inflight:
            self._capture_status_inflight = True
            wechat_app = self.wechat_var.get()
            results = self._capture_status_results

            def read_status() -> None:
                try:
                    value = capture_status(wechat_app)
                except Exception:
                    value = {}
                # A per-run queue prevents an old reader from entering a new run.
                results.put(value)

            threading.Thread(target=read_status, daemon=True).start()
        self._capture_poll_after_id = self.root.after(250, lambda: self._wait_for_monitor_ready(generation))

    def _apply_capture_status(self, status: dict[str, Any]) -> None:
        if (not status.get("pending") or not self._capture_transaction_id
                or status.get("transaction_id") != self._capture_transaction_id):
            # Clearing state is not success: finish_capture still has to return.
            return
        phase = status.get("capture_phase")
        order = _CAPTURE_PHASE_ORDER.get(phase, -1)
        if order < 0 or order < self._capture_phase_order:
            return
        if phase == "monitoring" and status.get("monitor_ready") is not True:
            return
        self._capture_phase_order = order
        if phase == "waiting_authorization":
            self.status_var.set("等待管理员授权并安装登录监测…")
            return
        self._capture_waiting_for_ready = False
        if phase == "monitoring":
            self.status_var.set("监测已就绪，可以重新登录")
            self.detail_var.set("登录监测已安装并正在监听。请登录同一个账号。\n" + _CAPTURE_CLOSE_NOTICE)
            if not self._capture_ready_shown:
                self._capture_ready_shown = True
                self._show_wechat()
        elif phase == "captured":
            self.status_var.set("捕获值已通过消息库与会话库校验")
            self.detail_var.set(_CAPTURE_CLOSE_NOTICE)
        elif phase == "validating":
            self.status_var.set("正在复验本次捕获结果…")
            self.detail_var.set("正在进行最终数据库复验，尚未完成提取。无需重新登录；请等待复验与恢复流程结束。")
        elif phase == "restoring":
            self.status_var.set("正在恢复腾讯原签名微信…")
            self.detail_var.set(
                "正在结束临时微信并恢复原版；成功和失败都会执行此步骤，尚不能据此确认提取成功。"
                "无需重新登录，请等待最终结果。"
            )

    def _stop_capture_polling(self) -> None:
        self._capture_poll_active = False
        self._capture_waiting_for_ready = False
        self._capture_poll_generation = getattr(self, "_capture_poll_generation", 0) + 1
        callback_id = getattr(self, "_capture_poll_after_id", None)
        self._capture_poll_after_id = None
        if callback_id is not None:
            self.root.after_cancel(callback_id)

    def _capture_finished(self, result: dict[str, Any], generation: int | None = None) -> None:
        if getattr(self, "_closed", False) or (
            generation is not None and generation != self._capture_poll_generation
        ):
            return
        self._stop_capture_polling()
        if result.get("fresh_capture") is not True or result.get("process_attached") is not True:
            self._handle_error(RuntimeError("本次结果缺少实时捕获证明，已拒绝显示旧缓存密钥"))
            return
        if result.get("official_wechat_verified") is not True:
            self._handle_error(RuntimeError("尚未确认腾讯官方微信恢复，已拒绝显示提取成功；请保留恢复状态与备份。"))
            return
        self._show_success(result.get("db_key"))

    def _show_success(self, key: Any) -> None:
        self.current_key = validate_database_key(key)
        self.key_var.set(mask_database_key(self.current_key))
        self.stage = "success"
        self.status_var.set("密钥已获取并通过数据库校验")
        self.detail_var.set(
            "本次密钥来自刚刚完成的实时登录捕获；临时调试微信已关闭，腾讯原签名微信已恢复。"
            "你可以点击下方按钮复制密钥，或打开本机受限缓存位置。"
        )
        self.primary_button.configure(text="复制密钥")
        self.copy_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _cancel(self) -> None:
        if self._busy:
            return
        if not messagebox.askokcancel("取消并恢复", "将关闭临时微信并恢复腾讯原签名版本，是否继续？"):
            return
        self._stop_capture_polling()
        self._run_task(
            lambda: cancel_capture(self.wechat_var.get(), self.work_root_var.get()),
            self._cancelled,
            status="正在恢复腾讯原签名微信…",
        )

    def _cancelled(self, result: dict[str, Any]) -> None:
        self._stop_capture_polling()
        if result.get("official_wechat_verified") is not True:
            self._handle_error(RuntimeError("尚未确认腾讯官方微信；恢复状态与备份均需保留。"))
            return
        self.stage = "idle"
        restored = result.get("official_wechat_restored") is True
        self.status_var.set("已取消并恢复腾讯原签名微信" if restored else "已取消，当前腾讯官方签名已确认")
        detail = "可以重新检查环境并开始提取。" if restored else "本次未替换当前微信，可以重新检查环境并开始提取。"
        if self.last_error:
            detail += f"\n上次错误：{self.last_error}"
        self.detail_var.set(detail)
        self.primary_button.configure(text="检查环境并开始")
        self.cancel_button.configure(state="disabled")
        if self._closing_after_cleanup:
            self._destroy_window()

    def _check_pending_capture(self) -> None:
        try:
            status = capture_status(self.wechat_var.get())
        except Exception:
            status = {"pending": True, "stage": "invalid"}
        if self._show_recovery_conflict(status):
            return
        if status.get("pending"):
            self.stage = "prepared"
            self.status_var.set("发现上次未完成的临时重签状态")
            self.detail_var.set("请先点击“取消并恢复微信”，确认腾讯原签名版本恢复后再开始新的提取。")
            self.primary_button.configure(state="disabled", text="等待恢复")
            self.cancel_button.configure(state="normal")

    def _show_recovery_conflict(self, status: dict[str, Any], message: str = "") -> bool:
        if not status.get("pending"):
            return False
        recovery_stage = status.get("stage")
        if recovery_stage == "external_install_conflict":
            self.stage = "external_install_conflict"
            self.status_var.set("微信安装已变化，未执行旧版恢复")
            self.detail_var.set(
                (f"{message}\n" if message else "")
                + "可点击“以当前版本重新开始”：重新验证当前腾讯官方版并建立新备份。旧备份和保护副本会保留，不会用旧版覆盖当前安装。"
            )
            self.primary_button.configure(state="normal", text="以当前版本重新开始")
            self.cancel_button.configure(state="disabled")
            return True
        if recovery_stage in {"recovery_blocked", "invalid"}:
            self.stage = "recovery_blocked"
            self.status_var.set("应用身份待确认，已停止自动处理")
            self.detail_var.set(
                (f"{message}\n" if message else "")
                + "当前应用无法安全归属本次事务，未覆盖安装。请先确认或重新安装所需的腾讯官方版，再重新打开工具检查；旧备份和恢复状态会保留。"
            )
            self.primary_button.configure(state="disabled", text="需要手动处理")
            self.cancel_button.configure(state="disabled")
            return True
        return False

    def _copy_key(self) -> None:
        if not self.current_key:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_key)
        self.status_var.set("密钥已复制到剪贴板")

    @staticmethod
    def _open_key_location() -> None:
        path = Path.home() / ".wcdb-key-tool"
        path.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["/usr/bin/open", str(path)])

    def _show_wechat(self) -> None:
        if getattr(self, "_closed", False):
            return
        wechat_app = Path(self.wechat_var.get().strip() or DEFAULT_WECHAT_APP).expanduser()
        if not wechat_app.is_dir():
            messagebox.showerror("WeData 密钥提取器", f"微信应用不存在: {wechat_app}")
            return
        subprocess.Popen(
            ["/usr/bin/open", str(wechat_app)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _hide_wechat(self) -> bool:
        """Hide the selected WeChat process without relying on its AppleEvent handler."""

        wechat_app = Path(self.wechat_var.get().strip() or DEFAULT_WECHAT_APP).expanduser()
        executable = wechat_app / "Contents" / "MacOS" / "WeChat"
        try:
            processes = subprocess.run(
                ["/usr/bin/pgrep", "-f", f"^{re.escape(str(executable))}$"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            pids = [line.strip() for line in processes.stdout.splitlines() if line.strip().isdigit()]
            if not pids:
                return False
            script = (
                "ObjC.import('AppKit'); "
                f"const app = $.NSRunningApplication.runningApplicationWithProcessIdentifier({int(pids[0])}); "
                "if (!app || !app.hide()) { throw new Error('unable to hide WeChat'); }"
            )
            result = subprocess.run(
                ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return False

    @staticmethod
    def _open_security_settings() -> None:
        # Open the settings app only; no trust exceptions or security options
        # are changed, and no confirmation is automated.
        subprocess.Popen(["/usr/bin/open", "-b", "com.apple.systempreferences"])

    @staticmethod
    def _open_full_disk_access() -> None:
        subprocess.Popen(
            [
                "/usr/bin/open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            ]
        )

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showinfo("操作进行中", "当前操作尚未结束，请等待完成或系统返回错误后再关闭。")
            return
        try:
            status = capture_status(self.wechat_var.get())
        except Exception:
            status = {"pending": True, "stage": "invalid"}
        if status.get("pending") and status.get("stage") in {"external_install_conflict", "recovery_blocked", "invalid"}:
            if messagebox.askokcancel("保留当前微信并退出", "恢复尚未完成。关闭工具不会替换当前微信，旧备份和恢复状态都会保留。是否退出？"):
                self._destroy_window()
            return
        if not status.get("pending"):
            self._destroy_window()
            return
        if not messagebox.askokcancel("先恢复微信", "当前微信处于临时调试状态。关闭前必须恢复腾讯原签名版本。"):
            return
        self._closing_after_cleanup = True
        self._stop_capture_polling()
        self._run_task(
            lambda: cancel_capture(self.wechat_var.get(), self.work_root_var.get()),
            self._cancelled,
            status="关闭前正在恢复腾讯原签名微信…",
        )

    def _destroy_window(self) -> None:
        self._closed = True
        self._stop_capture_polling()
        self.root.destroy()

    def _handle_error(self, error: Exception) -> None:
        if getattr(self, "_closed", False):
            return
        self._stop_capture_polling()
        message = str(error)
        code = str(getattr(error, "code", "unclassified_error") or "unclassified_error")
        safe_message = message.replace(str(Path.home()), "<HOME>")
        safe_message = re.sub(r"\b[0-9a-fA-F]{64}\b", "<REDACTED_KEY>", safe_message)
        self.last_error = f"[{code}] {safe_message}"
        print(
            f"WEDATA_UI_ERROR stage={self.stage} code={code} message={safe_message}",
            file=sys.stderr,
            flush=True,
        )
        try:
            status = capture_status(self.wechat_var.get())
        except Exception:
            status = {"pending": True, "stage": "invalid"}
        if code in {"in_place_debug_identity_unknown", "official_restore_staging_conflict"}:
            status = {**status, "pending": True, "stage": "recovery_blocked"}
        handled_conflict = self._show_recovery_conflict(status, message)
        if handled_conflict:
            pass
        elif status.get("pending"):
            self.stage = "prepared"
            self.status_var.set("操作失败，请先恢复微信")
            self.detail_var.set(f"{message}\n请点击“取消并恢复微信”，确认恢复后再重新开始。")
            self.primary_button.configure(state="disabled", text="等待恢复")
            self.cancel_button.configure(state="normal")
        else:
            self.stage = "idle"
            self.status_var.set("提取失败，可以重新开始")
            self.detail_var.set(message)
            self.primary_button.configure(state="normal", text="重新开始")
            self.cancel_button.configure(state="disabled")
        if self._closing_after_cleanup:
            self._closing_after_cleanup = False
        messagebox.showerror("WeData 密钥提取器", message)


def main() -> None:
    root = tk.Tk()
    KeyExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
