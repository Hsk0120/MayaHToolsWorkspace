# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""選択(ノードとコンポーネント)を選択順のまま保存・復元する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from .. import logger
from .componentRef import ComponentRef
from .nodeRef import NodeRef
from .snapshot import Snapshot, ValidationReport
from typing import Iterable
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.json.nameMapping import NameMapping
from mlib.nodes.node import Node

_COMPONENT_TYPES: tuple


class SelectionSnapshot(Snapshot):
    """選択したノードとコンポーネント(頂点・エッジ・フェース・UV・カーブのCV)を選択順に保持する。

    コンポーネントは同じシェイプ・同じ種類が続く範囲を1つの :class:`ComponentRef` にまとめる。
    NURBSサーフェスのCV等、番号が1つで表せないコンポーネントは保存しない。

    データの形::

        {"items": [{"node": {<NodeRef>}}, {"components": {<ComponentRef>}}, ...]}

    Examples:
        >>> snap = SelectionSnapshot.capture()
        >>> snap.save("selection.json")
        >>> SelectionSnapshot.load("selection.json").apply(namespaceMap={"chrA": "chrB"})
    """
    FORMAT: str
    VERSION: int
    @classmethod
    def capture(cls, items: Iterable[Node | Component | Components | str] | None = ...) -> SelectionSnapshot:
        """選択、または指定したノード・コンポーネントを取得する。

        Noneは現在の選択を選択順(``ls -orderedSelection``)で取得する。選択順の記録
        (``selectPref -trackSelectionOrder``)が無効で順序が取れない場合は ``ls -selection`` の順にする。

        Args:
            items (Iterable[Node | Component | Components | str] | None): 記録するノード・コンポーネント。
                文字列は ``"pCube1.vtx[0:3]"`` のようなコンポーネントの表記も受け付ける。Noneは現在の選択。

        Returns:
            SelectionSnapshot: 選択順の項目を持つ新しいインスタンス。

        Raises:
            TypeError: itemsの型が違う場合。
            RuntimeError: 指定したノード・コンポーネントが存在しない場合。
        """
        ...
    def apply(self, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ...) -> ValidationReport:
        """保存した項目を、対応付けたシーンのノード・コンポーネントで選択し直す(現在の選択を置き換える)。

        見つからないノードは ``missing``、範囲外の番号を含むコンポーネントは ``skipped`` に記録して飛ばし、
        まとめて警告する。見つかるものが無ければ選択を解除する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        ...
    def _check_data(self, data: dict):
        """``items`` の各項目がノードまたはコンポーネントの参照か確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        ...
    def _validate(self, mapping: NameMapping, report: ValidationReport, options: dict):
        """ノード・コンポーネントの対応を記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        ...
    def _apply(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """見つかった項目で選択を置き換える。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先(飛ばすものは :meth:`_validate` で記録済み)。
            options (dict): 使わない。
            fast (bool): 使わない。
        """
        ...
    def _plan(self, mapping: NameMapping, report: ValidationReport) -> list[str]:
        """選択する名前を集め、見つからないもの・範囲外のものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[str]: cmds.selectへ渡す名前(選択順)。
        """
        ...

def _selection_items(items: Iterable | None) -> list:
    """記録する項目の指定を、順序付きのlistにする。

    Args:
        items (Iterable | None): 指定。Noneは現在の選択。

    Returns:
        list: 指定順の項目。

    Raises:
        TypeError: itemsが並びでない場合。
    """
    ...

def _capture_item(item: Node | Component | Components | str | om2.MDagPath | om2.MObject) -> list[NodeRef | ComponentRef]:
    """1つの項目を参照にする。

    Args:
        item (Node | Component | Components | str | om2.MDagPath | om2.MObject): 項目。

    Returns:
        list[NodeRef | ComponentRef]: 参照。保存しない種類のコンポーネントは空list。

    Raises:
        TypeError: 対応しない型の場合。
        RuntimeError: 存在しない場合。
    """
    ...

def _capture_selection_entry(selection: om2.MSelectionList, index: int, label: str) -> list[NodeRef | ComponentRef]:
    """MSelectionListの1項目を参照にする。

    Args:
        selection (om2.MSelectionList): 選択の一覧。
        index (int): 項目の番号。
        label (str): 警告に使う名前。

    Returns:
        list[NodeRef | ComponentRef]: 参照。保存しない種類のコンポーネントは空list。
    """
    ...

def _append_ref(groups: list[NodeRef | ComponentRef], ref: NodeRef | ComponentRef):
    """参照を並びへ足す。直前と同じシェイプ・種類のコンポーネントは1つにまとめる。

    Args:
        groups (list[NodeRef | ComponentRef]): これまでの参照。変更する。
        ref (NodeRef | ComponentRef): 足す参照。
    """
    ...

def _item_data(ref: NodeRef | ComponentRef) -> dict:
    """参照を、選択のデータの1項目にする。

    Args:
        ref (NodeRef | ComponentRef): 参照。

    Returns:
        dict: ``{"node": ...}`` または ``{"components": ...}``。
    """
    ...
