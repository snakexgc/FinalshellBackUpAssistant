"""
WebDAV配置界面模块
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, Tuple

from core import WebDAVClient
from utils import ConfigManager


class WebDAVFrame(ttk.LabelFrame):
    """WebDAV配置面板"""

    def __init__(self, master, on_connected: Optional[Callable] = None,
                 on_disconnected: Optional[Callable] = None,
                 log_callback: Optional[Callable] = None,
                 url_variable: Optional[tk.StringVar] = None,
                 username_variable: Optional[tk.StringVar] = None,
                 password_variable: Optional[tk.StringVar] = None,
                 save_callback: Optional[Callable] = None,
                 prepare_sync_directory: bool = False,
                 **kwargs):
        """
        初始化WebDAV配置面板

        Args:
            master: 父窗口
            on_connected: 连接成功回调
            on_disconnected: 断开连接回调
            log_callback: 日志回调函数
        """
        self.save_callback = save_callback
        self.prepare_sync_directory = prepare_sync_directory
        super().__init__(master, text="WebDAV 云端存储配置", **kwargs)

        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.log_callback = log_callback
        self.webdav_client: Optional[WebDAVClient] = None
        self.config_manager = ConfigManager()
        self.webdav_url = url_variable or tk.StringVar(
            value="https://dav.jianguoyun.com/dav/"
        )
        self.webdav_username = username_variable or tk.StringVar()
        self.webdav_password = password_variable or tk.StringVar()
        self._login_events: queue.SimpleQueue = queue.SimpleQueue()
        self._connecting = False

        self._create_widgets()
        self.after(100, self._drain_login_events)

    def _create_widgets(self):
        """创建界面组件"""
        ttk.Label(self, text="WebDAV地址:", width=12).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.url_entry = ttk.Entry(self, textvariable=self.webdav_url)
        self.url_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(self, text="用户名:", width=12).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.username_entry = ttk.Entry(self, textvariable=self.webdav_username)
        self.username_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(self, text="密码:", width=12).grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.password_entry = ttk.Entry(
            self, textvariable=self.webdav_password, show="*"
        )
        self.password_entry.grid(row=2, column=1, padx=5, pady=2, sticky="ew")

        login_frame = ttk.Frame(self)
        login_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.login_button = ttk.Button(
            login_frame, text="登录WebDAV", command=self.login
        )
        self.login_button.pack(side="left", padx=5)
        ttk.Button(login_frame, text="保存配置", command=self.save_config).pack(side="left", padx=5)
        self.webdav_status = tk.StringVar(value="未连接")
        self.status_label = ttk.Label(login_frame, textvariable=self.webdav_status, foreground="red")
        self.status_label.pack(side="left", padx=10)

        self.columnconfigure(1, weight=1)

    def load_saved_config(self) -> Optional[Tuple[str, str, str, str]]:
        """加载程序同级目录中上次保存的配置。

        Returns:
            (url, username, password, source_path) 元组，失败返回 None
        """
        config = self.config_manager.load_config()
        if config:
            url, username, password, source_path = config
            self.webdav_url.set(url)
            self.webdav_username.set(username)
            self.webdav_password.set(password)
            if self.log_callback:
                self.log_callback("已加载上次保存的配置")
            return url, username, password, source_path
        return None

    def load_bundled_config(self) -> Optional[Tuple[str, str, str, str]]:
        """兼容旧调用名称。"""
        return self.load_saved_config()

    def save_config(self):
        """保存当前 WebDAV 设置和 FinalShell 路径。"""
        if self.save_callback:
            success, message = self.save_callback(
                self.webdav_url.get(),
                self.webdav_username.get(),
                self.webdav_password.get(),
            )
        else:
            success, message = self.config_manager.save_config(
                self.webdav_url.get(),
                self.webdav_username.get(),
                self.webdav_password.get(),
                "",
            )

        if self.log_callback:
            self.log_callback(message)
        if success:
            messagebox.showinfo("保存成功", message)
        else:
            messagebox.showerror("保存失败", message)

    def login(self):
        """在后台线程登录 WebDAV，避免阻塞 Tk 主线程。"""
        if self._connecting:
            return

        url = self.webdav_url.get().strip()
        username = self.webdav_username.get().strip()
        password = self.webdav_password.get().strip()

        if not url:
            messagebox.showerror("错误", "请输入WebDAV地址")
            return
        if not username:
            messagebox.showerror("错误", "请输入用户名")
            return
        if not password:
            messagebox.showerror("错误", "请输入密码")
            return

        self.webdav_status.set("连接中...")
        self.status_label.config(foreground="#b36b00")
        self._set_connecting(True)

        threading.Thread(
            target=self._login_worker,
            args=(url, username, password),
            name="WebDAVLogin",
            daemon=True,
        ).start()

    def _login_worker(self, url: str, username: str, password: str) -> None:
        client = WebDAVClient(
            url,
            username,
            password,
            log_callback=self._queue_log,
        )
        success, message = client.connect()
        if success and self.prepare_sync_directory:
            success, message = client.ensure_remote_directory(
                f"{client.sync_remote_path}/conn"
            )
        self._login_events.put(("result", client, success, message))

    def _queue_log(self, message: str) -> None:
        self._login_events.put(("log", str(message)))

    def _drain_login_events(self) -> None:
        try:
            while True:
                event = self._login_events.get_nowait()
                if event[0] == "log":
                    if self.log_callback:
                        self.log_callback(event[1])
                else:
                    _, client, success, message = event
                    self._finish_login(client, success, message)
        except queue.Empty:
            pass

        try:
            self.after(100, self._drain_login_events)
        except tk.TclError:
            pass

    def _finish_login(
        self, client: WebDAVClient, success: bool, message: str
    ) -> None:
        self._set_connecting(False)
        if success:
            self.webdav_client = client
            self.webdav_status.set("已连接")
            self.status_label.config(foreground="green")

            if self.on_connected:
                self.on_connected(client)
        else:
            self.webdav_status.set("连接失败")
            self.status_label.config(foreground="red")
            self.webdav_client = None
            messagebox.showerror("连接失败", message)

    def _set_connecting(self, connecting: bool) -> None:
        self._connecting = connecting
        state = "disabled" if connecting else "normal"
        self.url_entry.config(state=state)
        self.username_entry.config(state=state)
        self.password_entry.config(state=state)
        self.login_button.config(
            state=state,
            text="正在连接..." if connecting else "登录WebDAV",
        )

    def get_client(self) -> Optional[WebDAVClient]:
        """获取WebDAV客户端实例"""
        return self.webdav_client

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.webdav_client is not None and self.webdav_client.connected

    def get_connection_info(self) -> dict:
        """获取连接信息"""
        return {
            'url': self.webdav_url.get(),
            'username': self.webdav_username.get(),
            'connected': self.is_connected()
        }
