"""既存Channel Boxの表示対象と選択アトリビュートを取得する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel

from ..decorators.undo import undoChunk
from ..nodes.node import Node
from ..plugs.plug import Plug


class ChannelBox:
    """UIの選択アトリビュートを既存Plugへ解決する。UIの新規作成はしない。"""

    _sections = {"main": ("mainObjectList", "selectedMainAttributes"),
                 "shape": ("shapeObjectList", "selectedShapeAttributes"),
                 "history": ("historyObjectList", "selectedHistoryAttributes"),
                 "output": ("outputObjectList", "selectedOutputAttributes")}

    def __init__(self, control=None):
        """既存のChannel Boxを参照する。

        Args:
            control (str | None): UI名。省略時はMaya標準Channel Box。

        Raises:
            RuntimeError: GUIを利用できない場合。
        """
        if cmds.about(batch=True):
            raise RuntimeError("Channel Box requires Maya GUI")
        self._name = control or mel.eval('global string $gChannelBoxName; $gChannelBoxName;')
        self.name()

    def exists(self):
        """保持したUIが存在するか。

        Returns:
            bool: 保持したUIが存在するか。
        """
        return bool(self._name and cmds.channelBox(self._name, exists=True))

    def name(self):
        """UI名。削除済みの場合はRuntimeError。

        Returns:
            str: UI名。削除済みの場合はRuntimeError。
        """
        if not self.exists():
            raise RuntimeError(f"Channel Box is unavailable: {self._name}")
        return self._name

    def displayedNodes(self, section="main"):
        """指定欄の表示対象を返す。

        Args:
            section (str): main/shape/history/output/all。

        Returns:
            list[Node]: Mayaの欄別objectListの順。重複を除く。
        """
        result = {}
        for part in self._section_names(section):
            flag = self._sections[part][0]
            for name in cmds.channelBox(self.name(), query=True, **{flag: True}) or []:
                node = Node(name)
                result.setdefault(node.fullName(), node)
        return list(result.values())

    def selectedAttributes(self, section="main"):
        """指定欄の選択アトリビュート名を取得する。

        Args:
            section (str): main/shape/history/output/all。

        Returns:
            list[str]: Mayaが返すアトリビュート名。短縮名やaliasの場合もある。未選択は空。
        """
        names = []
        for part in self._section_names(section):
            flag = self._sections[part][1]
            names.extend(cmds.channelBox(self.name(), query=True, **{flag: True}) or [])
        return list(dict.fromkeys(names))

    def selectedPlugs(self, section="all"):
        """表示ノードと選択アトリビュートを欄ごとに対応付ける。

        Args:
            section (str): main/shape/history/output/all。

        Returns:
            list[Plug]: 重複なしのPlug。ノードに存在しないアトリビュートは除外する。
                未選択なら空リスト。全アトリビュートへの暗黙の切り替えはしない。
        """
        result = {}
        for part in self._section_names(section):
            attrs = self.selectedAttributes(part)
            if not attrs:
                continue
            for node in self.displayedNodes(part):
                for attr in attrs:
                    selection = om2.MSelectionList()
                    try:
                        selection.add(f"{node.fullName()}.{attr}")
                        plug = Plug(node, selection.getPlug(0))
                    except (RuntimeError, TypeError):
                        continue
                    result.setdefault(plug.fullName(), plug)
        return list(result.values())

    @undoChunk("hlibChannelBoxClearSelection")
    def clearSelection(self):
        """アトリビュートのUI選択を解除する。シーンのノード選択は変更しない。戻り値はNone。"""
        cmds.channelBox(self.name(), edit=True, select="")

    def _section_names(self, section):
        """sectionを検証する。未対応の名前はValueError。

        Args:
            section: UIの表示設定または操作対象の項目。
        """
        if section == "all":
            return tuple(self._sections)
        if section not in self._sections:
            raise ValueError("section must be main, shape, history, output or all")
        return (section,)
