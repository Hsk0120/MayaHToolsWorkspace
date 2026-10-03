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

__all__ = ["FramePlayerSync", "connect", "disconnect", "current", "last_error", "launch", "player_executable", "show"]

_current = None     # 今使っている接続(1つだけ持つ)。
_last_error = ""    # 最後に接続できなかった理由。


def _installed_executable():
    """インストーラーで入れたFramePlayerの実行ファイルのパスを返す。

    インストーラーはWindowsの「App Paths」(``HKEY_CURRENT_USER`` または ``HKEY_LOCAL_MACHINE`` の
    ``Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\FramePlayer.exe``)に場所を登録する。

    Returns:
        str: パス。インストールされていなければ空文字列。
    """
    try:
        import winreg
    except ImportError:  # Windows以外。
        return ""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\FramePlayer.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                path, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if path and os.path.isfile(path):
            return path
    return ""


def player_executable():
    """FramePlayerの実行ファイルのパスを返す。

    次の順に探す。

    1. 環境変数 ``FRAMEPLAYER_EXE``
    2. このパッケージに同梱の ``FramePlayer.exe``(パッケージ直下。リポジトリから使うとき)
    3. インストーラーで入れたFramePlayer(Windowsの「App Paths」に登録された場所)

    Returns:
        str: 実行ファイルのパス。どこにも無ければ、同梱の場所(存在しない)を返す。
    """
    path = os.environ.get("FRAMEPLAYER_EXE")
    if path:
        return path
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bundled = os.path.join(package_root, "FramePlayer.exe")
    if os.path.isfile(bundled):
        return bundled
    return _installed_executable() or bundled


def launch(*paths, sync=True):
    """FramePlayerを起動する。

    Args:
        *paths (str): 開く動画のパス。2つ渡すと2本目を比較として開く。
        sync (bool): Trueなら連携モード(Mayaからの接続を待つ)で起動する。FramePlayerは通常モードでは
            ポートを開かないので、Mayaと連携するときはTrueのままにする。

    Returns:
        subprocess.Popen: 起動したプロセス。

    Raises:
        RuntimeError: 実行ファイルが見つからない場合。
    """
    executable = player_executable()
    if not os.path.isfile(executable):
        raise RuntimeError("FramePlayer.exe が見つかりません: %s" % executable)
    arguments = [executable] + [str(path) for path in paths]
    if sync:
        arguments.append("--sync")
    return subprocess.Popen(arguments, close_fds=True)


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
            つないだ直後に、互いが同じ鍵(``%LOCALAPPDATA%\\FramePlayer\\sync.key``)を持つ相手かを確かめる。
        host (str): FramePlayerの待ち受け口のアドレス。
        **options: FramePlayerSync に渡す設定(offset・multiplier・sync_range・maya_to_player・
            player_to_maya・on_status)。

    Returns:
        FramePlayerSync or None: 接続できた場合は接続。できなければNone。
    """
    global _current, _last_error
    disconnect()
    sync = FramePlayerSync(host=host, port=port, **options)
    if not sync.connect():
        _last_error = sync.last_error
        return None
    _last_error = ""
    _current = sync
    return sync


def last_error():
    """最後に接続できなかった理由を返す。

    Returns:
        str: 理由。最後の接続が成功していれば空。
    """
    return _last_error


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
