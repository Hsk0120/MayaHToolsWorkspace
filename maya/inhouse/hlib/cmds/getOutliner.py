"""既存アウトライナーを操作する Outliner を取得する。

Examples
--------
.. code-block:: python

    outliner = hlib.getOutliner()
    outliner.set_settings(showShapes=True)
"""


def getOutliner(editor=None):
    """Outlinerを取得する。生成だけではUIを作成/変更しない。

    Args:
        editor (str | None): outlinerEditorまたはoutlinerPanel名。
            省略時は既存outlinerPanelから取得する。

    Returns:
        Outliner: 表示設定と階層展開を操作するオブジェクト。

    Raises:
        RuntimeError: 対象アウトライナーが存在しない、またはバッチ実行の場合。
    """
    from hlib.ui import Outliner

    return Outliner(editor)
