"""
WebDAV客户端模块 - 使用 webdavclient3 库封装WebDAV操作
"""

import os
import logging
from typing import Optional, Callable
from webdav3.client import Client
from webdav3.exceptions import WebDavException


class WebDAVClient:
    """WebDAV客户端封装"""

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
        self.client: Optional[Client] = None
        self.log_callback = log_callback
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
                'disable_check': True,
            }

            self.client = Client(options)

            self._log("验证连接...")
            self.client.check('/')

            self._log(f"确保备份目录存在: {self.remote_path}")
            self._ensure_directory_exists(self.remote_path)

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
            True 如果目录已存在，False 如果是新创建的
        """
        try:
            self.client.list(path)
            self._log(f"目录已存在: {path}")
            return True
        except Exception:
            try:
                self.client.mkdir(path)
                self._log(f"目录已创建: {path}")
                return False
            except Exception as e:
                error_msg = f"创建目录失败: {self._parse_error(e)}"
                self._log(error_msg, "error")
                return False

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
