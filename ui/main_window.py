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
from .webdav_frame import WebDAVFrame
from .backup_frame import BackupFrame
from .decrypt_frame import DecryptFrame


TEMP_DIR_NAME = "temfsbup"


class MainWindow:
    """应用程序主窗口"""

    def __init__(self):
        """初始化主窗口"""
        self.root = tk.Tk()
        self.root.title("FinalShell 配置备份与解密工具 v3.1")
        self.root.geometry("1050x900")

        self.webdav_client: WebDAVClient = None
        self.temp_dir = self._init_temp_dir()

        self._create_widgets()
        self._setup_logging()

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
            log_callback=self._log_message
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
            log_callback=self._log_message
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

        self.decrypt_frame = DecryptFrame(self.notebook)
        self.notebook.add(self.backup_page, text="备份恢复")
        self.notebook.add(self.decrypt_frame, text="解密")
        self._load_bundled_config()

    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        self.log_handler = TextHandler(self.log_text)
        logging.getLogger().addHandler(self.log_handler)

    def _load_bundled_config(self):
        """加载内置配置"""
        config = self.webdav_frame.load_bundled_config()
        if config:
            url, username, password, source_path = config
            if source_path:
                self.backup_frame.set_source_path(source_path)

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
        self.root.update()

    def _on_closing(self):
        """窗口关闭时的处理"""
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
