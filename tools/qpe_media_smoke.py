"""生成した動画・EXRのサムネイルを独立Qt環境で検証する。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets
from qpeMedia import ffmpegPath, mediaImage


def main():
    """実デコーダーの結果を確認してJSONとスクリーンショットへ残す。"""
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    ffmpeg = ffmpegPath()
    assert ffmpeg, 'FFmpeg unavailable'
    checks = []
    for name, options in [('preview.mp4', ['-t', '2', '-pix_fmt', 'yuv420p']),
                          ('texture.1001.exr', ['-frames:v', '1', '-c:v', 'exr'])]:
        path = out / name
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'testsrc=size=320x180:rate=24'] + options + [str(path)], check=True,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        image, error = mediaImage(str(path))
        assert not image.isNull(), error
        image.save(str(path.with_suffix('.png')))
        checks.append(name + ' real FFmpeg thumbnail')
    result = dict(status='passed', qt=QtCore.qVersion(), checks=checks)
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
