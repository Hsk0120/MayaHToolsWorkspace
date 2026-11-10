# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノードのローカルなアトリビュートの値(ポーズ)を保存・復元する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from .nodeRef import NodeRef
from .snapshot import Snapshot, ValidationReport
from typing import Iterable
from mlib.json.nameMapping import NameMapping
from mlib.nodes.node import Node
from mlib.plugs.plug import Plug



class PoseSnapshot(Snapshot):
    """キー可能なアトリビュートと、チャンネルボックスに表示されるアトリビュートの値を保持する。

    値はスカラー(数値・bool・enumの番号)だけで、mlibの既定の単位(角度は度、距離はcm)で保存するため、
    保存時・適用時のUI単位に左右されない。ロック・接続中のアトリビュートも保存し、適用時に書けないものは
    飛ばして報告する。適用でキーは打たず、ワールド空間は扱わない。

    データの形::

        {"nodes": [{"node": {<NodeRef>}, "attrs": {"translateX": 1.0, "rotateY": 45.0, ...}}, ...]}

    Examples:
        >>> pose = PoseSnapshot.capture(mlib.ls(type="joint"))
        >>> pose.save("pose.json")
        >>> PoseSnapshot.load("pose.json").apply(namespaceMap={"chrA": "chrB"})
    """
    FORMAT: str
    VERSION: int
    @classmethod
    def capture(cls, nodes: Iterable[Node | str]) -> PoseSnapshot:
        """ノードのキー可能・チャンネルボックス表示のアトリビュートの現在値を取得する。

        ユーザー定義アトリビュートも含む。スカラー以外の値になるものは保存しない。
        同じノードを複数回指定した場合は最初の1回だけ記録する。

        Args:
            nodes (Iterable[Node | str]): 対象のノード。1つのNode・名前も受け付ける。

        Returns:
            PoseSnapshot: 取得した値を持つ新しいインスタンス。

        Raises:
            TypeError: nodesがノードまたはその並びでない場合。
            RuntimeError: ノードが存在しない場合。
        """
        ...
    def apply(self, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ...) -> ValidationReport:
        """保存した値を、対応付けたノードのアトリビュートへ書き戻す。

        1回のUndoにまとめる。見つからないノードは ``missing``、ロック・入力接続(アニメカーブを含む)・
        対象に無いアトリビュートは ``skipped`` に記録して飛ばし、まとめて警告する。キーは打たない。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        ...
    def _check_data(self, data: dict):
        """``nodes`` の各項目がノード参照とスカラー値の辞書を持つか確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        ...
    def _validate(self, mapping: NameMapping, report: ValidationReport, options: dict):
        """ノードの対応と、書けないアトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        ...
    def _apply(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """書けるアトリビュートへ値を書き込む。

        飛ばすものは :meth:`_validate` で記録済みのため、ここでは書込みに失敗したものだけを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
            fast (bool): 使わない(常にcmdsで書く)。
        """
        ...
    def _plan(self, mapping: NameMapping, report: ValidationReport) -> list[tuple[Plug, object]]:
        """書き込む (Plug, 値) を集め、見つからないもの・書けないものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[tuple[Plug, object]]: 書き込める組。
        """
        ...

def _require_nodes(nodes: Iterable[Node | str] | Node | str) -> list[Node]:
    """ノードの指定をmlibのNodeのlistにする。

    Args:
        nodes (Iterable[Node | str] | Node | str): ノードの指定。

    Returns:
        list[Node]: 指定順のNode。

    Raises:
        TypeError: nodesがノードまたはその並びでない場合。
        RuntimeError: ノードが存在しない場合。
    """
    ...

def _capture_pose_attributes(node: Node) -> dict[str, bool | int | float]:
    """キー可能・チャンネルボックス表示のアトリビュートのスカラー値を集める。

    Args:
        node (Node): 対象のノード。

    Returns:
        dict[str, bool | int | float]: ロング名のアトリビュートパスと値。listAttrの順。
    """
    ...

def _find_plug(node: Node, attribute: str) -> Plug | None:
    """ノードのアトリビュートを探す。

    Args:
        node (Node): 対象のノード。
        attribute (str): アトリビュートのパス。

    Returns:
        Plug | None: 見つかったPlug。無ければNone。
    """
    ...

def _attribute_path(mplug: om2.MPlug) -> str:
    """ノード名を含めない、ロング名のアトリビュートパスを返す。

    Args:
        mplug (om2.MPlug): 対象のPlug。

    Returns:
        str: ``"translateX"``・``"weight[3]"`` 等。
    """
    ...

def _block_reason(mplug: om2.MPlug) -> str | None:
    """アトリビュートへ値を書けない理由を返す。

    自身・コンパウンドアトリビュートの親と子のロック、入力接続(アニメカーブを含む)を見る。

    Args:
        mplug (om2.MPlug): 対象のPlug。

    Returns:
        str | None: ``"locked"``・``"connected"``・``"not settable"``。書けるならNone。
    """
    ...

def _write_plug(plug: Plug, value: object, report: ValidationReport):
    """値を書き込み、失敗したものをreportへ記録する。

    Args:
        plug (Plug): 書き込み先。
        value (object): mlibの既定の単位の値。
        report (ValidationReport): 記録先。
    """
    ...
