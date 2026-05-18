"""
WebDAV配置界面模块
"""

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
                 get_source_path_callback: Optional[Callable] = None, **kwargs):
        """
        初始化WebDAV配置面板

        Args:
            master: 父窗口
            on_connected: 连接成功回调
            on_disconnected: 断开连接回调
            log_callback: 日志回调函数
            get_source_path_callback: 获取源目录路径的回调函数
        """
        super().__init__(master, text="WebDAV 云端存储配置", **kwargs)

        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.log_callback = log_callback
        self.get_source_path_callback = get_source_path_callback
        self.webdav_client: Optional[WebDAVClient] = None
        self.config_manager = ConfigManager()

        self._create_widgets()

    def _create_widgets(self):
        """创建界面组件"""
        ttk.Label(self, text="WebDAV地址:", width=12).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.webdav_url = tk.StringVar(value="https://dav.jianguoyun.com/dav/")
        ttk.Entry(self, textvariable=self.webdav_url).grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(self, text="用户名:", width=12).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.webdav_username = tk.StringVar()
        ttk.Entry(self, textvariable=self.webdav_username).grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(self, text="密码:", width=12).grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.webdav_password = tk.StringVar()
        ttk.Entry(self, textvariable=self.webdav_password, show="*").grid(row=2, column=1, padx=5, pady=2, sticky="ew")

        login_frame = ttk.Frame(self)
        login_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        ttk.Button(login_frame, text="登录WebDAV", command=self.login).pack(side="left", padx=5)
        self.webdav_status = tk.StringVar(value="未连接")
        self.status_label = ttk.Label(login_frame, textvariable=self.webdav_status, foreground="red")
        self.status_label.pack(side="left", padx=10)

        config_frame = ttk.Frame(self)
        config_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=2, sticky="w")

        self.remember_config = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            config_frame,
            text="保存配置",
            variable=self.remember_config,
            command=self._on_remember_changed
        ).pack(side="left")

        ttk.Button(
            config_frame,
            text="删除配置",
            command=self._delete_config
        ).pack(side="left", padx=5)

        self.columnconfigure(1, weight=1)

    def load_saved_config(self) -> Optional[Tuple[str, str, str, str]]:
        """加载已保存的配置

        Returns:
            (url, username, password, source_path) 元组，失败返回 None
        """
        config = self.config_manager.load_config()
        if config:
            url, username, password, source_path = config
            self.webdav_url.set(url)
            self.webdav_username.set(username)
            self.webdav_password.set(password)
            self.remember_config.set(True)
            if self.log_callback:
                self.log_callback("已加载保存的配置")
            return url, username, password, source_path
        return None

    def _on_remember_changed(self):
        """记住配置选项变化时的处理"""
        if not self.remember_config.get():
            self.config_manager.delete_config()
            if self.log_callback:
                self.log_callback("已删除保存的配置")

    def _delete_config(self):
        """删除配置文件"""
        if self.config_manager.has_config():
            if messagebox.askyesno("确认", "确定要删除保存的配置文件吗？"):
                self.config_manager.delete_config()
                self.remember_config.set(False)
                self.webdav_url.set("https://dav.jianguoyun.com/dav/")
                self.webdav_username.set("")
                self.webdav_password.set("")
                if self.log_callback:
                    self.log_callback("已删除保存的配置文件")
        else:
            messagebox.showinfo("提示", "没有找到保存的配置文件")

    def login(self):
        """登录WebDAV服务器"""
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
        self.update()

        self.webdav_client = WebDAVClient(url, username, password, log_callback=self.log_callback)
        success, message = self.webdav_client.connect()

        if success:
            self.webdav_status.set("已连接")
            self.status_label.config(foreground="green")

            source_path = ""
            if self.get_source_path_callback:
                source_path = self.get_source_path_callback()

            if self.remember_config.get():
                if self.config_manager.save_config(url, username, password, source_path):
                    if self.log_callback:
                        self.log_callback("配置已保存到本地")
                else:
                    if self.log_callback:
                        self.log_callback("保存配置失败")

            if self.on_connected:
                self.on_connected(self.webdav_client)
        else:
            self.webdav_status.set("连接失败")
            self.status_label.config(foreground="red")
            self.webdav_client = None
            messagebox.showerror("连接失败", message)

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
