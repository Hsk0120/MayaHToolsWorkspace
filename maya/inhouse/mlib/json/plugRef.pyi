# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Plugを、所有ノードの参照とアトリビュートのパスで記録する。"""

from .nameMapping import NameMapping
from .nodeRef import NodeRef
from mlib.plugs.plug import Plug
import maya.api.OpenMaya as om2



class PlugRef:
    """Plugを所有ノードの :class:`NodeRef` とアトリビュートのパスで記録した参照。

    アトリビュートのパスはロング名で、マルチアトリビュートの要素は ``weight[3]``、コンパウンドの子は
    ``translate.translateX`` のように書く。エイリアスは使わない。名前の対応付けはノードの部分にだけ当てる。
    """
    __hash__: None
    def __init__(self, node: NodeRef, attribute: str) -> None:
        """記録する値を保持する。

        Args:
            node (NodeRef): 所有ノードの参照。
            attribute (str): アトリビュートのパス(ノード名を含めない)。

        Raises:
            TypeError: nodeがNodeRefでない、またはattributeが文字列でない場合。
            ValueError: attributeが空の場合。
        """
        ...
    def __repr__(self) -> str:
        """ノード名とアトリビュートを含む表記を返す。

        Returns:
            str: ``PlugRef('chrA:arm_L_jnt.translateX')`` の形式。
        """
        ...
    def __eq__(self, other: object) -> bool:
        """ノードの参照とアトリビュートのパスが同じかを返す。

        Args:
            other (object): 比較する値。

        Returns:
            bool: 同じ記録ならTrue。PlugRef以外はNotImplemented。
        """
        ...
    @classmethod
    def capture(cls, plug: Plug | str | om2.MPlug) -> PlugRef:
        """シーンのPlugから参照を作る。

        Args:
            plug (Plug | str | om2.MPlug): 記録するPlug。

        Returns:
            PlugRef: 所有ノードとアトリビュートのパスを記録した参照。

        Raises:
            TypeError: plugが対応しない型の場合。
            ValueError: Plugが存在しない場合。
            RuntimeError: Plugが無効な場合。
        """
        ...
    @classmethod
    def fromData(cls, data: dict) -> PlugRef:
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): ``node``・``attr`` を持つ辞書。

        Returns:
            PlugRef: 新しい参照。

        Raises:
            ValueError: 辞書の形が違う場合。
        """
        ...
    @property
    def node(self) -> NodeRef:
        """所有ノードの参照を返す。

        Returns:
            NodeRef: 保持する参照。
        """
        ...
    @property
    def attribute(self) -> str:
        """アトリビュートのパスを返す。

        Returns:
            str: ``"translateX"``・``"weight[3]"`` 等。
        """
        ...
    def toData(self) -> dict:
        """JSONに書く辞書を返す。

        Returns:
            dict: ``{"node": {...}, "attr": ...}``。
        """
        ...
    def mappedName(self, mapping: NameMapping | None = ...) -> str:
        """対応付けを当てたPlug名を返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            str: ``<ノード名>.<アトリビュート>``。警告や報告の表示に使う。
        """
        ...
    def resolve(self, mapping: NameMapping | None = ...) -> Plug | None:
        """対応付けを当てたノードの、同じアトリビュートのPlugを返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            Plug | None: 見つかったPlug。ノードまたはアトリビュートが無ければNone。

        Raises:
            TypeError: mappingがNameMapping・None以外の場合。
        """
        ...
