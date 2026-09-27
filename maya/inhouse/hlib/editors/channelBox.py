"""既存Channel Boxの表示対象と選択属性を取得する。"""

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om2

from ..nodes.node import Node
from ..plugs.plug import Plug
from ..decorators.undo import undo_chunk


class ChannelBox:
    """UIの選択属性を既存Plugへ解決する。UIの新規作成はしない。"""

    _sections = {"main": ("mainObjectList", "selectedMainAttributes"),
                 "shape": ("shapeObjectList", "selectedShapeAttributes"),
                 "history": ("historyObjectList", "selectedHistoryAttributes"),
                 "output": ("outputObjectList", "selectedOutputAttributes")}

    def __init__(self, control=None):
        """既存UIを参照する。control省略時はMaya標準Channel Box。GUIなしはRuntimeError。"""
        if cmds.about(batch=True):
            raise RuntimeError("Channel Box requires Maya GUI")
        self._name = control or mel.eval('global string $gChannelBoxName; $gChannelBoxName;')
        self.name()

    def exists(self):
        """bool: 保持したUIが存在するか。"""
        return bool(self._name and cmds.channelBox(self._name, exists=True))

    def name(self):
        """str: UI名。削除済みの場合はRuntimeError。"""
        if not self.exists():
            raise RuntimeError(f"Channel Box is unavailable: {self._name}")
        return self._name

    def _section_names(self, section):
        """sectionを検証する。未対応の名前はValueError。"""
        if section == "all":
            return tuple(self._sections)
        if section not in self._sections:
            raise ValueError("section must be main, shape, history, output or all")
        return (section,)

    def displayed_nodes(self, section="main"):
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
                result.setdefault(node.full_name(), node)
        return list(result.values())

    def selected_attributes(self, section="main"):
        """指定欄の選択属性名を取得する。

        Args:
            section (str): main/shape/history/output/all。

        Returns:
            list[str]: Mayaが返す属性名。短縮名やaliasの場合もある。未選択は空。
        """
        names = []
        for part in self._section_names(section):
            flag = self._sections[part][1]
            names.extend(cmds.channelBox(self.name(), query=True, **{flag: True}) or [])
        return list(dict.fromkeys(names))

    def selected_plugs(self, section="all"):
        """表示ノードと選択属性を欄ごとに対応付ける。

        Args:
            section (str): main/shape/history/output/all。

        Returns:
            list[Plug]: 重複なしのPlug。ノードに存在しない属性は除外する。
                未選択なら空リスト。全属性への暗黙の切り替えはしない。
        """
        result = {}
        for part in self._section_names(section):
            attrs = self.selected_attributes(part)
            if not attrs:
                continue
            for node in self.displayed_nodes(part):
                for attr in attrs:
                    selection = om2.MSelectionList()
                    try:
                        selection.add(f"{node.full_name()}.{attr}")
                        plug = Plug(node, selection.getPlug(0))
                    except (RuntimeError, TypeError):
                        continue
                    result.setdefault(plug.full_name(), plug)
        return list(result.values())

    @undo_chunk("hlibChannelBoxClearSelection")
    def clear_selection(self):
        """属性のUI選択を解除する。シーンのノード選択は変更しない。戻り値はNone。"""
        cmds.channelBox(self.name(), edit=True, select="")
