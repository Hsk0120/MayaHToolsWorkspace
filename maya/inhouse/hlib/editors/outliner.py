"""既存アウトライナーの表示設定と階層展開を扱う。"""

import maya.cmds as cmds

from ._editor import _Editor


class Outliner(_Editor):
    """既存outlinerEditorを参照する。設定変更は指定エディターだけに作用する。"""

    _command = "outlinerEditor"
    _flags = ("showShapes", "showDagOnly", "showNamespace", "showReferenceNodes",
              "showAttributes", "showConnected", "showSetMembers", "showSelected",
              "longNames", "niceNames", "ignoreDagHierarchy", "sortOrder")

    def __init__(self, editor=None):
        """対象エディターを保持する。

        Args:
            editor (str | None): outlinerEditorまたはoutlinerPanel名。
                省略時はフォーカス中、可視、その他のoutlinerPanelの順で探す。

        Raises:
            RuntimeError: アウトライナーが存在しない、またはバッチ実行の場合。
        """
        if cmds.about(batch=True):
            raise RuntimeError("Outliner requires Maya GUI")
        panels = cmds.getPanel(type="outlinerPanel") or []
        if editor is None:
            candidates = [cmds.getPanel(withFocus=True)]
            candidates += cmds.getPanel(visiblePanels=True) or []
            candidates += panels
            editor = next((name for name in candidates if name in panels), None)
        if editor in panels:
            editor = cmds.outlinerPanel(editor, query=True, outlinerEditor=True)
        if not editor or not cmds.outlinerEditor(editor, exists=True):
            raise RuntimeError(f"No outlinerEditor available: {editor}")
        self._name = editor

    def expand_all(self, expanded=True):
        """表示中の階層をすべて展開、または折りたたむ。

        Args:
            expanded (bool): Trueで展開、Falseで折りたたむ。

        Returns:
            None: 値を返さない。ノードの選択は変更しない。
        """
        self._require_exists()
        cmds.outlinerEditor(self._name, edit=True, expandAllItems=bool(expanded))
