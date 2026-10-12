"""一覧用の静止サムネイル取得と連番・UDIM候補の判定。"""
import os
import re
import shutil
import subprocess
from pathlib import Path
from qpeQt import QtGui


def ffmpegPath():
    """明示設定、PATH、任意同梱パッケージの順でFFmpegを探す。"""
    configured = os.environ.get('QPE_FFMPEG') or shutil.which('ffmpeg')
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def mediaImage(path):
    """大きなデコード結果を返さず、縮小したPNG一枚を取得する。"""
    from qpeProductivityIO import requireLocal
    try:
        requireLocal(path)
    except OSError as error:
        return QtGui.QImage(), str(error)
    executable = ffmpegPath()
    if not executable:
        return QtGui.QImage(), 'Install imageio-ffmpeg or set QPE_FFMPEG for video / EXR thumbnails.'
    command = [executable, '-nostdin', '-v', 'error', '-i', str(path), '-frames:v', '1',
               '-vf', 'scale=720:480:force_original_aspect_ratio=decrease', '-f', 'image2pipe', '-vcodec', 'png', '-']
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        image = QtGui.QImage.fromData(result.stdout, 'PNG')
        return image, '' if not image.isNull() else result.stderr.decode(errors='replace')[:500]
    except (OSError, subprocess.TimeoutExpired) as error:
        return QtGui.QImage(), str(error)


def relatedFrames(path):
    """末尾の同桁番号を連番／UDIM候補として返す。"""
    path = Path(path)
    match = re.match(r'^(.*?)(\d+)(\.[^.]+)$', path.name)
    if not match:
        return [str(path)]
    prefix, digits, suffix = match.groups()
    pattern = re.compile(re.escape(prefix) + r'\d{' + str(len(digits)) + '}' + re.escape(suffix) + '$')
    return sorted(str(p) for p in path.parent.iterdir() if p.is_file() and pattern.fullmatch(p.name))
