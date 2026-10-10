"""Drive登録時の不一致と未共有状態の扱いをMaya非依存で検証する。"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import verification_video as video


class DriveAttachmentTests(unittest.TestCase):
    """動画取り違えと共有状態の誤報告を防ぐ検査。"""

    def setUp(self):
        """ワークスペース内に使い捨ての登録対象を作成する。"""
        base = video.ROOT / ".maya-output/verification"
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="unit-test-", dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        payload = b"test-video-payload"
        (self.folder / "verification.mp4").write_bytes(payload)
        record = {"title": "<検証>", "ok": True, "video_sha256": hashlib.sha256(payload).hexdigest()}
        (self.folder / "result.json").write_text(json.dumps(record), encoding="utf-8")
        self.metadata = {"id": "test-id", "webViewLink": "https://drive.google.com/file/d/test-id/view",
                         "mimeType": "video/mp4", "size": str(len(payload)), "md5Checksum": hashlib.md5(payload).hexdigest(),
                         "permissions": [{"type": "anyone", "role": "reader", "allowFileDiscovery": False}]}

    def test_shared_and_unshared_are_distinguished(self):
        """未共有のアップロードをリンク共有完了としない。"""
        video.attachDrive(self.folder, self.metadata)
        record = json.loads((self.folder / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(record["drive"]["link_viewer_verified"])
        self.assertTrue(record["drive"]["remote_checksum_verified"])
        self.metadata["permissions"] = []
        video.attachDrive(self.folder, self.metadata)
        record = json.loads((self.folder / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(record["drive"]["link_viewer_verified"])

    def test_wrong_remote_video_is_rejected(self):
        """形式・サイズ・チェックサム不一致を拒否する。"""
        for field, value in [("size", "1"), ("mimeType", "image/png"), ("md5Checksum", "wrong")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                video.attachDrive(self.folder, dict(self.metadata, **{field: value}))

    def test_changed_local_video_is_rejected(self):
        """同じサイズのローカル差し替えも検出する。"""
        (self.folder / "verification.mp4").write_bytes(b"TEST-video-payload")
        with self.assertRaises(ValueError):
            video.attachDrive(self.folder, self.metadata)

    def test_untrusted_url_is_rejected(self):
        """Drive以外のURLを正式な閲覧URLとして登録しない。"""
        for url in ["https://drive.google.com.example.org/video", "javascript:alert(1)"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                video.attachDrive(self.folder, dict(self.metadata, webViewLink=url))


if __name__ == "__main__":
    unittest.main()
