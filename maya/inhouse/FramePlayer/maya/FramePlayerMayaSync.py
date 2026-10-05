"""FramePlayer と Maya のタイムスライダーを連携させるパネルを開く(単体で使う人向けの入口)。

FramePlayer だけをダウンロード・インストールした人が、Maya の設定を変えずに連携を使うためのスクリプト。
同じ FramePlayer のフォルダにある ``python/frameplayer`` (Maya 側の連携パッケージ)を読み込んでパネルを開く。

使い方(どちらか):

- このファイルを Maya のビューへドラッグ&ドロップする。パネルが開き、今のシェルフに「FramePlayer」の
  ボタンを追加する(次からはボタンで開ける)。
- スクリプトエディターの File > Source Script でこのファイルを実行する。

連携の通信は FramePlayer 側が開く待ち受け口(このPCの中からだけ接続できる。既定はポート 7010)に、
Maya から接続して行う。FramePlayer の「Maya Sync」ボタンを押すか、パネルの「Launch FramePlayer」で起動する。
Maya 側でポートを開く(commandPort)必要は無い。

フォルダの並び(リポジトリでもインストール先でも同じ)::

    FramePlayer/
    ├ FramePlayer.exe
    ├ maya/FramePlayerMayaSync.py   このファイル
    └ python/frameplayer/           連携パッケージ
"""

import os
import sys

SHELF_LABEL = "FramePlayer"


def _registered_install_dir():
    """インストーラーで入れた FramePlayer のフォルダを、Windows の App Paths から探す。

    Returns:
        str | None: FramePlayer.exe のあるフォルダ。見つからなければ None。
    """
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\FramePlayer.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                exe = winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
        if exe:
            return os.path.dirname(exe)
    return None


def package_dir(script_path=None):
    """連携パッケージ(``frameplayer``)を含むフォルダを探す。

    Args:
        script_path (str | None): このスクリプトのパス。None なら ``__file__`` を使う。

    Returns:
        str | None: ``frameplayer`` パッケージの親フォルダ(``sys.path`` に足す場所)。見つからなければ None。
    """
    candidates = []
    # ドラッグ&ドロップでは __file__ が無いことがあるので、この関数のコードが持つファイル名も使う。
    path = script_path or globals().get("__file__") or package_dir.__code__.co_filename
    if path:
        here = os.path.dirname(os.path.abspath(path))
        candidates += [os.path.join(here, os.pardir, "python"), os.path.join(here, "python")]
    if os.environ.get("FRAMEPLAYER_HOME"):
        candidates.append(os.path.join(os.environ["FRAMEPLAYER_HOME"], "python"))
    installed = _registered_install_dir()
    if installed:
        candidates.append(os.path.join(installed, "python"))
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "frameplayer", "__init__.py")):
            return os.path.normpath(candidate)
    return None


def show(script_path=None):
    """連携パッケージを読み込み、連携パネルを開く。

    Args:
        script_path (str | None): このスクリプトのパス(パッケージを探す手掛かり)。

    Returns:
        str | None: 読み込んだパッケージのフォルダ。見つからなければ None(警告を出す)。
    """
    from maya import cmds

    directory = package_dir(script_path)
    if directory is None:
        cmds.warning("FramePlayer: the Maya sync package (python/frameplayer) was not found next to this script. "
                     "Keep the FramePlayer folder layout, or set FRAMEPLAYER_HOME to the FramePlayer folder.")
        return None
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import frameplayer
    frameplayer.show()
    return directory


def add_shelf_button(directory):
    """今のシェルフに、連携パネルを開くボタンを追加する(同じ名前のボタンがあれば足さない)。

    Args:
        directory (str): 連携パッケージのフォルダ(ボタンのコマンドに埋め込む)。
    """
    from maya import cmds, mel

    top = mel.eval("$frameplayer_tmp = $gShelfTopLevel")
    if not top or not cmds.tabLayout(top, exists=True):
        return
    shelf = cmds.tabLayout(top, query=True, selectTab=True)
    if not shelf:
        return
    for button in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.objectTypeUI(button) == "shelfButton" and cmds.shelfButton(button, query=True, label=True) == SHELF_LABEL:
            return
    command = ("import sys\n"
               "path = r'{0}'\n"
               "if path not in sys.path:\n"
               "    sys.path.insert(0, path)\n"
               "import frameplayer\n"
               "frameplayer.show()\n").format(directory)
    cmds.shelfButton(parent=shelf, label=SHELF_LABEL, imageOverlayLabel="FP", image="pythonFamily.png",
                     annotation="Open the FramePlayer sync panel", command=command, sourceType="python")


def onMayaDroppedPythonFile(*args):
    """Maya のビューへドラッグ&ドロップされたときに Maya が呼ぶ。パネルを開き、シェルフにボタンを足す。"""
    directory = show()
    if directory:
        add_shelf_button(directory)


if __name__ == "__main__":
    show()
