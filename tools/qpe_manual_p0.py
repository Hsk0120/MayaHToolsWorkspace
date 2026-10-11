"""P0実機確認用データと、遅延読込を使う検証画面を用意する。"""
import tempfile
from pathlib import Path


def prepare():
    """制作ファイルを使わず専用フォルダーを毎回新規作成する。

    Returns:
        Path: 作成した検証ルート。
    """
    output = Path(__file__).resolve().parents[1] / '.maya-output/qpe-manual-p0'
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='review-', dir=str(output)))
    for name in ('A', 'B', 'Empty', '日本語の長い名前を持つ検証フォルダー'):
        (root / name).mkdir()
    for i in range(65):
        (root / ('Folder-%02d' % i)).mkdir()
        (root / 'A' / ('Child-%02d' % i)).mkdir()
        (root / ('File-%02d.txt' % i)).write_text('QuickPathExplorer test %02d' % i, encoding='utf-8')
    (root / 'A/Deep/Two/Three/Four/Five/Six').mkdir(parents=True)
    return root


def show():
    """Mayaでシーンを変更せず、800ms遅延の一覧を開く。

    Returns:
        Explorer: 検証用のQPE。終了時はこのウィンドウを閉じる。
    """
    import time
    import qpeHost
    from qpeDirectoryModel import ScanJob
    class SlowScan(ScanJob):
        """入力後に読込完了が届く状況を作る検証専用ワーカ。"""
        def run(self):
            """GUIを止めず800ms待って実際の一覧を取得する。"""
            time.sleep(.8)
            super().run()
    root = prepare()
    widget = qpeHost.show(str(root))
    widget.folderModel.jobFactory = SlowScan
    widget.fileModel.jobFactory = SlowScan
    widget.setBrowseRoot(str(root))
    print('QPE manual fixture: ' + str(root))
    return widget


if __name__ == '__main__':
    print(prepare())
