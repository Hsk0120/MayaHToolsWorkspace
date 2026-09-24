"""Maya の名前空間の参照・作成・移動・削除を提供する。"""

from contextlib import contextmanager

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorators.undo import undo_chunk


class Namespace:
    """Maya namespaceを表すシーンエンティティ。"""

    def __init__(self, name=":"):
        """Namespace名を正規化してラッパーを初期化する。

        名前を保持するだけで、シーン内の名前空間を作成・存在確認しない。

        Args:
            name (str | Namespace): 名前空間名または既存ラッパー。既定の : はルート。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 空文字列または文字列・Namespace 以外の場合。
        """
        if isinstance(name, Namespace):
            name = name.name()
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._name = self._normalize(name)

    @staticmethod
    def _normalize(name):
        """Namespace名をMayaの絶対表記へ正規化する。

        Args:
            name (str): 正規化する名前。

        Returns:
            str: / を : に置き換え、両端の : を除いて先頭に : を付けた名前。区切り文字だけなら :。
        """
        name = name.replace("/", ":")
        if name == ":" or not name.strip(":"):
            return ":"
        name = name.strip(":")
        return ":" + name

    def name(self):
        """正規化済みの絶対Namespace名を返す。

        Returns:
            str: 先頭が : の保持名。
        """
        return self._name

    def exists(self):
        """NamespaceがMayaシーンに存在するか判定する。

        Returns:
            bool: 保持名の名前空間が現在のシーンに存在すれば True。
        """
        return bool(om2.MNamespace.namespaceExists(self._name))

    def parent(self):
        """親Namespaceを返す。root namespaceの親は ``None``。

        Returns:
            Namespace | None: 名前から求めた親。ルート自身では None。親の存在は確認しない。
        """
        if self._name == ":":
            return None
        parent_name = self._name.rsplit(":", 1)[0] or ":"
        return Namespace(parent_name)

    def children(self):
        """直下の子Namespaceを返す。

        Returns:
            list[Namespace]: 直下の子。自身が存在しない場合は空リスト。
        """
        if not self.exists():
            return []
        names = om2.MNamespace.getNamespaces(self._name, False) or []
        children = []
        prefix = self._name if self._name.endswith(":") else self._name + ":"
        for name in names:
            absolute_name = name if name.startswith(":") else prefix + name
            child = Namespace(absolute_name)
            if child.parent() == self:
                children.append(child)
        return children

    def nodes(self, recurse=False):
        """Namespace内のNodeをhlib wrapperとして返す。

        Args:
            recurse (bool): ``True`` の場合は子Namespace内も含める。

        Returns:
            list[Node]: 名前空間内のノードラッパー。自身が存在しない場合は空リスト。
        """
        if not self.exists():
            return []
        # nodes.node が ..namespaces を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..nodes import Node

        mobjects = om2.MNamespace.getNamespaceObjects(self._name, recurse) or []
        return [Node(mobject) for mobject in mobjects]

    @classmethod
    def current(cls):
        """カレントNamespaceを返す。

        Returns:
            Namespace: 現在のカレントNamespace。
        """
        return cls(om2.MNamespace.currentNamespace())

    @undo_chunk("hlibNamespaceSetCurrent")
    def set_as_current(self):
        """カレントNamespaceを自身へ切り替える。

        Returns:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない場合。
        """
        if not self.exists():
            raise RuntimeError(f"Namespace does not exist: {self._name}")
        cmds.namespace(set=self._name)
        return self

    @contextmanager
    def as_current(self):
        """カレントNamespaceを自身へ一時的に切り替える。

        ブロックを抜けると、例外が発生した場合も含めて元のカレントNamespaceへ戻す。
        ブロック内で元のNamespaceが削除された場合は復元しない。

        Yields:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない場合。
        """
        previous = Namespace.current()
        self.set_as_current()
        try:
            yield self
        finally:
            if previous.exists():
                previous.set_as_current()

    @classmethod
    @undo_chunk("hlibNamespaceCreate")
    def create(cls, name, parent=":"):
        """Namespaceを作成し、作成したNamespaceを返す。

        単一階層の name とルート以外の parent を組み合わせると、作成先は parent 配下だが戻り値の保持名には parent が反映されない。現在の実装では、完全な入れ子名を name に指定すると作成先と戻り値が一致する。

        Args:
            name (str | Namespace): 作成する名前。入れ子の名前なら、その名前に含まれる親を優先する。
            parent (str | Namespace): 単一階層名を作成する親。存在しなければ再帰的に作成する。

        Returns:
            Namespace: name を正規化したラッパー。存在する場合もそのラッパーを返す。

        Raises:
            ValueError: name または parent が不正な場合。
            RuntimeError: Maya が作成を拒否した場合。
        """
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

    @undo_chunk("hlibNamespaceRename")
    def rename(self, name):
        """Namespace自身の名前を変更する。

        Args:
            name (str | Namespace): 新しい名前。最後の階層名だけを使用し、現在の親は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの変更、または名前が不正な場合。
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        if self._name == ":":
            raise ValueError("root namespace cannot be renamed")
        target = Namespace(name)
        parent = self.parent()
        target = Namespace(f"{parent.name()}:{target.name().rsplit(':', 1)[-1]}")
        self._move_contents(target)
        self._name = target.name()
        return self

    @undo_chunk("hlibNamespaceMove")
    def move(self, parent=":"):
        """Namespaceを指定した親Namespaceへ移動する。

        Args:
            parent (str | Namespace): 移動先の既存の親名前空間。末尾の自身の名前は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの移動、または parent が不正な場合。
            RuntimeError: 親が存在しない、移動先が既存、または Maya 操作が失敗した場合。
        """
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
        """Namespaceの内容を別Namespaceへ移し、元Namespaceを削除する。

        移動先を作成し、force=True で内容を移して元を削除する。自身の保持名はここでは更新しない。

        Args:
            target (Namespace): 新規作成する移動先。親は存在している必要がある。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        if target.exists():
            raise RuntimeError(f"Namespace already exists: {target.name()}")
        target_parent = target.parent()
        if target_parent is None or not target_parent.exists():
            raise RuntimeError(f"Namespace does not exist: {target_parent}")
        cmds.namespace(add=target.name().rsplit(":", 1)[-1], parent=target_parent.name())
        cmds.namespace(moveNamespace=(self._name, target.name()), force=True)
        cmds.namespace(removeNamespace=self._name)

    @undo_chunk("hlibNamespaceRemove")
    def remove(self, destination=":"):
        """内容を移動してNamespaceを削除する。

        Args:
            destination (str | Namespace): 内容を移動する既存の名前空間。既定はルート。

        Returns:
            Namespace: 内容を受け取った移動先。自身の保持名は削除前のまま。

        Raises:
            ValueError: ルートの削除、または destination が不正な場合。
            RuntimeError: 移動先が存在しない、または Maya 操作が失敗した場合。
        """
        if self._name == ":":
            raise ValueError("root namespace cannot be removed")
        destination_namespace = Namespace(destination)
        if not destination_namespace.exists():
            raise RuntimeError(f"Namespace does not exist: {destination_namespace.name()}")
        cmds.namespace(moveNamespace=(self._name, destination_namespace.name()), force=True)
        cmds.namespace(removeNamespace=self._name)
        return destination_namespace

    def __str__(self):
        """Namespaceの絶対名を返す。

        Returns:
            str: 正規化済みの保持名。存在確認はしない。
        """
        return self._name

    def __repr__(self):
        """Namespaceのデバッグ表現を返す。

        Returns:
            str: Namespace と保持名を含む文字列表現。
        """
        return f"Namespace({self._name!r})"

    def __eq__(self, other):
        """Namespace名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Namespace 同士は保持名を比較する。異なる型では NotImplemented。
        """
        if not isinstance(other, Namespace):
            return NotImplemented
        return self._name == other._name

    def __hash__(self):
        """Namespace名を使ったハッシュ値を返す。

        Returns:
            int: 現在の保持名のハッシュ。rename/move により変化するため、集合や辞書キーとして保持中の名前変更は避ける。
        """
        return hash(self._name)
