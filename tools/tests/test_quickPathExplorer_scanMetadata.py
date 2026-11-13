"""上段用走査が不要なファイルstatを発生させないことを検証する。"""
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore
from qpeDirectoryModel import ScanJob


def main():
    """低速の共有フォルダーで不要なメタデータ照会をしない契約を確認する。"""
    calls, results = [], []

    class Entry:
        """statの対象を記録するディレクトリ項目。"""
        def __init__(self, name, directory, hidden=False):
            """名前・種別・隠し属性だけを保持する。"""
            self.name, self.directory, self.hidden = name, directory, hidden

        def is_dir(self):
            """列挙時に分かる種別を返す。"""
            return self.directory

        def stat(self):
            """メタデータの照会回数を記録する。"""
            calls.append(self.name)
            return SimpleNamespace(st_size=1, st_mtime=1000., st_file_attributes=2 if self.hidden else 0)

    @contextmanager
    def scan(path):
        """全件を列挙するが、statは明示的に呼ばれるまで実行しない。"""
        yield iter([Entry('folder', True), Entry('file.txt', False), Entry('hidden', True, True)])

    with patch('qpeDirectoryModel.os.scandir', scan):
        job = ScanJob('fixture', 1)
        job.directoriesOnly = True
        job.signals.ready.connect(lambda *args: results.append(args))
        job.run()
        assert calls == ['folder', 'hidden'], calls
        assert [entry[0] for entry in results[-1][2]] == ['folder']
        calls.clear()
        job.directoriesOnly = False
        job.showHidden = True
        job.run()
        assert calls == ['folder', 'file.txt', 'hidden'], calls
        assert len(results[-1][2]) == 3
        job.cancelled.set()
        job.run()
        assert len(results) == 2
    print('PASS: folder-only metadata, hidden entries, full scan, cancellation')


if __name__ == '__main__':
    app = QtCore.QCoreApplication([])
    main()
