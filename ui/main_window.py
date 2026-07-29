"""
主窗口模块
"""

import os
import shutil
import logging
import tempfile
import tkinter as tk
from tkinter import ttk

from core import WebDAVClient
from utils import ConfigManager
from .webdav_frame import WebDAVFrame
from .backup_frame import BackupFrame
from .decrypt_frame import DecryptFrame
from .sync_frame import SyncFrame


TEMP_DIR_NAME = "temfsbup"


class MainWindow:
    """应用程序主窗口"""

    def __init__(self):
        """初始化主窗口"""
        self.root = tk.Tk()
        self.root.title("FinalShell 配置备份、同步与解密工具 v3.2")
        self.root.geometry("1050x900")

        self.webdav_client: WebDAVClient = None
        self.temp_dir = self._init_temp_dir()
        self.config_manager = ConfigManager()
        self.webdav_url = tk.StringVar(value="https://dav.jianguoyun.com/dav/")
        self.webdav_username = tk.StringVar()
        self.webdav_password = tk.StringVar()
        self.source_path = tk.StringVar(value="D:/finalshell")
        self._config_was_loaded = self._load_saved_config()

        self._create_widgets()
        self._setup_logging()
        if self._config_was_loaded:
            self._log_message("已从程序同级配置 JSON 加载上次保存的设置")

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _init_temp_dir(self) -> str:
        """初始化临时目录"""
        temp_base = tempfile.gettempdir()
        temp_dir = os.path.join(temp_base, TEMP_DIR_NAME)

        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def _cleanup_temp_dir(self):
        """清理临时目录"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def _create_widgets(self):
        """创建界面组件"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.backup_page = ttk.Frame(self.notebook)

        self.webdav_frame = WebDAVFrame(
            self.backup_page,
            on_connected=self._on_webdav_connected,
            log_callback=self._log_message,
            url_variable=self.webdav_url,
            username_variable=self.webdav_username,
            password_variable=self.webdav_password,
            save_callback=self._save_config,
        )
        self.webdav_frame.pack(fill="x", padx=20, pady=10)

        temp_frame = ttk.LabelFrame(self.backup_page, text="本地临时目录")
        temp_frame.pack(padx=20, pady=5, fill="x")

        self.temp_path_var = tk.StringVar(value=self.temp_dir)
        ttk.Entry(temp_frame, textvariable=self.temp_path_var, state="readonly").pack(
            side="left", padx=5, pady=5, fill="x", expand=True
        )
        ttk.Button(temp_frame, text="打开目录", command=self._open_temp_dir).pack(
            side="right", padx=5, pady=5
        )

        self.backup_frame = BackupFrame(
            self.backup_page,
            log_callback=self._log_message,
            source_variable=self.source_path,
        )
        self.backup_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.status_var = tk.StringVar(value="就绪")
        self.status_bar = ttk.Label(self.backup_page, textvariable=self.status_var, background="lightgray")
        self.status_bar.pack(fill="x", padx=20, pady=5)

        log_frame = ttk.LabelFrame(self.backup_page, text="操作日志")
        log_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=8, state="disabled")
        self.log_text.pack(padx=5, pady=5, fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        self.sync_frame = SyncFrame(
            self.notebook,
            url_variable=self.webdav_url,
            username_variable=self.webdav_username,
            password_variable=self.webdav_password,
            source_variable=self.source_path,
            save_callback=self._save_config,
        )
        self.decrypt_frame = DecryptFrame(self.notebook)
        self.notebook.add(self.sync_frame, text="同步")
        self.notebook.add(self.backup_page, text="备份恢复")
        self.notebook.add(self.decrypt_frame, text="解密")
        self.notebook.select(self.sync_frame)

    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        self.log_handler = TextHandler(self.log_text)
        logging.getLogger().addHandler(self.log_handler)

    def _load_saved_config(self) -> bool:
        """加载程序同级 JSON 中上次保存的设置。"""
        config = self.config_manager.load_config()
        if not config:
            return False

        url, username, password, source_path = config
        if url:
            self.webdav_url.set(url)
        self.webdav_username.set(username)
        self.webdav_password.set(password)
        if source_path:
            self.source_path.set(source_path)
        return True

    def _save_config(
        self, url: str, username: str, password: str
    ) -> tuple[bool, str]:
        """保存两页共用的 WebDAV 设置和 FinalShell 路径。"""
        return self.config_manager.save_config(
            url,
            username,
            password,
            self.source_path.get(),
        )

    def _on_webdav_connected(self, client: WebDAVClient):
        """WebDAV连接成功回调"""
        self.webdav_client = client
        self.backup_frame.set_webdav_client(client)
        self.status_var.set("WebDAV已连接")
        self._log_message("WebDAV连接成功，可以开始备份操作")

    def _open_temp_dir(self):
        """打开临时目录"""
        if os.path.exists(self.temp_dir):
            os.startfile(self.temp_dir)

    def _log_message(self, message: str):
        """添加日志消息"""
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state="disabled")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def _on_closing(self):
        """窗口关闭时的处理"""
        self.sync_frame.cleanup()
        self._cleanup_temp_dir()
        self.root.destroy()

    def run(self):
        """运行应用程序"""
        self.root.mainloop()


class TextHandler(logging.Handler):
    """自定义日志处理器，将日志输出到文本框"""

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.config(state="normal")
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.config(state="disabled")
        self.text_widget.see(tk.END)
