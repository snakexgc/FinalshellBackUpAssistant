import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.sync_manager import CLOUD_BASELINE, LOCAL_BASELINE, SyncManager
from utils.config_manager import ConfigManager


class FakeWebDAV:
    sync_remote_path = "Finalshell_BackUp/sync"

    def __init__(self, root: Path):
        self.root = root
        self.uploaded_paths = []

    def _path(self, remote_path: str) -> Path:
        parts = Path(remote_path.replace("\\", "/")).parts
        return self.root.joinpath(*parts)

    def ensure_remote_directory(self, remote_path: str):
        self._path(remote_path).mkdir(parents=True, exist_ok=True)
        return True, "ok"

    def list_remote_tree(self, remote_path: str):
        base = self._path(remote_path)
        files = {}
        directories = set()
        if base.exists():
            for item in base.rglob("*"):
                relative = item.relative_to(base).as_posix()
                if item.is_dir():
                    directories.add(relative)
                else:
                    files[relative] = {"size": item.stat().st_size}
        return True, "ok", files, directories

    def upload_path(self, local_path: str, remote_path: str):
        destination = self._path(remote_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        self.uploaded_paths.append(remote_path)
        return True, "ok"

    def download_path(self, remote_path: str, local_path: str):
        source = self._path(remote_path)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_path)
        return True, "ok"

    def delete_path(self, remote_path: str):
        target = self._path(remote_path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        return True, "ok"


class ConcurrentFakeWebDAV(FakeWebDAV):
    def __init__(self, root: Path):
        super().__init__(root)
        self._activity_lock = threading.Lock()
        self.active_downloads = 0
        self.max_active_downloads = 0

    def download_path(self, remote_path: str, local_path: str):
        with self._activity_lock:
            self.active_downloads += 1
            self.max_active_downloads = max(
                self.max_active_downloads, self.active_downloads
            )
        try:
            time.sleep(0.05)
            return super().download_path(remote_path, local_path)
        finally:
            with self._activity_lock:
                self.active_downloads -= 1


class SyncManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.local = self.base / "local"
        self.remote = self.base / "remote"
        self.local.mkdir()
        self.remote.mkdir()
        (self.local / "finalshell.exe").write_bytes(b"exe")
        self._write_json(
            self.local / "config.json",
            {
                "theme": "local",
                "cmd_history": [{"text": "local secret command"}],
                "file_history": [{"path": "D:/local/secret.txt"}],
            },
        )
        (self.local / "conn").mkdir()
        (self.local / "conn" / "local.json").write_text(
            "local-connection", encoding="utf-8"
        )
        self.webdav = FakeWebDAV(self.remote)
        self.manager = SyncManager(self.webdav, debounce_seconds=0.1)
        self.manager.source_path = self.local.resolve()

    def tearDown(self):
        self.manager.stop()
        self.temp_dir.cleanup()

    def remote_sync_path(self) -> Path:
        return self.remote / "Finalshell_BackUp" / "sync"

    @staticmethod
    def _write_json(path: Path, content: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(content, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_local_baseline_exactly_replaces_cloud(self):
        cloud = self.remote_sync_path()
        (cloud / "conn").mkdir(parents=True)
        self._write_json(cloud / "config.json", {"theme": "old-cloud"})
        (cloud / "conn" / "remote-only.json").write_text(
            "remove-me", encoding="utf-8"
        )

        actual = self.manager._perform_initial_sync(LOCAL_BASELINE)

        self.assertEqual(LOCAL_BASELINE, actual)
        cloud_config = self._read_json(cloud / "config.json")
        self.assertEqual("local", cloud_config["theme"])
        self.assertEqual([], cloud_config["cmd_history"])
        self.assertEqual([], cloud_config["file_history"])
        self.assertEqual(
            [{"text": "local secret command"}],
            self._read_json(self.local / "config.json")["cmd_history"],
        )
        self.assertEqual(
            [{"path": "D:/local/secret.txt"}],
            self._read_json(self.local / "config.json")["file_history"],
        )
        self.assertEqual(
            "local-connection",
            (cloud / "conn" / "local.json").read_text(encoding="utf-8"),
        )
        self.assertFalse((cloud / "conn" / "remote-only.json").exists())

    def test_cloud_baseline_exactly_replaces_local(self):
        cloud = self.remote_sync_path()
        (cloud / "conn" / "nested").mkdir(parents=True)
        self._write_json(
            cloud / "config.json",
            {
                "theme": "cloud",
                "cmd_history": [{"text": "cloud secret command"}],
                "file_history": [{"path": "/cloud/secret.txt"}],
            },
        )
        (cloud / "conn" / "cloud.json").write_text(
            "cloud-connection", encoding="utf-8"
        )

        actual = self.manager._perform_initial_sync(CLOUD_BASELINE)

        self.assertEqual(CLOUD_BASELINE, actual)
        local_config = self._read_json(self.local / "config.json")
        self.assertEqual("cloud", local_config["theme"])
        self.assertEqual(
            [{"text": "local secret command"}], local_config["cmd_history"]
        )
        self.assertEqual(
            [{"path": "D:/local/secret.txt"}], local_config["file_history"]
        )
        self.assertEqual(
            [], self._read_json(cloud / "config.json")["cmd_history"]
        )
        self.assertEqual(
            [], self._read_json(cloud / "config.json")["file_history"]
        )
        self.assertEqual(
            "cloud-connection",
            (self.local / "conn" / "cloud.json").read_text(encoding="utf-8"),
        )
        self.assertFalse((self.local / "conn" / "local.json").exists())

    def test_empty_cloud_falls_back_to_local_baseline(self):
        self.webdav.ensure_remote_directory("Finalshell_BackUp/sync/conn")

        actual = self.manager._perform_initial_sync(CLOUD_BASELINE)

        self.assertEqual(LOCAL_BASELINE, actual)
        cloud_config = self._read_json(self.remote_sync_path() / "config.json")
        self.assertEqual("local", cloud_config["theme"])
        self.assertEqual([], cloud_config["cmd_history"])
        self.assertEqual([], cloud_config["file_history"])

    def test_config_history_only_change_is_not_uploaded(self):
        self.manager._perform_initial_sync(LOCAL_BASELINE)
        self.manager._snapshot = self.manager._build_local_snapshot()
        uploads_before_change = len(self.webdav.uploaded_paths)

        config_path = self.local / "config.json"
        config = self._read_json(config_path)
        config["cmd_history"] = [
            {
                "active_time": 1785738492566,
                "index": 0,
                "text": "bash <(curl -Ls https://example.test/install.sh)",
                "type": "",
            }
        ]
        config["file_history"] = [{"path": "D:/changed/only-history.txt"}]
        self._write_json(config_path, config)
        self.manager.sync_local_changes()

        self.assertEqual(uploads_before_change, len(self.webdav.uploaded_paths))
        self.assertEqual(
            [], self._read_json(self.remote_sync_path() / "config.json")["cmd_history"]
        )
        self.assertEqual(
            [], self._read_json(self.remote_sync_path() / "config.json")["file_history"]
        )

    def test_other_config_change_uploads_with_empty_history(self):
        self.manager._perform_initial_sync(LOCAL_BASELINE)
        self.manager._snapshot = self.manager._build_local_snapshot()
        uploads_before_change = len(self.webdav.uploaded_paths)

        config_path = self.local / "config.json"
        config = self._read_json(config_path)
        config["theme"] = "changed"
        config["cmd_history"] = [{"text": "must not reach cloud"}]
        config["file_history"] = [{"path": "must-not-reach-cloud"}]
        self._write_json(config_path, config)
        self.manager.sync_local_changes()

        self.assertEqual(uploads_before_change + 1, len(self.webdav.uploaded_paths))
        cloud_config = self._read_json(self.remote_sync_path() / "config.json")
        self.assertEqual("changed", cloud_config["theme"])
        self.assertEqual([], cloud_config["cmd_history"])
        self.assertEqual([], cloud_config["file_history"])
        self.assertEqual(
            [{"text": "must not reach cloud"}],
            self._read_json(config_path)["cmd_history"],
        )
        self.assertEqual(
            [{"path": "must-not-reach-cloud"}],
            self._read_json(config_path)["file_history"],
        )

    def test_upload_adds_missing_history_field(self):
        self._write_json(self.local / "config.json", {"theme": "without-history"})

        self.manager._perform_initial_sync(LOCAL_BASELINE)

        self.assertEqual(
            [], self._read_json(self.remote_sync_path() / "config.json")["cmd_history"]
        )
        self.assertEqual(
            [], self._read_json(self.remote_sync_path() / "config.json")["file_history"]
        )

    def test_cloud_files_are_downloaded_concurrently_with_eight_thread_limit(self):
        cloud = self.remote_sync_path()
        self._write_json(cloud / "config.json", {"theme": "cloud"})
        for index in range(16):
            target = cloud / "conn" / f"connection-{index}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(index), encoding="utf-8")

        concurrent_webdav = ConcurrentFakeWebDAV(self.remote)
        self.manager.webdav = concurrent_webdav
        self.manager._perform_initial_sync(CLOUD_BASELINE)

        self.assertGreater(concurrent_webdav.max_active_downloads, 1)
        self.assertLessEqual(concurrent_webdav.max_active_downloads, 8)
        for index in range(16):
            self.assertEqual(
                str(index),
                (self.local / "conn" / f"connection-{index}.json").read_text(
                    encoding="utf-8"
                ),
            )

    def test_cloud_baseline_handles_file_directory_type_changes(self):
        local_file = self.local / "conn" / "local.json"
        local_directory = self.local / "conn" / "local-directory"
        local_directory.mkdir()
        (local_directory / "old.json").write_text("old", encoding="utf-8")

        cloud = self.remote_sync_path()
        (cloud / "conn" / "local.json").mkdir(parents=True)
        (cloud / "conn" / "local.json" / "nested.json").write_text(
            "nested", encoding="utf-8"
        )
        (cloud / "conn" / "local-directory").write_text(
            "cloud-file", encoding="utf-8"
        )

        self.manager._perform_initial_sync(CLOUD_BASELINE)

        self.assertTrue(local_file.is_dir())
        self.assertEqual(
            "nested",
            (local_file / "nested.json").read_text(encoding="utf-8"),
        )
        self.assertTrue(local_directory.is_file())
        self.assertEqual(
            "cloud-file", local_directory.read_text(encoding="utf-8")
        )

    def test_realtime_sync_handles_file_directory_type_changes(self):
        self.manager._perform_initial_sync(LOCAL_BASELINE)
        self.manager._snapshot = self.manager._build_local_snapshot()
        local_item = self.local / "conn" / "local.json"
        remote_item = self.remote_sync_path() / "conn" / "local.json"

        local_item.unlink()
        local_item.mkdir()
        (local_item / "nested.json").write_text("nested", encoding="utf-8")
        self.manager.sync_local_changes()

        self.assertTrue(remote_item.is_dir())
        self.assertEqual(
            "nested",
            (remote_item / "nested.json").read_text(encoding="utf-8"),
        )

        shutil.rmtree(local_item)
        local_item.write_text("file-again", encoding="utf-8")
        self.manager.sync_local_changes()

        self.assertTrue(remote_item.is_file())
        self.assertEqual("file-again", remote_item.read_text(encoding="utf-8"))

    def test_watcher_uploads_local_change(self):
        actual = self.manager.start(str(self.local), LOCAL_BASELINE)
        self.assertEqual(LOCAL_BASELINE, actual)
        changed_file = self.local / "conn" / "local.json"
        changed_file.write_text("changed", encoding="utf-8")
        remote_file = self.remote_sync_path() / "conn" / "local.json"

        self._wait_until(
            lambda: remote_file.exists()
            and remote_file.read_text(encoding="utf-8") == "changed"
        )
        self.assertEqual("changed", remote_file.read_text(encoding="utf-8"))

        new_local_file = self.local / "conn" / "new.json"
        new_remote_file = self.remote_sync_path() / "conn" / "new.json"
        new_local_file.write_text("new", encoding="utf-8")
        self._wait_until(new_remote_file.exists)
        self.assertEqual("new", new_remote_file.read_text(encoding="utf-8"))

        new_local_file.unlink()
        self._wait_until(lambda: not new_remote_file.exists())
        self.assertFalse(new_remote_file.exists())

    def _wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("等待实时同步结果超时")


class ConfigManagerTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            manager = ConfigManager(config_file)

            success, _ = manager.save_config(
                "https://dav.example.test/",
                "user",
                "password",
                "D:/finalshell",
            )

            self.assertTrue(success)
            self.assertEqual(
                (
                    "https://dav.example.test/",
                    "user",
                    "password",
                    "D:/finalshell",
                ),
                manager.load_config(),
            )


if __name__ == "__main__":
    unittest.main()
