"""Maya namespace wrapper."""

import maya.cmds as cmds

from ..decorators.undo import undoable


class Namespace:
    """Maya namespaceを表すシーンエンティティ。"""

    def __init__(self, name=":"):
        """Namespace名を正規化してラッパーを初期化する。"""
        if isinstance(name, Namespace):
            name = name.name()
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._name = self._normalize(name)

    @staticmethod
    def _normalize(name):
        """Namespace名をMayaの絶対表記へ正規化する。"""
        name = name.replace("/", ":")
        if name == ":" or not name.strip(":"):
            return ":"
        name = name.strip(":")
        return ":" + name

    def name(self):
        """正規化済みの絶対Namespace名を返す。"""
        return self._name

    def exists(self):
        """NamespaceがMayaシーンに存在するか判定する。"""
        return bool(cmds.namespace(exists=self._name))

    def parent(self):
        """親Namespaceを返す。root namespaceの親は ``None``。"""
        if self._name == ":":
            return None
        parent_name = self._name.rsplit(":", 1)[0] or ":"
        return Namespace(parent_name)

    def children(self):
        """直下の子Namespaceを返す。"""
        if not self.exists():
            return []
        names = cmds.namespaceInfo(
            self._name,
            listOnlyNamespaces=True,
            recurse=False,
            absoluteName=True,
        ) or []
        children = []
        prefix = self._name if self._name.endswith(":") else self._name + ":"
        for name in names:
            absolute_name = name if name.startswith(":") else prefix + name
            child = Namespace(absolute_name)
            if child.parent() == self:
                children.append(child)
        return children

    def nodes(self, recurse=False):
        """Namespace内のNodeをHlib wrapperとして返す。

        Args:
            recurse (bool): ``True`` の場合は子Namespace内も含める。
        """
        if not self.exists():
            return []
        from ..nodes import Node

        names = cmds.namespaceInfo(
            self._name,
            listOnlyDependencyNodes=True,
            recurse=recurse,
            absoluteName=True,
        ) or []
        return [Node(name) for name in names]

    @classmethod
    @undoable("HlibNamespaceCreate")
    def create(cls, name, parent=":"):
        """Namespaceを作成し、作成したNamespaceを返す。"""
        namespace = cls(name)
        parent_namespace = cls(parent)
        if ":" in namespace.name().strip(":"):
            parent_namespace = namespace.parent()
        if namespace.exists():
            return namespace
        if parent_namespace is None:
            raise ValueError("root namespace cannot be created")
        if not parent_namespace.exists():
            cls.create(parent_namespace)
        leaf_name = namespace.name().rsplit(":", 1)[-1]
        cmds.namespace(add=leaf_name, parent=parent_namespace.name())
        return namespace

    @undoable("HlibNamespaceRename")
    def rename(self, name):
        """Namespace自身の名前を変更する。"""
        if self._name == ":":
            raise ValueError("root namespace cannot be renamed")
        target = Namespace(name)
        parent = self.parent()
        target = Namespace(f"{parent.name()}:{target.name().rsplit(':', 1)[-1]}")
        self._move_contents(target)
        self._name = target.name()
        return self

    @undoable("HlibNamespaceMove")
    def move(self, parent=":"):
        """Namespaceを指定した親Namespaceへ移動する。"""
        if self._name == ":":
            raise ValueError("root namespace cannot be moved")
        parent_namespace = Namespace(parent)
        if not parent_namespace.exists():
            raise RuntimeError(f"Namespace does not exist: {parent_namespace.name()}")
        leaf_name = self._name.rsplit(":", 1)[-1]
        target = Namespace(f"{parent_namespace.name()}:{leaf_name}")
        self._move_contents(target)
        self._name = target.name()
        return self

    def _move_contents(self, target):
        """Namespaceの内容を別Namespaceへ移し、元Namespaceを削除する。"""
        if target.exists():
            raise RuntimeError(f"Namespace already exists: {target.name()}")
        target_parent = target.parent()
        if target_parent is None or not target_parent.exists():
            raise RuntimeError(f"Namespace does not exist: {target_parent}")
        cmds.namespace(add=target.name().rsplit(":", 1)[-1], parent=target_parent.name())
        cmds.namespace(moveNamespace=(self._name, target.name()), force=True)
        cmds.namespace(removeNamespace=self._name)

    @undoable("HlibNamespaceRemove")
    def remove(self, destination=":"):
        """内容を移動してNamespaceを削除する。"""
        if self._name == ":":
            raise ValueError("root namespace cannot be removed")
        destination_namespace = Namespace(destination)
        if not destination_namespace.exists():
            raise RuntimeError(f"Namespace does not exist: {destination_namespace.name()}")
        cmds.namespace(moveNamespace=(self._name, destination_namespace.name()), force=True)
        cmds.namespace(removeNamespace=self._name)
        return destination_namespace

    def __str__(self):
        """Namespaceの絶対名を返す。"""
        return self._name

    def __repr__(self):
        """Namespaceのデバッグ表現を返す。"""
        return f"Namespace({self._name!r})"

    def __eq__(self, other):
        """Namespace名を基準に同一性を判定する。"""
        if not isinstance(other, Namespace):
            return NotImplemented
        return self._name == other._name

    def __hash__(self):
        """Namespace名を使ったハッシュ値を返す。"""
        return hash(self._name)
