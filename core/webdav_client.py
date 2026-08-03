"""
WebDAV客户端模块 - 使用 webdavclient3 库封装WebDAV操作
"""

import os
import logging
import posixpath
import threading
from pathlib import PurePosixPath
from typing import Optional, Callable
from webdav3.client import Client
from webdav3.exceptions import WebDavException


class WebDAVClient:
    """WebDAV客户端封装"""

    TIMEOUT_SECONDS = 10

    def __init__(self, base_url: str, username: str, password: str,
                 log_callback: Optional[Callable] = None):
        """
        初始化WebDAV客户端

        Args:
            base_url: WebDAV服务器地址
            username: 用户名
            password: 密码
            log_callback: 日志回调函数，用于将日志输出到UI
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.connected = False
        self.remote_path = "Finalshell_BackUp"
        self.sync_remote_path = f"{self.remote_path}/sync"
        self.client: Optional[Client] = None
        self._client_options: Optional[dict] = None
        self._download_clients = threading.local()
        self.log_callback = log_callback
        self._known_directories: set[str] = set()
        # 缓存文件列表（用于不支持 list 方法的 WebDAV）
        self._cached_files: list = []

    def _log(self, message: str, level: str = "info"):
        """输出日志到回调函数"""
        if isinstance(message, bytes):
            try:
                message = message.decode('utf-8')
            except:
                message = message.decode('latin-1', errors='ignore')

        if self.log_callback:
            self.log_callback(message)
        else:
            if level == "error":
                logging.error(message)
            elif level == "warning":
                logging.warning(message)
            else:
                logging.info(message)

    def _parse_error(self, error) -> str:
        """解析错误信息，提供更友好的错误提示"""
        error_str = str(error)

        if "401" in error_str:
            return "认证失败：用户名或密码错误"
        elif "403" in error_str:
            return "权限拒绝：坚果云请使用「应用密码」而非登录密码。\n获取方式：坚果云网页 → 账户信息 → 安全选项 → 第三方应用管理 → 添加应用密码"
        elif "404" in error_str:
            return "路径不存在：请检查WebDAV地址是否正确"
        elif "405" in error_str:
            return "方法不被允许：该服务器可能不支持WebDAV协议"
        elif "500" in error_str:
            return "服务器内部错误"
        elif "503" in error_str:
            return "服务不可用：服务器可能正在维护"
        elif "Request to" in error_str and "failed with code" in error_str:
            import re
            match = re.search(r'code (\d+)', error_str)
            if match:
                code = match.group(1)
                return f"HTTP错误 {code}：连接被拒绝"

        return error_str

    def connect(self) -> tuple[bool, str]:
        """
        连接并验证WebDAV服务器

        Returns:
            (success, message) 元组
        """
        try:
            self._log(f"正在连接WebDAV服务器: {self.base_url}")
            self._log(f"用户名: {self.username}")

            options = {
                'webdav_hostname': self.base_url,
                'webdav_login': self.username,
                'webdav_password': self.password,
                'webdav_timeout': self.TIMEOUT_SECONDS,
            }

            self._client_options = options.copy()
            self.client = Client(options)

            self._log("验证连接...")
            if not self.client.check('/'):
                raise RuntimeError("WebDAV根目录不可访问")

            self._log(f"确保备份目录存在: {self.remote_path}")
            if not self._ensure_directory_exists(self.remote_path):
                raise RuntimeError(f"无法访问或创建备份目录: {self.remote_path}")

            self.connected = True
            self._log("WebDAV连接成功")
            return True, "连接成功"

        except WebDavException as e:
            error_msg = f"WebDAV错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg
        except Exception as e:
            error_msg = f"连接错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg

    def _ensure_directory_exists(self, path: str) -> bool:
        """
        确保远程目录存在
        
        Returns:
            目录存在或创建成功时返回 True
        """
        if path in self._known_directories:
            return True

        try:
            self.client.list(path)
            self._known_directories.add(path)
            self._log(f"目录已存在: {path}")
            return True
        except Exception:
            try:
                self.client.mkdir(path)
                self._known_directories.add(path)
                self._log(f"目录已创建: {path}")
                return True
            except Exception as e:
                error_msg = f"创建目录失败: {self._parse_error(e)}"
                self._log(error_msg, "error")
                return False

    @staticmethod
    def _normalize_remote_path(remote_path: str) -> str:
        """将远程路径规范化为 WebDAV 使用的 POSIX 相对路径。"""
        normalized = posixpath.normpath(remote_path.replace("\\", "/")).strip("/")
        if not normalized or normalized == "." or normalized.startswith("../"):
            raise ValueError(f"无效的远程路径: {remote_path}")
        return normalized

    def ensure_remote_directory(self, remote_path: str) -> tuple[bool, str]:
        """逐级确保指定 WebDAV 目录存在。"""
        if not self.client or not self.connected:
            return False, "WebDAV未连接"

        try:
            normalized = self._normalize_remote_path(remote_path)
            current = ""
            for part in normalized.split("/"):
                current = posixpath.join(current, part)
                if not self._ensure_directory_exists(current):
                    return False, f"无法访问或创建目录: {current}"
            return True, "目录已就绪"
        except Exception as error:
            message = f"准备远程目录失败: {self._parse_error(error)}"
            self._log(message, "error")
            return False, message

    def list_remote_tree(
        self, remote_path: str
    ) -> tuple[bool, str, dict[str, dict], set[str]]:
        """
        递归列出远程目录。

        Returns:
            (success, message, files, directories)，文件和目录均以 remote_path
            为基准使用 POSIX 相对路径。
        """
        if not self.client or not self.connected:
            return False, "WebDAV未连接", {}, set()

        try:
            normalized = self._normalize_remote_path(remote_path)
            files: dict[str, dict] = {}
            directories: set[str] = set()
            pending = [(normalized, "")]

            while pending:
                current_remote, current_relative = pending.pop()
                entries = self.client.list(current_remote, get_info=True)
                for entry in entries:
                    raw_path = str(entry.get("path") or "").rstrip("/")
                    name = PurePosixPath(raw_path).name
                    if not name:
                        name = str(entry.get("name") or "").strip("/")
                    if not name or name in {".", ".."} or "/" in name or "\\" in name:
                        continue

                    relative_path = posixpath.join(current_relative, name)
                    if entry.get("isdir"):
                        if relative_path not in directories:
                            directories.add(relative_path)
                            pending.append(
                                (posixpath.join(current_remote, name), relative_path)
                            )
                    else:
                        files[relative_path] = entry

            return True, "远程目录读取成功", files, directories
        except Exception as error:
            message = f"读取远程目录失败: {self._parse_error(error)}"
            self._log(message, "error")
            return False, message, {}, set()

    def upload_path(self, local_path: str, remote_path: str) -> tuple[bool, str]:
        """上传文件到指定远程完整路径。"""
        if not self.client or not self.connected:
            return False, "WebDAV未连接"

        normalized = ""
        try:
            normalized = self._normalize_remote_path(remote_path)
            self.client.upload_sync(remote_path=normalized, local_path=local_path)
            self._log(f"同步上传成功: {normalized}")
            return True, "上传成功"
        except Exception as error:
            if normalized:
                self._forget_remote_directory(posixpath.dirname(normalized))
            message = f"同步上传失败: {self._parse_error(error)}"
            self._log(message, "error")
            return False, message

    def download_path(self, remote_path: str, local_path: str) -> tuple[bool, str]:
        """从指定远程完整路径下载文件。"""
        if not self.client or not self.connected:
            return False, "WebDAV未连接"

        try:
            normalized = self._normalize_remote_path(remote_path)
            # requests.Session 不保证多线程共享安全。每个拉取线程
            # 复用自己的 WebDAV Client，既隔离 Session 又保留连接池。
            download_client = self._get_download_client()
            download_client.download_sync(
                remote_path=normalized, local_path=local_path
            )
            self._log(f"同步下载成功: {normalized}")
            return True, "下载成功"
        except Exception as error:
            message = f"同步下载失败: {self._parse_error(error)}"
            self._log(message, "error")
            return False, message

    def _get_download_client(self) -> Client:
        """获取当前线程专用的下载客户端。"""
        download_client = getattr(self._download_clients, "client", None)
        if download_client is None:
            if self._client_options is None:
                # 兼容测试或外部直接注入 client 的用法。
                return self.client
            download_client = Client(self._client_options.copy())
            self._download_clients.client = download_client
        return download_client

    def delete_path(self, remote_path: str) -> tuple[bool, str]:
        """删除指定远程文件或目录。"""
        if not self.client or not self.connected:
            return False, "WebDAV未连接"

        try:
            normalized = self._normalize_remote_path(remote_path)
            self.client.clean(normalized)
            self._forget_remote_directory(normalized)
            self._log(f"同步删除成功: {normalized}")
            return True, "删除成功"
        except Exception as error:
            message = f"同步删除失败: {self._parse_error(error)}"
            self._log(message, "error")
            return False, message

    def _forget_remote_directory(self, remote_path: str) -> None:
        """清除目录缓存，使失败后的重试会重新确认远程目录。"""
        if not remote_path:
            return
        prefix = remote_path.rstrip("/") + "/"
        self._known_directories = {
            path
            for path in self._known_directories
            if path != remote_path and not path.startswith(prefix)
        }

    def _get_remote_path(self, filename: str) -> str:
        """获取远程文件完整路径"""
        return f"{self.remote_path}/{filename}"

    def list_files(self) -> tuple[bool, str, list]:
        """
        列出远程备份目录中的所有zip文件

        Returns:
            (success, message, files) 元组
        """
        try:
            self._log(f"正在获取文件列表: {self.remote_path}")

            try:
                files_info = self.client.list(self.remote_path, get_info=True)
                files = []

                for file_info in files_info:
                    filename = file_info.get('name', '')

                    if filename.endswith('.zip'):
                        size = file_info.get('size', 0)
                        if isinstance(size, str):
                            try:
                                size = int(size)
                            except:
                                size = 0

                        modified = file_info.get('modified', '')

                        files.append({
                            'filename': filename,
                            'size': size,
                            'modified': modified,
                            'path': f"{self.remote_path}/{filename}"
                        })

                self._cached_files = files

                self._log(f"获取文件列表成功，找到 {len(files)} 个zip文件")
                return True, "获取文件列表成功", files

            except Exception as list_error:
                warning_msg = f"list 方法不支持: {self._parse_error(list_error)}，使用缓存列表"
                self._log(warning_msg, "warning")
                return True, f"获取文件列表成功（使用缓存，共 {len(self._cached_files)} 个文件）", self._cached_files

        except WebDavException as e:
            error_msg = f"WebDAV错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg, []
        except Exception as e:
            error_msg = f"获取文件列表失败: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg, []

    def upload_file(self, local_path: str, remote_filename: str) -> tuple[bool, str]:
        """
        上传文件到WebDAV

        Args:
            local_path: 本地文件路径
            remote_filename: 远程文件名

        Returns:
            (success, message) 元组
        """
        try:
            remote_path = self._get_remote_path(remote_filename)
            self._log(f"正在上传文件: {remote_filename}")
            self.client.upload_sync(remote_path=remote_path, local_path=local_path)

            # 添加到缓存
            file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
            self._cached_files.append({
                'filename': remote_filename,
                'size': file_size,
                'modified': '',
                'path': remote_path
            })

            self._log(f"上传成功: {remote_filename} ({file_size / 1024 / 1024:.2f} MB)")
            return True, "上传成功"

        except WebDavException as e:
            error_msg = f"WebDAV错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg
        except Exception as e:
            error_msg = f"上传错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg

    def download_file(self, remote_filename: str, local_path: str) -> tuple[bool, str]:
        """
        从WebDAV下载文件

        Args:
            remote_filename: 远程文件名
            local_path: 本地保存路径

        Returns:
            (success, message) 元组
        """
        try:
            remote_path = self._get_remote_path(remote_filename)
            self._log(f"正在下载文件: {remote_filename}")
            self.client.download_sync(remote_path=remote_path, local_path=local_path)

            file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
            self._log(f"下载成功: {remote_filename} ({file_size / 1024 / 1024:.2f} MB)")
            return True, "下载成功"

        except WebDavException as e:
            error_msg = f"WebDAV错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg
        except Exception as e:
            error_msg = f"下载错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg

    def delete_file(self, remote_filename: str) -> tuple[bool, str]:
        """
        删除远程文件

        Args:
            remote_filename: 远程文件名

        Returns:
            (success, message) 元组
        """
        try:
            remote_path = self._get_remote_path(remote_filename)
            self._log(f"正在删除文件: {remote_filename}")
            self.client.clean(remote_path)

            # 从缓存中移除
            self._cached_files = [f for f in self._cached_files if f['filename'] != remote_filename]

            self._log(f"删除成功: {remote_filename}")
            return True, "删除成功"

        except WebDavException as e:
            error_msg = f"WebDAV错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg
        except Exception as e:
            error_msg = f"删除错误: {self._parse_error(e)}"
            self._log(error_msg, "error")
            return False, error_msg
