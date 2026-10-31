"""Anim Bar: タイムスライダーの上に置く、アニメーション作業用のツールバー。

処理は :mod:`animBar.core`(mlib を使い、Qt を使わない)、画面は :mod:`animBar.ui`(PySide)に分ける。
"""

#: パッケージの版番号。
__version__ = "1.0.0"


def show():
    """バーを表示する(タイムスライダーの上にドックする)。

    Returns:
        str: workspaceControl の名前。
    """
    # 画面はMaya GUIだけで使うため、処理だけを使う場合にQtを読み込まないよう呼出し時に読み込む。
    from .ui import bar
    return bar.show()


def toggle():
    """バーの表示・非表示を切り替える。

    Returns:
        bool: 表示したらTrue。
    """
    # show と同じ理由で、画面は呼出し時に読み込む。
    from .ui import bar
    return bar.toggle()
