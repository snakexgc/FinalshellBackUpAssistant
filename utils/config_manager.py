"""应用程序配置的读取与保存。"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Union


class ConfigManager:
    """管理程序同级目录中的明文 JSON 配置。"""

    CONFIG_FILE_NAME = "FinalshellBackUpAssistant.json"
    LEGACY_CONFIG_FILE_NAME = "config.json"

    def __init__(self, config_file: Optional[Union[str, Path]] = None):
        self._explicit_config_file = config_file is not None
        self.config_file = (
            Path(config_file).resolve()
            if config_file is not None
            else self._get_config_path()
        )

    def _get_config_path(self) -> Path:
        """开发环境使用项目目录，打包后使用 exe 所在目录。"""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / self.CONFIG_FILE_NAME
        return Path(__file__).resolve().parent.parent / self.CONFIG_FILE_NAME

    def load_config(self) -> Optional[Tuple[str, str, str, str]]:
        """
        加载上次保存的配置。

        Returns:
            (url, username, password, source_path) 元组，文件不存在或无效时返回 None
        """
        try:
            config_file = self.config_file
            if not config_file.is_file():
                legacy_file = config_file.with_name(self.LEGACY_CONFIG_FILE_NAME)
                if self._explicit_config_file or not legacy_file.is_file():
                    return None
                config_file = legacy_file

            with config_file.open("r", encoding="utf-8-sig") as config_stream:
                config_data = json.load(config_stream)

            if not isinstance(config_data, dict):
                return None
            if not {"url", "username", "password", "source_path"} & set(config_data):
                # 避免程序恰好放在 FinalShell 目录时误读其 config.json。
                return None

            return (
                str(config_data.get("url", "")),
                str(config_data.get("username", "")),
                str(config_data.get("password", "")),
                str(config_data.get("source_path", "")),
            )
        except (OSError, ValueError, TypeError) as error:
            print(f"加载配置失败: {error}")
            return None

    def save_config(
        self,
        url: str,
        username: str,
        password: str,
        source_path: str,
    ) -> Tuple[bool, str]:
        """将配置以 UTF-8 JSON 原子写入程序同级目录。"""
        config_data = {
            "url": url.strip(),
            "username": username.strip(),
            "password": password,
            "source_path": source_path.strip(),
        }
        temp_file = self.config_file.with_name(f"{self.config_file.name}.tmp")

        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with temp_file.open("w", encoding="utf-8", newline="\n") as config_stream:
                json.dump(config_data, config_stream, ensure_ascii=False, indent=2)
                config_stream.write("\n")
                config_stream.flush()
                os.fsync(config_stream.fileno())
            os.replace(temp_file, self.config_file)
            return True, f"配置已保存到: {self.config_file}"
        except OSError as error:
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False, f"保存配置失败: {error}"
