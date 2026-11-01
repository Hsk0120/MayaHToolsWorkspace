"""隔離設定でQPEのimport・構築・起動経路・初回描画を計測する。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def main():
    """同じ設定コピーを使い、初回描画までを計測して専用QPEだけ閉じる。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    if root / '.maya-output' not in out.parents:
        raise ValueError('Dedicated output required')
    out.mkdir(parents=True, exist_ok=True)
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    (out / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    sys.path.insert(0, str(args.source.resolve()))
    started = time.perf_counter()
    from quickPathExplorer import Explorer, QtCore, QtWidgets
    imported = time.perf_counter()
    app = QtWidgets.QApplication([])
    e = Explorer()
    built = time.perf_counter()
    result = dict(importSeconds=imported - started, constructSeconds=built - imported)
    navigations = []
    navigate = e.navigate

    def tracked(*args, **kwargs):
        """移動回数だけを記録し、製品の移動をそのまま実行する。"""
        navigations.append(time.perf_counter())
        return navigate(*args, **kwargs)

    class FirstPaint(QtCore.QObject):
        """OS入力と区別し、QPE自身の初回Paint配送を観測する。"""
        def eventFilter(self, watched, event):
            """初回Paint時刻だけを記録し、イベントの処理を妨げない。"""
            if watched is e and event.type() == QtCore.QEvent.Paint and 'firstPaintSeconds' not in result:
                result['firstPaintSeconds'] = time.perf_counter() - started
            return False

    e.navigate = tracked
    observer = FirstPaint(e)
    e.installEventFilter(observer)
    e.show()
    if hasattr(e, 'restoreStartup'):
        e.restoreStartup()
    else:
        e.navigate(settings['lastPath'])
        e.folderTabs.restoreSession()
    result['startupPathSeconds'] = time.perf_counter() - built
    app.processEvents()
    result['firstEventPassSeconds'] = time.perf_counter() - started
    result['navigations'] = len(navigations)
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    e.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
