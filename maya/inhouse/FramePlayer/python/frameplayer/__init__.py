"""FramePlayer(コマ送り確認用の動画プレイヤー)をMayaから使うためのパッケージ。

主な使い方::

    import frameplayer
    frameplayer.show()          # 連携の画面を開く
    frameplayer.launch()        # FramePlayerを起動する(動画のパスを渡すと開く)
    frameplayer.connect()       # 起動中のFramePlayerとタイムスライダーを連携する
    frameplayer.disconnect()

このパッケージは maya.cmds・maya.api.OpenMaya・標準ライブラリだけを使い、他の社内ライブラリに依存しない。
"""

import os
import subprocess

from frameplayer.sync import DEFAULT_HOST, DEFAULT_PORT, FramePlayerSync

__all__ = ["FramePlayerSync", "connect", "disconnect", "current", "launch", "player_executable", "show"]

_current = None  # 今使っている接続(1つだけ持つ)。


def player_executable():
    """FramePlayerの実行ファイルのパスを返す。

    環境変数 ``FRAMEPLAYER_EXE`` があればそれを、無ければこのパッケージに同梱の
    ``FramePlayer.exe``(パッケージ直下)を使う。

    Returns:
        str: 実行ファイルのパス(存在するかは確かめない)。
    """
    path = os.environ.get("FRAMEPLAYER_EXE")
    if path:
        return path
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(package_root, "FramePlayer.exe")


def launch(*paths):
    """FramePlayerを起動する。

    Args:
        *paths (str): 開く動画のパス。2つ渡すと2本目を比較として開く。

    Returns:
        subprocess.Popen: 起動したプロセス。

    Raises:
        RuntimeError: 実行ファイルが見つからない場合。
    """
    executable = player_executable()
    if not os.path.isfile(executable):
        raise RuntimeError("FramePlayer.exe が見つかりません: %s" % executable)
    return subprocess.Popen([executable] + [str(path) for path in paths], close_fds=True)


def current():
    """今使っている接続を返す。

    Returns:
        FramePlayerSync or None: 接続。まだ作っていなければNone。
    """
    return _current


def connect(port=DEFAULT_PORT, host=DEFAULT_HOST, **options):
    """起動中のFramePlayerへ接続し、タイムスライダーの連携を始める。

    既に接続していれば、いったん切ってからつなぎ直す。

    Args:
        port (int): FramePlayerの待ち受け口の番号(FramePlayerの設定 ``SyncPort``、既定7010)。
        host (str): FramePlayerの待ち受け口のアドレス。
        **options: FramePlayerSync に渡す設定(offset・multiplier・sync_range・maya_to_player・
            player_to_maya・on_status)。

    Returns:
        FramePlayerSync or None: 接続できた場合は接続。できなければNone。
    """
    global _current
    disconnect()
    sync = FramePlayerSync(host=host, port=port, **options)
    if not sync.connect():
        return None
    _current = sync
    return sync


def disconnect():
    """連携をやめ、接続を切る。接続していなければ何もしない。"""
    global _current
    if _current is not None:
        _current.disconnect()
        _current = None


def show():
    """連携の画面を開く。

    Returns:
        str: 画面(window)の名前。
    """
    from frameplayer import ui
    return ui.show()
