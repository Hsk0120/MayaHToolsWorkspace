"""Skin Weight Kit: 右端に縦に置く、スキンのウェイト作業用のパネル。

処理は :mod:`skinWeightKit.core`(mlib を使い、Qt を使わない)、画面は :mod:`skinWeightKit.ui`(PySide)に分ける。
"""

#: パッケージの版番号。
__version__ = "1.0.0"


def show():
    """パネルを表示する(メインウィンドウの右端にドックする)。

    Returns:
        str: workspaceControl の名前。
    """
    # 画面はMaya GUIだけで使うため、処理だけを使う場合にQtを読み込まないよう呼出し時に読み込む。
    from .ui import panel
    return panel.show()


def toggle():
    """パネルの表示・非表示を切り替える。

    Returns:
        bool: 表示したらTrue。
    """
    # show と同じ理由で、画面は呼出し時に読み込む。
    from .ui import panel
    return panel.toggle()
