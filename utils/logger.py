"""
日志工具模块
"""

import logging
import tkinter as tk
from tkinter import ttk


def setup_logging(level=logging.INFO):
    """
    设置日志配置
    
    Args:
        level: 日志级别
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


class TextHandler(logging.Handler):
    """
    自定义日志处理器，将日志输出到Tkinter文本框
    """
    
    def __init__(self, text_widget):
        """
        初始化日志处理器
        
        Args:
            text_widget: Tkinter文本框组件
        """
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        """
        输出日志记录
        
        Args:
            record: 日志记录
        """
        msg = self.format(record)
        self.text_widget.config(state="normal")
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.config(state="disabled")
        self.text_widget.see(tk.END)


class LogFrame(ttk.LabelFrame):
    """
    日志显示面板
    """
    
    def __init__(self, master, **kwargs):
        """
        初始化日志面板
        
        Args:
            master: 父窗口
        """
        super().__init__(master, text="操作日志", **kwargs)
        
        self._create_widgets()
    
    def _create_widgets(self):
        """创建界面组件"""
        self.log_text = tk.Text(self, height=8, state="disabled")
        self.log_text.pack(padx=5, pady=5, fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # 创建日志处理器
        self.log_handler = TextHandler(self.log_text)
        logging.getLogger().addHandler(self.log_handler)
    
    def log(self, message: str):
        """
        添加日志消息
        
        Args:
            message: 日志消息
        """
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state="disabled")
        self.log_text.see(tk.END)
    
    def clear(self):
        """清空日志"""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")
    
    def get_handler(self):
        """获取日志处理器"""
        return self.log_handler
