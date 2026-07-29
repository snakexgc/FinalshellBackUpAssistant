"""FinalShell WebDAV 实时同步标签页。"""

import os
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from core import CLOUD_BASELINE, LOCAL_BASELINE, SyncManager, WebDAVClient
from .webdav_frame import WebDAVFrame


class SyncFrame(ttk.Frame):
    """同步配置、首次镜像、文件监听和 FinalShell 启动界面。"""

    def __init__(
        self,
        master,
        url_variable: tk.StringVar,
        username_variable: tk.StringVar,
        password_variable: tk.StringVar,
        source_variable: tk.StringVar,
        save_callback: Callable[[str, str, str], tuple[bool, str]],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.source_path = source_variable
        self.webdav_client: Optional[WebDAVClient] = None
        self.sync_manager: Optional[SyncManager] = None
        self._closing = False
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()

        self.webdav_frame = WebDAVFrame(
            self,
            on_connected=self._on_webdav_connected,
            log_callback=self._log,
            url_variable=url_variable,
            username_variable=username_variable,
            password_variable=password_variable,
            save_callback=save_callback,
            prepare_sync_directory=True,
        )
        self.webdav_frame.pack(fill="x", padx=20, pady=10)

        self._create_source_section()
        self._create_options_section()
        self._create_action_section()
        self._create_log_section()
        self._set_source_enabled(False)

        self._queue_job = self.after(100, self._drain_ui_queue)

    def _create_source_section(self) -> None:
        source_frame = ttk.LabelFrame(
            self, text="FinalShell 安装目录（finalshell.exe 所在位置）"
        )
        source_frame.pack(fill="x", padx=20, pady=5)

        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_path)
        self.source_entry.pack(
            side="left", padx=5, pady=7, fill="x", expand=True
        )
        self.browse_button = ttk.Button(
            source_frame, text="选择 finalshell.exe...", command=self._select_executable
        )
        self.browse_button.pack(side="right", padx=5, pady=7)

    def _create_options_section(self) -> None:
        options_frame = ttk.LabelFrame(self, text="首次同步基准")
        options_frame.pack(fill="x", padx=20, pady=5)

        self.baseline = tk.StringVar(value=CLOUD_BASELINE)
        self.cloud_radio = ttk.Radiobutton(
            options_frame,
            text="云端基准（云端完整替换本地）",
            variable=self.baseline,
            value=CLOUD_BASELINE,
        )
        self.cloud_radio.pack(anchor="w", padx=8, pady=3)
        self.local_radio = ttk.Radiobutton(
            options_frame,
            text="本地基准（本地完整替换云端）",
            variable=self.baseline,
            value=LOCAL_BASELINE,
        )
        self.local_radio.pack(anchor="w", padx=8, pady=3)
        ttk.Label(
            options_frame,
            text="云端没有 config.json 或 conn 文件时，会自动改用本地基准。",
            foreground="#666666",
        ).pack(anchor="w", padx=8, pady=(1, 6))

    def _create_action_section(self) -> None:
        action_frame = ttk.LabelFrame(self, text="同步控制")
        action_frame.pack(fill="x", padx=20, pady=5)

        button_frame = ttk.Frame(action_frame)
        button_frame.pack(pady=8)
        self.sync_button = ttk.Button(
            button_frame, text="启动同步", command=self._toggle_sync
        )
        self.sync_button.pack(side="left", padx=8)
        self.launch_button = ttk.Button(
            button_frame,
            text="启动 FinalShell 程序",
            command=self._launch_finalshell,
            state="disabled",
        )
        self.launch_button.pack(side="left", padx=8)

        self.status_variable = tk.StringVar(value="请先登录 WebDAV")
        self.status_label = ttk.Label(
            action_frame,
            textvariable=self.status_variable,
            anchor="center",
            background="#eeeeee",
        )
        self.status_label.pack(fill="x", padx=8, pady=(0, 8))

    def _create_log_section(self) -> None:
        log_frame = ttk.LabelFrame(self, text="同步日志")
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=14, state="disabled")
        self.log_text.grid(row=0, column=0, padx=(5, 0), pady=5, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        scrollbar.grid(row=0, column=1, padx=(0, 5), pady=5, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _on_webdav_connected(self, client: WebDAVClient) -> None:
        if self.sync_manager and self.sync_manager.running:
            self.sync_manager.stop()

        self.webdav_client = client
        self._set_source_enabled(True)
        self.sync_button.configure(state="normal", text="启动同步")
        self.launch_button.configure(state="disabled")
        self.status_variable.set("WebDAV 已连接，可以启动同步")
        self._log("WebDAV 登录成功，请确认 FinalShell 路径和首次同步基准")

    def _select_executable(self) -> None:
        initial_directory = self.source_path.get().strip()
        if not os.path.isdir(initial_directory):
            initial_directory = ""

        executable = filedialog.askopenfilename(
            title="选择 finalshell.exe",
            initialdir=initial_directory or None,
            filetypes=[("FinalShell 程序", "finalshell.exe"), ("EXE 程序", "*.exe")],
        )
        if not executable:
            return
        if Path(executable).name.lower() != "finalshell.exe":
            messagebox.showerror("选择错误", "请选择名为 finalshell.exe 的程序")
            return

        source = str(Path(executable).resolve().parent)
        if not self._validate_source(source):
            return
        self.source_path.set(source)
        self._log(f"FinalShell 安装目录已设置为: {source}")

    def _toggle_sync(self) -> None:
        if self.sync_manager and self.sync_manager.running:
            self._stop_sync_async()
        else:
            self._start_sync()

    def _start_sync(self) -> None:
        if not self.webdav_client or not self.webdav_client.connected:
            messagebox.showerror("无法同步", "请先登录 WebDAV")
            return

        source = self.source_path.get().strip()
        if not self._validate_source(source):
            return

        self.sync_button.configure(state="disabled")
        self.launch_button.configure(state="disabled")
        self._set_source_enabled(False)
        self._set_baseline_enabled(False)
        self.status_variable.set("正在执行首次同步，请勿启动 FinalShell...")
        self._log("开始首次同步")

        manager = SyncManager(
            self.webdav_client,
            log_callback=self._log,
            sync_complete_callback=self._on_realtime_sync_complete,
        )
        self.sync_manager = manager
        worker = threading.Thread(
            target=self._start_sync_worker,
            args=(manager, source, self.baseline.get()),
            name="FinalShellInitialSync",
            daemon=True,
        )
        worker.start()

    def _start_sync_worker(
        self, manager: SyncManager, source: str, baseline: str
    ) -> None:
        try:
            actual_baseline = manager.start(source, baseline)
        except Exception as error:
            try:
                manager.stop()
            except Exception:
                pass
            self._post_ui(self._on_sync_start_failed, manager, str(error))
            return
        self._post_ui(self._on_sync_started, manager, actual_baseline)

    def _on_sync_started(self, manager: SyncManager, actual_baseline: str) -> None:
        if manager is not self.sync_manager or self._closing:
            manager.stop()
            return
        self.baseline.set(actual_baseline)
        self.sync_button.configure(state="normal", text="停止同步")
        self.launch_button.configure(state="normal")
        baseline_text = "云端" if actual_baseline == CLOUD_BASELINE else "本地"
        self.status_variable.set(f"正在监听（首次同步使用{baseline_text}基准）")
        self._log("同步监听状态已就绪，现在可以启动 FinalShell")

    def _on_sync_start_failed(
        self, manager: SyncManager, error_message: str
    ) -> None:
        if manager is not self.sync_manager:
            return
        self.sync_manager = None
        self.sync_button.configure(state="normal", text="启动同步")
        self.launch_button.configure(state="disabled")
        self._set_source_enabled(self.webdav_client is not None)
        self._set_baseline_enabled(True)
        self.status_variable.set("同步启动失败")
        self._log(f"同步启动失败: {error_message}")
        messagebox.showerror("同步启动失败", error_message)

    def _stop_sync_async(self) -> None:
        manager = self.sync_manager
        if not manager:
            return
        self.sync_button.configure(state="disabled")
        self.launch_button.configure(state="disabled")
        self.status_variable.set("正在停止同步...")

        def stop_worker() -> None:
            manager.stop()
            self._post_ui(self._on_sync_stopped, manager)

        threading.Thread(
            target=stop_worker, name="FinalShellStopSync", daemon=True
        ).start()

    def _on_sync_stopped(self, manager: SyncManager) -> None:
        if manager is not self.sync_manager:
            return
        self.sync_manager = None
        self.sync_button.configure(state="normal", text="启动同步")
        self._set_source_enabled(self.webdav_client is not None)
        self._set_baseline_enabled(True)
        self.status_variable.set("同步已停止")

    def _launch_finalshell(self) -> None:
        if not self.sync_manager or not self.sync_manager.running:
            messagebox.showerror("无法启动", "请先启动同步并进入监听状态")
            return

        active_source = self.sync_manager.source_path
        if active_source is None:
            messagebox.showerror("无法启动", "同步监听没有有效的 FinalShell 路径")
            return
        executable = active_source / "finalshell.exe"
        if not executable.is_file():
            messagebox.showerror("无法启动", f"找不到程序: {executable}")
            return

        try:
            subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parent),
                close_fds=True,
            )
            self._log(f"已启动 FinalShell: {executable}")
        except OSError as error:
            messagebox.showerror("启动失败", str(error))
            self._log(f"启动 FinalShell 失败: {error}")

    def _on_realtime_sync_complete(self) -> None:
        self._post_ui(
            self.status_variable.set,
            f"正在监听（最近同步 {datetime.now().strftime('%H:%M:%S')}）",
        )

    def _validate_source(self, source_path: str) -> bool:
        source = Path(source_path)
        missing = []
        if not (source / "finalshell.exe").is_file():
            missing.append("finalshell.exe")
        if not (source / "config.json").is_file():
            missing.append("config.json")
        if not (source / "conn").is_dir():
            missing.append("conn 文件夹")
        if missing:
            messagebox.showerror(
                "FinalShell 路径无效",
                "所选目录缺少: " + "、".join(missing),
            )
            return False
        return True

    def _set_source_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.source_entry.configure(state=state)
        self.browse_button.configure(state=state)

    def _set_baseline_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.cloud_radio.configure(state=state)
        self.local_radio.configure(state=state)

    def _log(self, message: str) -> None:
        self._post_ui(self._append_log, str(message))

    def _append_log(self, message: str) -> None:
        if self._closing:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    def _post_ui(self, callback: Callable, *args) -> None:
        if not self._closing:
            self._ui_queue.put((callback, args))

    def _drain_ui_queue(self) -> None:
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        self._queue_job = self.after(100, self._drain_ui_queue)

    def cleanup(self) -> None:
        """窗口关闭时停止后台线程。"""
        self._closing = True
        try:
            self.after_cancel(self._queue_job)
        except (AttributeError, tk.TclError):
            pass
        if self.sync_manager:
            self.sync_manager.stop()
            self.sync_manager = None
