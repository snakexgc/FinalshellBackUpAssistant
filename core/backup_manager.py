"""
备份管理模块 - 处理备份和恢复逻辑
"""

import os
import shutil
import zipfile
import tempfile
import logging
from datetime import datetime
from typing import Optional, Callable, List, Tuple

from .webdav_client import WebDAVClient


class BackupManager:
    """备份管理器"""

    def __init__(self, webdav_client: WebDAVClient, temp_dir: Optional[str] = None):
        """
        初始化备份管理器

        Args:
            webdav_client: WebDAV客户端实例
            temp_dir: 临时目录路径，如果为None则自动创建
        """
        self.webdav = webdav_client
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.logger = logging.getLogger(__name__)

    def get_backup_filename(self, backup_type: str) -> str:
        """
        生成备份文件名

        Args:
            backup_type: 备份类型

        Returns:
            备份文件名
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{timestamp}_{backup_type}.zip"

    def _add_to_zip(self, zipf: zipfile.ZipFile, src_config: Optional[str], 
                    src_conn: Optional[str], conn_prefix: str = 'conn') -> int:
        """
        添加文件到zip

        Args:
            zipf: ZipFile对象
            src_config: config.json源路径
            src_conn: conn文件夹源路径
            conn_prefix: conn在zip中的前缀

        Returns:
            添加的文件数量
        """
        count = 0
        if src_config and os.path.exists(src_config):
            zipf.write(src_config, 'config.json')
            count += 1

        if src_conn and os.path.exists(src_conn):
            for root, dirs, files in os.walk(src_conn):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.join(conn_prefix, os.path.relpath(file_path, src_conn))
                    zipf.write(file_path, arcname)
                    count += 1

        return count

    def full_backup(self, source_path: str, include_config: bool,
                    progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        本地完整备份：直接将本地的config.json和conn文件夹中的全部内容打包上传webdav

        Args:
            source_path: Finalshell安装目录
            include_config: 是否包含config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            src_config = os.path.join(source_path, "config.json")
            src_conn = os.path.join(source_path, "conn")

            if not os.path.exists(src_conn):
                return False, "源目录中找不到conn文件夹"

            backup_filename = self.get_backup_filename("完整备份")
            local_backup_path = os.path.join(self.temp_dir, backup_filename)

            if progress_callback:
                progress_callback("正在创建完整备份...")

            with zipfile.ZipFile(local_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                config_path = src_config if include_config else None
                count = self._add_to_zip(zipf, config_path, src_conn)

            size_mb = os.path.getsize(local_backup_path) / (1024 * 1024)
            self.logger.info(f"本地备份创建完成: {backup_filename} ({size_mb:.2f} MB, {count}个文件)")

            if progress_callback:
                progress_callback("正在上传到云端...")

            success, message = self.webdav.upload_file(local_backup_path, backup_filename)
            if not success:
                return False, f"上传到WebDAV失败: {message}"

            self._cleanup_temp_files([local_backup_path])
            return True, backup_filename

        except Exception as e:
            self.logger.error(f"完整备份失败: {str(e)}")
            return False, f"完整备份失败: {str(e)}"

    def local_priority_backup(self, source_path: str, base_filename: str, 
                               include_config: bool,
                               progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        本地优先备份：以选中的云端包为基准，用本地的config.json和conn替换掉基准包中的文件，
        同名文件直接用本地的替换掉

        Args:
            source_path: Finalshell安装目录
            base_filename: 基准备份文件名
            include_config: 是否包含config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            src_config = os.path.join(source_path, "config.json")
            src_conn = os.path.join(source_path, "conn")

            if not os.path.exists(src_conn):
                return False, "源目录中找不到conn文件夹"

            backup_filename = self.get_backup_filename("本地优先备份")
            local_backup_path = os.path.join(self.temp_dir, backup_filename)
            base_zip_path = os.path.join(self.temp_dir, f"base_{base_filename}")

            if progress_callback:
                progress_callback("正在下载基准备份...")

            success, message = self.webdav.download_file(base_filename, base_zip_path)
            if not success:
                return False, f"下载基准备份失败: {message}"

            if progress_callback:
                progress_callback("正在创建本地优先备份...")

            local_conn_files = set()
            if os.path.exists(src_conn):
                for root, dirs, files in os.walk(src_conn):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, src_conn)
                        local_conn_files.add(rel_path.replace('\\', '/'))

            with zipfile.ZipFile(local_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                with zipfile.ZipFile(base_zip_path, 'r') as base_zip:
                    for item in base_zip.namelist():
                        if item == 'config.json':
                            if include_config and os.path.exists(src_config):
                                zipf.write(src_config, 'config.json')
                            else:
                                data = base_zip.read(item)
                                zipf.writestr(item, data)
                        elif item.startswith('conn/'):
                            rel_path = item[5:]
                            if rel_path in local_conn_files:
                                local_file = os.path.join(src_conn, rel_path.replace('/', os.sep))
                                if os.path.exists(local_file):
                                    zipf.write(local_file, item)
                                else:
                                    data = base_zip.read(item)
                                    zipf.writestr(item, data)
                            else:
                                data = base_zip.read(item)
                                zipf.writestr(item, data)
                        else:
                            data = base_zip.read(item)
                            zipf.writestr(item, data)

                if include_config and os.path.exists(src_config):
                    if 'config.json' not in base_zip.namelist():
                        zipf.write(src_config, 'config.json')

                for rel_path in local_conn_files:
                    zip_item = f'conn/{rel_path}'
                    if zip_item not in base_zip.namelist():
                        local_file = os.path.join(src_conn, rel_path.replace('/', os.sep))
                        if os.path.exists(local_file):
                            zipf.write(local_file, zip_item)

            size_mb = os.path.getsize(local_backup_path) / (1024 * 1024)
            self.logger.info(f"本地优先备份创建完成: {backup_filename} ({size_mb:.2f} MB)")

            if progress_callback:
                progress_callback("正在上传到云端...")

            success, message = self.webdav.upload_file(local_backup_path, backup_filename)
            if not success:
                return False, f"上传到WebDAV失败: {message}"

            self._cleanup_temp_files([base_zip_path, local_backup_path])
            return True, backup_filename

        except Exception as e:
            self.logger.error(f"本地优先备份失败: {str(e)}")
            return False, f"本地优先备份失败: {str(e)}"

    def cloud_priority_backup(self, source_path: str, base_filename: str,
                              include_config: bool,
                              progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        云端优先备份：以选中的云端包为基准，用本地的config.json和conn替换掉基准包中的文件，
        同名文件以云端中的为准，不要替换

        Args:
            source_path: Finalshell安装目录
            base_filename: 基准备份文件名
            include_config: 是否包含config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            src_config = os.path.join(source_path, "config.json")
            src_conn = os.path.join(source_path, "conn")

            if not os.path.exists(src_conn):
                return False, "源目录中找不到conn文件夹"

            backup_filename = self.get_backup_filename("云端优先备份")
            local_backup_path = os.path.join(self.temp_dir, backup_filename)
            base_zip_path = os.path.join(self.temp_dir, f"base_{base_filename}")

            if progress_callback:
                progress_callback("正在下载基准备份...")

            success, message = self.webdav.download_file(base_filename, base_zip_path)
            if not success:
                return False, f"下载基准备份失败: {message}"

            if progress_callback:
                progress_callback("正在创建云端优先备份...")

            local_conn_files = set()
            if os.path.exists(src_conn):
                for root, dirs, files in os.walk(src_conn):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, src_conn)
                        local_conn_files.add(rel_path.replace('\\', '/'))

            with zipfile.ZipFile(local_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                with zipfile.ZipFile(base_zip_path, 'r') as base_zip:
                    base_items = set(base_zip.namelist())

                    for item in base_zip.namelist():
                        if item == 'config.json':
                            if include_config:
                                data = base_zip.read(item)
                                zipf.writestr(item, data)
                        else:
                            data = base_zip.read(item)
                            zipf.writestr(item, data)

                if include_config and os.path.exists(src_config):
                    if 'config.json' not in base_items:
                        zipf.write(src_config, 'config.json')

                for rel_path in local_conn_files:
                    zip_item = f'conn/{rel_path}'
                    if zip_item not in base_items:
                        local_file = os.path.join(src_conn, rel_path.replace('/', os.sep))
                        if os.path.exists(local_file):
                            zipf.write(local_file, zip_item)

            size_mb = os.path.getsize(local_backup_path) / (1024 * 1024)
            self.logger.info(f"云端优先备份创建完成: {backup_filename} ({size_mb:.2f} MB)")

            if progress_callback:
                progress_callback("正在上传到云端...")

            success, message = self.webdav.upload_file(local_backup_path, backup_filename)
            if not success:
                return False, f"上传到WebDAV失败: {message}"

            self._cleanup_temp_files([base_zip_path, local_backup_path])
            return True, backup_filename

        except Exception as e:
            self.logger.error(f"云端优先备份失败: {str(e)}")
            return False, f"云端优先备份失败: {str(e)}"

    def cloud_overwrite_restore(self, filename: str, target_path: str, 
                                 include_config: bool,
                                 progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        云端覆盖恢复：以选中的云端包为准，直接替换掉本地的config.json，
        然后删除本地conn文件夹中全部内容后，将云端的内容复制进conn文件夹中

        Args:
            filename: 备份文件名
            target_path: 目标恢复路径
            include_config: 是否恢复config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            local_zip_path = os.path.join(self.temp_dir, filename)

            if progress_callback:
                progress_callback("正在从云端下载备份...")

            success, message = self.webdav.download_file(filename, local_zip_path)
            if not success:
                return False, f"下载备份失败: {message}"

            if progress_callback:
                progress_callback("正在恢复文件...")

            dst_config = os.path.join(target_path, "config.json")
            dst_conn = os.path.join(target_path, "conn")

            with zipfile.ZipFile(local_zip_path, 'r') as zipf:
                if include_config and 'config.json' in zipf.namelist():
                    os.makedirs(os.path.dirname(dst_config), exist_ok=True)
                    with zipf.open('config.json') as src, open(dst_config, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    self.logger.info("恢复 config.json")

                conn_files = [f for f in zipf.namelist() if f.startswith('conn/')]
                if conn_files:
                    if os.path.exists(dst_conn):
                        self._remove_readonly(dst_conn)
                        shutil.rmtree(dst_conn, ignore_errors=True)
                    os.makedirs(dst_conn, exist_ok=True)

                    for file_path in conn_files:
                        zipf.extract(file_path, os.path.dirname(dst_conn))
                    self.logger.info(f"恢复 conn 文件夹: {len(conn_files)} 个文件")

            self._cleanup_temp_files([local_zip_path])
            return True, "恢复成功"

        except Exception as e:
            self.logger.error(f"云端覆盖恢复失败: {str(e)}")
            return False, f"云端覆盖恢复失败: {str(e)}"

    def cloud_priority_restore(self, filename: str, target_path: str,
                                include_config: bool,
                                progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        云端优先恢复：以选中的云端包为基准，用云端的config.json和conn替换掉基准包中的文件，
        同名文件直接用本地的替换掉，不同名则新增进去

        Args:
            filename: 备份文件名
            target_path: 目标恢复路径
            include_config: 是否恢复config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            local_zip_path = os.path.join(self.temp_dir, filename)

            if progress_callback:
                progress_callback("正在从云端下载备份...")

            success, message = self.webdav.download_file(filename, local_zip_path)
            if not success:
                return False, f"下载备份失败: {message}"

            if progress_callback:
                progress_callback("正在恢复文件...")

            dst_config = os.path.join(target_path, "config.json")
            dst_conn = os.path.join(target_path, "conn")

            with zipfile.ZipFile(local_zip_path, 'r') as zipf:
                if include_config and 'config.json' in zipf.namelist():
                    os.makedirs(os.path.dirname(dst_config), exist_ok=True)
                    with zipf.open('config.json') as src, open(dst_config, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    self.logger.info("恢复 config.json")

                conn_files = [f for f in zipf.namelist() if f.startswith('conn/')]
                if conn_files:
                    os.makedirs(dst_conn, exist_ok=True)

                    local_conn_files = set()
                    if os.path.exists(dst_conn):
                        for root, dirs, files in os.walk(dst_conn):
                            for file in files:
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(file_path, dst_conn)
                                local_conn_files.add(rel_path.replace('\\', '/'))

                    for file_path in conn_files:
                        rel_path = file_path[5:]
                        if rel_path not in local_conn_files:
                            zipf.extract(file_path, os.path.dirname(dst_conn))
                            self.logger.info(f"新增文件: {rel_path}")

            self._cleanup_temp_files([local_zip_path])
            return True, "恢复成功"

        except Exception as e:
            self.logger.error(f"云端优先恢复失败: {str(e)}")
            return False, f"云端优先恢复失败: {str(e)}"

    def local_priority_restore(self, filename: str, target_path: str,
                                include_config: bool,
                                progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        本地优先恢复：以选中的云端包为基准，用云端的config.json和conn替换掉基准包中的文件，
        同名文件以本地的为准，不要替换

        Args:
            filename: 备份文件名
            target_path: 目标恢复路径
            include_config: 是否恢复config.json
            progress_callback: 进度回调函数

        Returns:
            (success, message) 元组
        """
        try:
            local_zip_path = os.path.join(self.temp_dir, filename)

            if progress_callback:
                progress_callback("正在从云端下载备份...")

            success, message = self.webdav.download_file(filename, local_zip_path)
            if not success:
                return False, f"下载备份失败: {message}"

            if progress_callback:
                progress_callback("正在恢复文件...")

            dst_config = os.path.join(target_path, "config.json")
            dst_conn = os.path.join(target_path, "conn")

            with zipfile.ZipFile(local_zip_path, 'r') as zipf:
                if include_config and 'config.json' in zipf.namelist():
                    if not os.path.exists(dst_config):
                        os.makedirs(os.path.dirname(dst_config), exist_ok=True)
                        with zipf.open('config.json') as src, open(dst_config, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        self.logger.info("新增 config.json")

                conn_files = [f for f in zipf.namelist() if f.startswith('conn/')]
                if conn_files:
                    os.makedirs(dst_conn, exist_ok=True)

                    local_conn_files = set()
                    if os.path.exists(dst_conn):
                        for root, dirs, files in os.walk(dst_conn):
                            for file in files:
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(file_path, dst_conn)
                                local_conn_files.add(rel_path.replace('\\', '/'))

                    for file_path in conn_files:
                        rel_path = file_path[5:]
                        if rel_path not in local_conn_files:
                            zipf.extract(file_path, os.path.dirname(dst_conn))
                            self.logger.info(f"新增文件: {rel_path}")

            self._cleanup_temp_files([local_zip_path])
            return True, "恢复成功"

        except Exception as e:
            self.logger.error(f"本地优先恢复失败: {str(e)}")
            return False, f"本地优先恢复失败: {str(e)}"

    def delete_backup(self, filename: str) -> Tuple[bool, str]:
        """
        删除备份文件

        Args:
            filename: 备份文件名

        Returns:
            (success, message) 元组
        """
        return self.webdav.delete_file(filename)

    def get_backup_list(self) -> Tuple[bool, str, list]:
        """
        获取备份列表

        Returns:
            (success, message, files) 元组
        """
        return self.webdav.list_files()

    def _cleanup_temp_files(self, file_paths: list) -> None:
        """清理临时文件"""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    self.logger.warning(f"清理临时文件失败 {path}: {str(e)}")

    def _remove_readonly(self, path: str) -> None:
        """移除文件的只读属性"""
        import stat
        for root, dirs, files in os.walk(path):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    os.chmod(dir_path, stat.S_IWRITE)
                except Exception:
                    pass
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.chmod(file_path, stat.S_IWRITE)
                except Exception:
                    pass
        try:
            os.chmod(path, stat.S_IWRITE)
        except Exception:
            pass

    def cleanup(self) -> None:
        """清理临时目录"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"清理临时目录: {self.temp_dir}")
        except Exception as e:
            self.logger.warning(f"清理临时目录失败: {str(e)}")
