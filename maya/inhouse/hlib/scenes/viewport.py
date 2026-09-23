"""ビューポートの表示設定とメインペインの一時停止。"""

from contextlib import contextmanager

import maya.cmds as cmds
import maya.mel as mel

from ._editor import _Editor


class Viewport(_Editor):
    """既存modelPanelの表示設定を操作する。生成時にUIを変更しない。

    settings/set_settings は modelEditor の長いフラグ名を使う。
    suspend は個別パネルではなく、Mayaのメインペイン全体に作用する。
    """

    _command = "modelEditor"
    _flags = ("grid", "joints", "nurbsCurves", "polymeshes", "locators",
              "cameras", "lights", "displayAppearance", "displayTextures",
              "wireframeOnShaded", "xray", "selectionHiliteDisplay")

    def __init__(self, panel=None):
        """対象パネルを保持する。

        Args:
            panel (str | None): modelPanel名。省略時はフォーカス中、
                次に可視modelPanelを使用する。

        Raises:
            RuntimeError: 対象modelPanelがない、またはバッチ実行の場合。
        """
        if cmds.about(batch=True):
            raise RuntimeError("Viewport requires Maya GUI")
        panels = cmds.getPanel(type="modelPanel") or []
        if panel is None:
            focused = cmds.getPanel(withFocus=True)
            visible = cmds.getPanel(visiblePanels=True) or []
            panel = focused if focused in panels else next(
                (name for name in visible if name in panels), None)
        if panel not in panels:
            raise RuntimeError(f"No modelPanel available: {panel}")
        self._panel = panel
        self._name = cmds.modelPanel(panel, query=True, modelEditor=True)

    def panel(self):
        """str: 保持しているmodelPanel名を返す。"""
        return self._panel

    def camera(self):
        """str: 現在表示しているカメラ名を返す。"""
        self._require_exists()
        return cmds.modelEditor(self._name, query=True, camera=True)

    def set_camera(self, camera):
        """表示カメラを変更する。

        Args:
            camera (str): Mayaが解決できるカメラ名。

        Returns:
            None: 値を返さない。
        """
        self._require_exists()
        cmds.modelEditor(self._name, edit=True, camera=camera)

    @staticmethod
    def _main_pane():
        """str: Mayaのメインペインを取得する。GUIがなければ RuntimeError。"""
        if cmds.about(batch=True):
            raise RuntimeError("Viewport suspension requires Maya GUI")
        pane = mel.eval('global string $gMainPane; $hlibMainPane = $gMainPane;')
        if not pane or not cmds.paneLayout(pane, exists=True):
            raise RuntimeError("Maya main pane is unavailable")
        return pane

    @staticmethod
    def is_enabled():
        """bool: メインペインのmanage状態。描画エンジンの状態ではない。"""
        return bool(cmds.paneLayout(Viewport._main_pane(), query=True, manage=True))

    @staticmethod
    def set_enabled(enabled):
        """mGear viewport_offと同じ方式でメインペインを表示/非表示にする。

        Args:
            enabled (bool): Falseでmanageを解除し、Trueで表示へ戻す。
                メインペイン内のアウトライナー等も対象。計算や再生は停止しない。

        Returns:
            None: 値を返さない。安全な一時停止には suspend() を推奨する。
        """
        cmds.paneLayout(Viewport._main_pane(), edit=True, manage=bool(enabled))

    @staticmethod
    @contextmanager
    def suspend():
        """メインペインを一時的に非表示にし、例外時も元のmanage状態に戻す。

        ネスト可能。内部処理の例外は伝播し、処理を再実行しない。
        OGSやrefreshの停止フラグは変更しない。

        Yields:
            None: withブロック内で任意の処理を実行する。
        """
        pane = Viewport._main_pane()
        previous = cmds.paneLayout(pane, query=True, manage=True)
        try:
            cmds.paneLayout(pane, edit=True, manage=False)
            yield
        finally:
            if cmds.paneLayout(pane, exists=True):
                cmds.paneLayout(pane, edit=True, manage=previous)
