"""FinalShell 配置目录的 WebDAV 精确同步与本地文件监听。"""

from __future__ import annotations

import hashlib
import os
import posixpath
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .webdav_client import WebDAVClient


LOCAL_BASELINE = "local"
CLOUD_BASELINE = "cloud"


@dataclass(frozen=True)
class LocalSnapshot:
    """本地受管文件的内容摘要和目录集合。"""

    files: dict[str, str]
    directories: set[str]


class _FinalShellEventHandler(FileSystemEventHandler):
    def __init__(self, source_path: Path, callback: Callable[[], None]):
        super().__init__()
        self.source_path = source_path
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type in {"opened", "closed", "closed_no_write"}:
            return

        paths = [event.src_path]
        destination_path = getattr(event, "dest_path", None)
        if destination_path:
            paths.append(destination_path)

        if any(self._is_managed_path(path) for path in paths):
            self.callback()

    def _is_managed_path(self, raw_path: str) -> bool:
        try:
            relative = Path(raw_path).resolve().relative_to(self.source_path)
        except (OSError, ValueError):
            return False

        parts = relative.parts
        return bool(parts) and (
            parts == ("config.json",) or parts[0].lower() == "conn"
        )


class SyncManager:
    """执行首次镜像，并在本地变化后将最终状态实时推送到 WebDAV。"""

    def __init__(
        self,
        webdav: WebDAVClient,
        log_callback: Optional[Callable[[str], None]] = None,
        sync_complete_callback: Optional[Callable[[], None]] = None,
        debounce_seconds: float = 0.8,
    ):
        self.webdav = webdav
        self.log_callback = log_callback
        self.sync_complete_callback = sync_complete_callback
        self.debounce_seconds = debounce_seconds
        self.remote_root = webdav.sync_remote_path

        self.source_path: Optional[Path] = None
        self._snapshot = LocalSnapshot({}, {"conn"})
        self._observer: Optional[Observer] = None
        self._worker: Optional[threading.Thread] = None
        self._change_event = threading.Event()
        self._stop_event = threading.Event()
        self._sync_lock = threading.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, source_path: str, baseline: str) -> str:
        """
        完成首次镜像并启动监听。

        Returns:
            实际采用的基准。云端没有受管文件时始终返回 ``local``。
        """
        if baseline not in {LOCAL_BASELINE, CLOUD_BASELINE}:
            raise ValueError("同步基准必须是 local 或 cloud")
        if self._running:
            raise RuntimeError("同步监听已经启动")

        source = Path(source_path).resolve()
        self._validate_source(source)
        self.source_path = source
        self._stop_event.clear()
        self._change_event.clear()

        actual_baseline = self._perform_initial_sync(baseline)
        self._raise_if_stopping()
        self._snapshot = self._build_local_snapshot()

        event_handler = _FinalShellEventHandler(source, self.request_sync)
        observer = Observer()
        observer.schedule(event_handler, str(source), recursive=True)
        observer.start()
        self._observer = observer
        self._running = True

        self._worker = threading.Thread(
            target=self._sync_worker,
            name="FinalShellWebDAVSync",
            daemon=True,
        )
        self._worker.start()

        # 覆盖首次同步到监听启动之间的极短窗口。
        if self._build_local_snapshot() != self._snapshot:
            self.request_sync()

        self._log("本地文件监听已启动")
        return actual_baseline

    def stop(self) -> None:
        """停止文件监听和后台同步线程。"""
        self._stop_event.set()
        self._change_event.set()

        observer = self._observer
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)

        worker = self._worker
        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(timeout=5)

        self._observer = None
        self._worker = None
        self._running = False
        self._log("同步监听已停止")

    def request_sync(self) -> None:
        """通知后台线程本地受管内容已经变化。"""
        if not self._stop_event.is_set():
            self._change_event.set()

    def sync_local_changes(self) -> None:
        """立即将自上次成功同步以来的本地增删改推送到云端。"""
        if self.source_path is None:
            raise RuntimeError("尚未设置 FinalShell 目录")

        with self._sync_lock:
            current = self._build_local_snapshot()

            new_directories = current.directories - self._snapshot.directories
            changed_files = {
                relative
                for relative, digest in current.files.items()
                if self._snapshot.files.get(relative) != digest
            }
            deleted_files = set(self._snapshot.files) - set(current.files)
            deleted_directories = (
                self._snapshot.directories - current.directories - {"conn"}
            )

            # 先删除旧类型，正确处理“文件变目录”或“目录变文件”。
            for relative in sorted(
                deleted_files, key=lambda item: item.count("/"), reverse=True
            ):
                self._raise_if_stopping()
                self._delete_remote(relative)

            for relative in sorted(
                deleted_directories, key=lambda item: item.count("/"), reverse=True
            ):
                self._raise_if_stopping()
                self._delete_remote(relative)

            for relative in sorted(new_directories, key=lambda item: item.count("/")):
                self._raise_if_stopping()
                self._ensure_remote_directory(relative)

            for relative in sorted(changed_files):
                self._raise_if_stopping()
                self._ensure_remote_parent(relative)
                local_path = self._local_path(relative)
                self._upload(local_path, relative)

            self._snapshot = current

        if changed_files or deleted_files or new_directories or deleted_directories:
            self._log(
                "实时同步完成："
                f"上传 {len(changed_files)}，"
                f"删除文件 {len(deleted_files)}，"
                f"目录变化 {len(new_directories) + len(deleted_directories)}"
            )
            if self.sync_complete_callback:
                self.sync_complete_callback()

    def _perform_initial_sync(self, requested_baseline: str) -> str:
        self._log(f"正在准备云端同步目录 {self.remote_root} ...")
        success, message = self.webdav.ensure_remote_directory(self.remote_root)
        self._require_success(success, message)
        success, message = self.webdav.ensure_remote_directory(
            posixpath.join(self.remote_root, "conn")
        )
        self._require_success(success, message)

        remote_files, remote_directories = self._read_remote_tree()
        managed_remote_files = {
            path: info
            for path, info in remote_files.items()
            if self._is_managed_relative(path)
        }
        cloud_is_empty = not managed_remote_files

        actual_baseline = requested_baseline
        if cloud_is_empty:
            actual_baseline = LOCAL_BASELINE
            self._log("云端同步目录为空，已自动改用本地基准")

        if actual_baseline == CLOUD_BASELINE:
            self._log("正在以云端为基准替换本地 config.json 和 conn ...")
            self._mirror_cloud_to_local(
                managed_remote_files,
                {
                    path
                    for path in remote_directories
                    if self._is_managed_directory(path)
                },
            )
        else:
            self._log("正在以本地为基准替换云端 config.json 和 conn ...")
            self._mirror_local_to_cloud(remote_files, remote_directories)

        self._log(
            "首次同步完成，实际基准："
            + ("云端" if actual_baseline == CLOUD_BASELINE else "本地")
        )
        return actual_baseline

    def _mirror_cloud_to_local(
        self,
        remote_files: dict[str, dict],
        remote_directories: set[str],
    ) -> None:
        local = self._build_local_snapshot()
        target_directories = {"conn"} | remote_directories

        for relative in sorted(
            target_directories & set(local.files),
            key=lambda item: item.count("/"),
        ):
            self._local_path(relative).unlink(missing_ok=True)

        for relative in sorted(
            target_directories, key=lambda item: item.count("/")
        ):
            self._local_path(relative).mkdir(parents=True, exist_ok=True)

        # 全部下载并原子替换，避免下载失败后留下半个文件。
        for relative in sorted(remote_files):
            self._raise_if_stopping()
            destination = self._local_path(relative)
            if destination.is_dir():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temp_name = tempfile.mkstemp(
                prefix=".finalshell-sync-", dir=str(destination.parent)
            )
            os.close(file_descriptor)
            temp_path = Path(temp_name)
            try:
                success, message = self.webdav.download_path(
                    self._remote_path(relative), str(temp_path)
                )
                self._require_success(success, message)
                os.replace(temp_path, destination)
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

        for relative in sorted(set(local.files) - set(remote_files)):
            self._raise_if_stopping()
            local_path = self._local_path(relative)
            try:
                if local_path.is_file() or local_path.is_symlink():
                    local_path.unlink(missing_ok=True)
            except OSError as error:
                raise RuntimeError(f"删除本地文件失败 {relative}: {error}") from error

        extra_directories = local.directories - target_directories - {"conn"}
        for relative in sorted(
            extra_directories, key=lambda item: item.count("/"), reverse=True
        ):
            self._raise_if_stopping()
            local_path = self._local_path(relative)
            try:
                if local_path.is_dir():
                    shutil.rmtree(local_path)
            except OSError as error:
                raise RuntimeError(f"删除本地目录失败 {relative}: {error}") from error

    def _mirror_local_to_cloud(
        self,
        remote_files: dict[str, dict],
        remote_directories: set[str],
    ) -> None:
        local = self._build_local_snapshot()

        for relative in sorted(
            set(remote_files) - set(local.files),
            key=lambda item: item.count("/"),
            reverse=True,
        ):
            self._raise_if_stopping()
            self._delete_remote(relative)

        extra_directories = remote_directories - local.directories - {"conn"}
        for relative in sorted(
            extra_directories, key=lambda item: item.count("/"), reverse=True
        ):
            self._raise_if_stopping()
            self._delete_remote(relative)

        for relative in sorted(
            local.directories, key=lambda item: item.count("/")
        ):
            self._raise_if_stopping()
            self._ensure_remote_directory(relative)

        for relative in sorted(local.files):
            self._raise_if_stopping()
            self._ensure_remote_parent(relative)
            self._upload(self._local_path(relative), relative)

    def _build_local_snapshot(self) -> LocalSnapshot:
        if self.source_path is None:
            raise RuntimeError("尚未设置 FinalShell 目录")

        files: dict[str, str] = {}
        directories = {"conn"}
        config_path = self.source_path / "config.json"
        if config_path.is_file() and not config_path.is_symlink():
            files["config.json"] = self._file_digest(config_path)

        conn_path = self.source_path / "conn"
        if conn_path.is_dir():
            for root, directory_names, file_names in os.walk(
                conn_path, followlinks=False
            ):
                root_path = Path(root)
                directory_names[:] = [
                    name
                    for name in directory_names
                    if not (root_path / name).is_symlink()
                ]
                relative_root = root_path.relative_to(self.source_path)
                directories.add(relative_root.as_posix())

                for directory_name in directory_names:
                    relative_directory = (
                        root_path / directory_name
                    ).relative_to(self.source_path)
                    directories.add(relative_directory.as_posix())

                for file_name in file_names:
                    file_path = root_path / file_name
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    relative_file = file_path.relative_to(self.source_path).as_posix()
                    files[relative_file] = self._file_digest(file_path)

        return LocalSnapshot(files, directories)

    @staticmethod
    def _file_digest(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as file_stream:
            for chunk in iter(lambda: file_stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _read_remote_tree(self) -> tuple[dict[str, dict], set[str]]:
        success, message, files, directories = self.webdav.list_remote_tree(
            self.remote_root
        )
        self._require_success(success, message)
        return files, directories

    def _local_path(self, relative_path: str) -> Path:
        if self.source_path is None:
            raise RuntimeError("尚未设置 FinalShell 目录")
        normalized = self._normalize_relative(relative_path)
        return self.source_path.joinpath(*normalized.split("/"))

    def _remote_path(self, relative_path: str) -> str:
        return posixpath.join(
            self.remote_root, self._normalize_relative(relative_path)
        )

    def _ensure_remote_parent(self, relative_file: str) -> None:
        parent = posixpath.dirname(relative_file)
        if parent:
            self._ensure_remote_directory(parent)

    def _ensure_remote_directory(self, relative_directory: str) -> None:
        success, message = self.webdav.ensure_remote_directory(
            self._remote_path(relative_directory)
        )
        self._require_success(success, message)

    def _upload(self, local_path: Path, relative_path: str) -> None:
        success, message = self.webdav.upload_path(
            str(local_path), self._remote_path(relative_path)
        )
        self._require_success(success, message)

    def _delete_remote(self, relative_path: str) -> None:
        success, message = self.webdav.delete_path(
            self._remote_path(relative_path)
        )
        self._require_success(success, message)

    @staticmethod
    def _normalize_relative(relative_path: str) -> str:
        normalized = posixpath.normpath(relative_path.replace("\\", "/")).strip("/")
        if (
            not normalized
            or normalized == "."
            or normalized.startswith("../")
            or normalized == ".."
        ):
            raise ValueError(f"无效的同步相对路径: {relative_path}")
        return normalized

    @staticmethod
    def _is_managed_relative(relative_path: str) -> bool:
        try:
            normalized = SyncManager._normalize_relative(relative_path)
        except ValueError:
            return False
        return normalized == "config.json" or normalized.startswith("conn/")

    @staticmethod
    def _is_managed_directory(relative_path: str) -> bool:
        try:
            normalized = SyncManager._normalize_relative(relative_path)
        except ValueError:
            return False
        return normalized == "conn" or normalized.startswith("conn/")

    @staticmethod
    def _validate_source(source: Path) -> None:
        missing = []
        if not (source / "finalshell.exe").is_file():
            missing.append("finalshell.exe")
        if not (source / "config.json").is_file():
            missing.append("config.json")
        if not (source / "conn").is_dir():
            missing.append("conn 文件夹")
        if missing:
            raise ValueError(
                "不是有效的 FinalShell 安装目录，缺少: " + "、".join(missing)
            )

    def _sync_worker(self) -> None:
        while not self._stop_event.is_set():
            if not self._change_event.wait(timeout=0.5):
                continue
            if self._stop_event.is_set():
                break

            self._change_event.clear()
            deadline = time.monotonic() + self.debounce_seconds
            while not self._stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if self._change_event.wait(timeout=remaining):
                    self._change_event.clear()
                    deadline = time.monotonic() + self.debounce_seconds

            if self._stop_event.is_set():
                break

            try:
                self.sync_local_changes()
            except Exception as error:
                self._log(f"实时同步失败，将自动重试: {error}")
                if not self._stop_event.wait(timeout=3):
                    self._change_event.set()

    def _raise_if_stopping(self) -> None:
        if self._stop_event.is_set():
            raise RuntimeError("同步已停止")

    @staticmethod
    def _require_success(success: bool, message: str) -> None:
        if not success:
            raise RuntimeError(message)

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
