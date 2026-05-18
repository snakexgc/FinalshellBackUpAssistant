"""
配置管理模块 - 读取内置WebDAV配置
"""

import json
import sys
from pathlib import Path
from typing import Optional, Tuple


class ConfigManager:
    """配置管理器 - 读取随程序打包的WebDAV配置"""

    CONFIG_FILE_NAME = "config.json"

    def __init__(self):
        self.config_file = self._get_config_path()

    def _get_config_path(self) -> Path:
        """获取内置配置文件路径"""
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS) / self.CONFIG_FILE_NAME
        return Path(__file__).resolve().parent.parent / self.CONFIG_FILE_NAME

    def load_config(self) -> Optional[Tuple[str, str, str, str]]:
        """
        加载内置配置

        Returns:
            (url, username, password, source_path) 元组，失败返回 None
        """
        try:
            if not self.config_file.exists():
                return None

            with open(self.config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            return (
                config_data.get("url", ""),
                config_data.get("username", ""),
                config_data.get("password", ""),
                config_data.get("source_path", "")
            )
        except Exception as e:
            print(f"加载配置失败: {e}")
            return None
