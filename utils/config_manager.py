"""
配置管理模块 - 加密存储WebDAV配置
使用机器特征绑定，确保配置只能在当前机器上使用
"""

import os
import json
import base64
import hashlib
import platform
import uuid
from pathlib import Path
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class ConfigManager:
    """配置管理器 - 加密存储WebDAV配置"""

    CONFIG_DIR = Path.home() / ".finalshell_backup"
    CONFIG_FILE = CONFIG_DIR / "config.enc"

    def __init__(self):
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def _get_machine_id(self) -> str:
        """
        获取机器唯一标识
        组合多个机器特征，确保唯一性和稳定性
        """
        features = []

        try:
            mac = uuid.getnode()
            features.append(str(mac))
        except:
            pass

        try:
            features.append(platform.node())
        except:
            pass

        try:
            features.append(platform.machine())
        except:
            pass

        try:
            if platform.system() == "Windows":
                import subprocess
                result = subprocess.run(
                    ["wmic", "csproduct", "get", "UUID"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    uuid_str = result.stdout.strip().split("\n")[-1].strip()
                    if uuid_str and uuid_str != "UUID":
                        features.append(uuid_str)
        except:
            pass

        machine_str = "|".join(features)
        return hashlib.sha256(machine_str.encode()).hexdigest()

    def _derive_key(self) -> bytes:
        """
        从机器ID派生加密密钥
        """
        machine_id = self._get_machine_id()
        salt = b"FinalshellBackup_Salt_2024"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
        return key

    def save_config(self, url: str, username: str, password: str, source_path: str = "") -> bool:
        """
        加密保存配置

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

            json_data = json.dumps(config_data, ensure_ascii=False)
            key = self._derive_key()
            fernet = Fernet(key)
            encrypted = fernet.encrypt(json_data.encode())

            with open(self.CONFIG_FILE, "wb") as f:
                f.write(encrypted)

            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def load_config(self) -> Optional[Tuple[str, str, str, str]]:
        """
        解密加载配置

        Returns:
            (url, username, password, source_path) 元组，失败返回 None
        """
        try:
            if not self.CONFIG_FILE.exists():
                return None

            with open(self.CONFIG_FILE, "rb") as f:
                encrypted = f.read()

            key = self._derive_key()
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted)

            config_data = json.loads(decrypted.decode())

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
        return self.CONFIG_FILE.exists()
