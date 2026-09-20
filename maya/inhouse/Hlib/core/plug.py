"""Maya API 2.0 based attribute plug wrapper."""

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorator.undo import undoable


class Plug:
    """Maya API 2.0 MPlug を扱う属性ラッパー。

    Args:
        node (Node): このプラグを所有する Hlib ノード。
        mplug (om2.MPlug): ラップする Maya API 2.0 プラグ。

    属性の書き込み・接続・ロック変更は、すべて Maya の Undo に対応する。
    """

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

    def get(self):
        """評価済みの Maya 属性値を取得する。

        Returns:
            object: scalar は Maya の ``getAttr`` 値、compound は tuple、array は
            論理インデックスをキーとする dict。
        """
        if self.is_array:
            return {index: self.element(index).get() for index in self._mplug.getExistingArrayAttributeIndices()}
        if self.is_compound:
            return tuple(self.child(index).get() for index in range(self._mplug.numChildren()))
        value = cmds.getAttr(self.full_name)
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    @undoable("HlibPlugSet")
    def set(self, value):
        """プラグ値を変更する。

        Args:
            value (object): 設定する Maya 互換値。compound には子数と同数の
                シーケンスを指定する。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: array プラグへ直接値を設定した場合。
            ValueError: compound 値の要素数が一致しない場合。
        """
        if self.is_array:
            raise TypeError("Set an array element instead of the array plug")
        if self.is_compound:
            values = tuple(value)
            if len(values) != self._mplug.numChildren():
                raise ValueError("Compound plug value length does not match its child count")
            for index, child_value in enumerate(values):
                self.child(index).set(child_value)
            return self
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

    def child(self, name_or_index):
        """compound 属性の子 Plug を取得する。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または子インデックス。

        Returns:
            Plug: 子プラグ。

        Raises:
            TypeError: compound プラグでない場合。
            AttributeError: 指定した子が存在しない場合。
        """
        if not self.is_compound:
            raise TypeError(f"{self.full_name} is not a compound plug")
        if isinstance(name_or_index, int):
            return Plug(self._node, self._mplug.child(name_or_index))
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if name_or_index in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {name_or_index!r} on {self.full_name}")

    def children(self):
        """compound 属性の直接の子 Plug を取得する。

        Returns:
            list[Plug]: 子プラグ。compound でない場合は空リスト。
        """
        if not self.is_compound:
            return []
        return [self.child(index) for index in range(self._mplug.numChildren())]

    def element(self, index, create=False):
        """multi 属性の論理インデックス要素を取得する。

        Args:
            index (int): 論理インデックス。
            create (bool): 存在しない要素も作成対象として取得するか。

        Returns:
            Plug: 要素プラグ。

        Raises:
            TypeError: multi 属性でない場合。
            IndexError: create が ``False`` で要素が存在しない場合。
        """
        if not self.is_array:
            raise TypeError(f"{self.full_name} is not an array plug")
        existing_indices = self._mplug.getExistingArrayAttributeIndices()
        if not create and index not in existing_indices:
            raise IndexError(f"No element at logical index {index} on {self.full_name}")
        mplug = self._mplug.elementByLogicalIndex(index)
        return Plug(self._node, mplug)

    def elements(self):
        """存在する multi 属性要素をすべて取得する。

        Returns:
            list[Plug]: 既存要素。multi 属性でない場合は空リスト。
        """
        if not self.is_array:
            return []
        return [self.element(index) for index in self._mplug.getExistingArrayAttributeIndices()]

    def __getitem__(self, index):
        """multi 属性の論理インデックス要素を取得する。

        Args:
            index (int): 論理インデックス。

        Returns:
            Plug: 対応する要素プラグ。
        """
        return self.element(index)

    def __getattr__(self, name):
        """compound 属性の子を Python 属性形式で取得する。

        Args:
            name (str): 子属性名。

        Returns:
            Plug: 解決した子プラグ。

        Raises:
            AttributeError: private 名または存在しない子を指定した場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.child(name)
        except (AttributeError, TypeError) as error:
            raise AttributeError(f"No plug member named {name!r}") from error

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
        from ..node.node import Node

        return Node(mplug.node())