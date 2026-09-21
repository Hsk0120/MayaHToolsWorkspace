"""Maya API 2.0 based scalar attribute plug wrapper."""

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undoable


class Plug:
    """Maya API 2.0 MPlug を扱う scalar 属性ラッパー。

    ``Plug(node, mplug)`` を呼ぶだけで、属性データ型（``_registry`` に登録済みの
    型）や array/compound 属性は自動的に対応する専用クラスのインスタンスとして返る。

    Args:
        node (Node): このプラグを所有する Hlib ノード。
        mplug (om2.MPlug): ラップする Maya API 2.0 プラグ。

    属性の書き込み・接続・ロック変更は、すべて Maya の Undo に対応する。
    """

    _registry = None  #: initialize_plug_api() が構築後に注入する PlugRegistry。

    def __new__(cls, node, mplug):
        if cls is Plug:
            # ArrayPlug/CompoundPlug との循環importを避けるため呼び出し時に遅延importする。
            from .array_plug import ArrayPlug
            from .compound_plug import CompoundPlug

            wrapped = om2.MPlug(mplug)
            if wrapped.isArray:
                return ArrayPlug(node, mplug)
            if cls._registry is not None:
                attr_type = cmds.getAttr(wrapped.name(), type=True)
                resolved_class = cls._registry.lookup(attr_type)
                if resolved_class is not None:
                    return resolved_class(node, mplug)
            if wrapped.isCompound:
                return CompoundPlug(node, mplug)
        return super().__new__(cls)

    def __init__(self, node, mplug):
        """所有ノードと API 2.0 MPlug のコピーを保持する。"""
        self._node = node
        self._mplug = om2.MPlug(mplug)

    def mplug(self):
        """内部で保持する Maya API 2.0 MPlug を返す。

        Returns:
            om2.MPlug: ラップ対象のプラグ。
        """
        return self._mplug

    @property
    def node(self):
        """この Plug を所有する Hlib ノードを取得する。

        Returns:
            Node: 所有ノード。
        """
        return self._node

    @property
    def name(self):
        """ノード名を含まない短いプラグ名を取得する。

        Returns:
            str: 必要な multi インデックスを含むプラグ名。
        """
        return self._mplug.partialName(
            includeNodeName=False,
            includeNonMandatoryIndices=True,
            useLongNames=False,
        )

    @property
    def full_name(self):
        """ノード名を含む完全修飾プラグ名を取得する。

        Returns:
            str: ``node.attribute`` 形式のプラグ名。
        """
        return self._mplug.name()

    @property
    def attribute(self):
        """基になる Maya 属性のロング名を取得する。

        Returns:
            str: MFnAttribute が返す属性名。
        """
        return om2.MFnAttribute(self._mplug.attribute()).name

    def type(self):
        """このプラグを表す現在の Hlib クラスを返す。

        Returns:
            type: 解決済みの Plug サブクラス（例: ``DoubleLinearPlug``）。
        """
        return type(self)

    @property
    def is_array(self):
        """multi 属性か判定する。

        Returns:
            bool: array プラグの場合は ``True``。
        """
        return self._mplug.isArray

    @property
    def is_compound(self):
        """compound 属性か判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        return self._mplug.isCompound

    @property
    def is_element(self):
        """multi 属性の要素プラグか判定する。

        Returns:
            bool: array 要素の場合は ``True``。
        """
        return self._mplug.isElement

    @property
    def is_child(self):
        """compound 属性の子プラグか判定する。

        Returns:
            bool: 子プラグの場合は ``True``。
        """
        return self._mplug.isChild

    @property
    def is_connected(self):
        """入出力接続を持つか判定する。

        Returns:
            bool: 何らかの接続を持つ場合は ``True``。
        """
        return self._mplug.isConnected

    @property
    def is_source(self):
        """出力接続元か判定する。

        Returns:
            bool: 他のプラグへの出力接続を持つ場合は ``True``。
        """
        return self._mplug.isSource

    @property
    def is_destination(self):
        """入力接続先か判定する。

        Returns:
            bool: 他のプラグからの入力接続を持つ場合は ``True``。
        """
        return self._mplug.isDestination

    @property
    def is_locked(self):
        """プラグがロックされているか判定する。

        Returns:
            bool: ロックされている場合は ``True``。
        """
        return self._mplug.isLocked

    @undoable("HlibPlugLock")
    def set_locked(self, state):
        """プラグのロック状態を変更する。

        Args:
            state (bool): ``True`` でロック、``False`` で解除する。

        Returns:
            Plug: 自身。
        """
        cmds.setAttr(self.full_name, lock=bool(state))
        return self

    def get(self, ws=False):
        """評価済みの Maya 属性値を取得する。

        Args:
            ws (bool): ワールド空間値を要求する。汎用 scalar Plug では無視される。

        Returns:
            object: Maya の ``getAttr`` が返す scalar 値。
        """
        value = cmds.getAttr(self.full_name)
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    @undoable("HlibPlugSet")
    def set(self, value):
        """プラグ値を変更する。

        Args:
            value (object): 設定する Maya 互換値。

        Returns:
            Plug: 自身。
        """
        if isinstance(value, str):
            cmds.setAttr(self.full_name, value, type="string")
        elif isinstance(value, (tuple, list)):
            cmds.setAttr(self.full_name, *value)
        else:
            cmds.setAttr(self.full_name, value)
        return self

    def source(self):
        """入力接続元の Plug を取得する。

        Returns:
            Plug | None: 接続元。入力接続がない場合は ``None``。
        """
        sources = self._mplug.connectedTo(True, False)
        return Plug(self._node_from_mplug(sources[0]), sources[0]) if sources else None

    def destinations(self):
        """出力接続先の Plug をすべて取得する。

        Returns:
            list[Plug]: 接続先プラグ。
        """
        return [Plug(self._node_from_mplug(plug), plug) for plug in self._mplug.connectedTo(False, True)]

    @undoable("HlibPlugConnect")
    def connect(self, target, force=False):
        """このプラグを別のプラグへ接続する。

        Args:
            target (Plug): 接続先プラグ。
            force (bool): 既存入力接続を強制的に置き換えるか。

        Returns:
            Plug: 接続先プラグ。

        Raises:
            TypeError: target が Plug でない場合。
        """
        target = self._coerce_plug(target)
        cmds.connectAttr(self.full_name, target.full_name, force=force)
        return target

    @undoable("HlibPlugDisconnect")
    def disconnect(self, target=None):
        """プラグ接続を解除する。

        Args:
            target (Plug | None): 明示的に解除する接続先。省略時は入力元と全出力先を
                解除する。

        Returns:
            Plug: 自身。
        """
        if target is not None:
            target = self._coerce_plug(target)
            cmds.disconnectAttr(self.full_name, target.full_name)
            return self
        source = self.source()
        if source is not None:
            cmds.disconnectAttr(source.full_name, self.full_name)
        for destination in self.destinations():
            cmds.disconnectAttr(self.full_name, destination.full_name)
        return self

    def __str__(self):
        """完全修飾した Maya プラグ名を返す。"""
        return self.full_name

    def __repr__(self):
        """デバッグ用に完全修飾プラグ名を含む表現を返す。"""
        return f"Plug({self.full_name!r})"

    @staticmethod
    def _coerce_plug(value):
        """接続先入力が Plug であることを検証する。"""
        if not isinstance(value, Plug):
            raise TypeError("target must be an Hlib Plug")
        return value

    @staticmethod
    def _node_from_mplug(mplug):
        """MPlug の所有 MObject から汎用 Node ラッパーを生成する。"""
        from ..nodes.node import Node

        return Node(mplug.node())
