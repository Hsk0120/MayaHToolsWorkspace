"""既存ビューポートを操作する Viewport を取得する。

Examples
--------
.. code-block:: python

    view = hlib.viewport()
    with view.suspend():
        nodes = hlib.ls(sl=True)
"""


def viewport(panel=None):
    """Viewportを取得する。生成だけでは表示を変更しない。

    Args:
        panel (str | None): modelPanel名。省略時はフォーカス中または可視パネル。

    Returns:
        Viewport: 表示設定を操作するオブジェクト。

    Raises:
        RuntimeError: 使用できるmodelPanelがない、またはバッチ実行の場合。
    """
    from ..editors import Viewport

    return Viewport(panel)
