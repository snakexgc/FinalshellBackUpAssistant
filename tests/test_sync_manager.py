import shutil
import tempfile
import time
import unittest
from pathlib import Path

from core.sync_manager import CLOUD_BASELINE, LOCAL_BASELINE, SyncManager
from utils.config_manager import ConfigManager


class FakeWebDAV:
    sync_remote_path = "Finalshell_BackUp/sync"

    def __init__(self, root: Path):
        self.root = root

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


class SyncManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.local = self.base / "local"
        self.remote = self.base / "remote"
        self.local.mkdir()
        self.remote.mkdir()
        (self.local / "finalshell.exe").write_bytes(b"exe")
        (self.local / "config.json").write_text("local-config", encoding="utf-8")
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

    def test_local_baseline_exactly_replaces_cloud(self):
        cloud = self.remote_sync_path()
        (cloud / "conn").mkdir(parents=True)
        (cloud / "config.json").write_text("old-cloud", encoding="utf-8")
        (cloud / "conn" / "remote-only.json").write_text(
            "remove-me", encoding="utf-8"
        )

        actual = self.manager._perform_initial_sync(LOCAL_BASELINE)

        self.assertEqual(LOCAL_BASELINE, actual)
        self.assertEqual(
            "local-config", (cloud / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "local-connection",
            (cloud / "conn" / "local.json").read_text(encoding="utf-8"),
        )
        self.assertFalse((cloud / "conn" / "remote-only.json").exists())

    def test_cloud_baseline_exactly_replaces_local(self):
        cloud = self.remote_sync_path()
        (cloud / "conn" / "nested").mkdir(parents=True)
        (cloud / "config.json").write_text("cloud-config", encoding="utf-8")
        (cloud / "conn" / "cloud.json").write_text(
            "cloud-connection", encoding="utf-8"
        )

        actual = self.manager._perform_initial_sync(CLOUD_BASELINE)

        self.assertEqual(CLOUD_BASELINE, actual)
        self.assertEqual(
            "cloud-config",
            (self.local / "config.json").read_text(encoding="utf-8"),
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
        self.assertEqual(
            "local-config",
            (self.remote_sync_path() / "config.json").read_text(encoding="utf-8"),
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
