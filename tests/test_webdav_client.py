import unittest
from unittest.mock import patch

from core.webdav_client import WebDAVClient


class FakeClient:
    last_options = None
    list_calls = []

    def __init__(self, options):
        type(self).last_options = options
        type(self).list_calls = []

    def check(self, remote_path):
        return remote_path == "/"

    def list(self, remote_path, **kwargs):
        type(self).list_calls.append(remote_path)
        return []

    def mkdir(self, remote_path):
        return True


class WebDAVClientTests(unittest.TestCase):
    def test_backup_and_sync_share_root_and_use_ten_second_timeout(self):
        with patch("core.webdav_client.Client", FakeClient):
            client = WebDAVClient(
                "https://dav.example.test/",
                "user",
                "password",
            )
            success, _ = client.connect()
            sync_success, _ = client.ensure_remote_directory(
                f"{client.sync_remote_path}/conn"
            )
            cached_success, _ = client.ensure_remote_directory(
                f"{client.sync_remote_path}/conn"
            )

        self.assertTrue(success)
        self.assertTrue(sync_success)
        self.assertTrue(cached_success)
        self.assertEqual("Finalshell_BackUp", client.remote_path)
        self.assertEqual("Finalshell_BackUp/sync", client.sync_remote_path)
        self.assertEqual(10, FakeClient.last_options["webdav_timeout"])
        self.assertEqual(
            [
                "Finalshell_BackUp",
                "Finalshell_BackUp/sync",
                "Finalshell_BackUp/sync/conn",
            ],
            FakeClient.list_calls,
        )


if __name__ == "__main__":
    unittest.main()
