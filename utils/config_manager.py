"""
配置管理模块 - 存储WebDAV配置
"""

import json
from pathlib import Path
from typing import Optional, Tuple


class ConfigManager:
    """配置管理器 - 存储WebDAV配置"""

    CONFIG_DIR = Path.home() / ".finalshell_backup"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    LEGACY_CONFIG_FILE = CONFIG_DIR / "config.enc"

    def __init__(self):
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def save_config(self, url: str, username: str, password: str, source_path: str = "") -> bool:
        """
        保存配置

        Args:
            url: WebDAV地址
            username: 用户名
            password: 密码
            source_path: Finalshell安装目录

        Returns:
            是否保存成功
        """
        try:
            config_data = {
                "url": url,
                "username": username,
                "password": password,
                "source_path": source_path
            }

            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def load_config(self) -> Optional[Tuple[str, str, str, str]]:
        """
        加载配置

        Returns:
            (url, username, password, source_path) 元组，失败返回 None
        """
        try:
            if not self.CONFIG_FILE.exists():
                return None

            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
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

    def delete_config(self) -> bool:
        """
        删除配置文件

        Returns:
            是否删除成功
        """
        try:
            if self.CONFIG_FILE.exists():
                self.CONFIG_FILE.unlink()
            if self.LEGACY_CONFIG_FILE.exists():
                self.LEGACY_CONFIG_FILE.unlink()
            return True
        except Exception as e:
            print(f"删除配置失败: {e}")
            return False

    def has_config(self) -> bool:
        """
        检查是否存在配置文件

        Returns:
            是否存在配置文件
        """
        return self.CONFIG_FILE.exists() or self.LEGACY_CONFIG_FILE.exists()
