"""Maya の名前空間の参照・作成・移動・削除を提供する。"""

from contextlib import contextmanager

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _require_bool, undoChunk


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
            TypeError: 文字列・Namespace 以外の場合。
            ValueError: 空文字列の場合。
        """
        if isinstance(name, Namespace):
            name = name.name
        if not isinstance(name, str):
            raise TypeError("name must be a str")
        if not name:
            raise ValueError("name must be a non-empty string")
        self._name = self._normalize(name)

    def __repr__(self):
        """Namespaceのデバッグ表現を返す。

        Returns:
            str: Namespace と保持名を含む文字列表現。
        """
        return f"Namespace({self._name!r})"

    def __str__(self):
        """Namespaceの絶対名を返す。

        Returns:
            str: 正規化済みの保持名。存在確認はしない。
        """
        return self._name

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

    @classmethod
    def getCurrent(cls):
        """カレントNamespaceを取得する。

        Returns:
            Namespace: 現在のカレントNamespace。
        """
        return cls(om2.MNamespace.currentNamespace())

    @classmethod
    def create(cls, name, parent=":"):
        """指定先の名前空間を作成する。既存なら作成せず参照を返す。

        カレントNamespaceは変更しない。/は:と同じ区切りとして扱う。
        cmds.namespaceでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            name (str | Namespace): 相対名はparent配下、絶対名とNamespace参照はparentを無視する。
                多段名も指定できる。
            parent (str | Namespace): 作成先の親。相対文字列はカレントから解決する。
                既定はルート(:)。存在しない親も再帰的に作成する。

        Returns:
            Namespace: 新規・既存の作成先の完全名を保持するラッパー。

        Raises:
            ValueError: nameまたはparentが不正な場合。
            RuntimeError: Mayaが作成を拒否した場合。

        Note:
            不正文字(``-``・空白・先頭の数字・``#`` 等)はMayaの規則で置き換え、
            置き換え後の名前が既存なら末尾に番号を付ける。戻り値はMayaが実際に作った名前。
        """
        with undoChunk("mlibNamespaceCreate"):
            return cls._create(name, parent)

    @property
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

    def getParent(self):
        """親Namespaceを返す。root namespaceの親は ``None``。

        Returns:
            Namespace | None: 名前から求めた親。ルート自身では None。親の存在は確認しない。
        """
        if self._name == ":":
            return None
        parent_name = self._name.rsplit(":", 1)[0] or ":"
        return Namespace(parent_name)

    def getShortName(self):
        """末端の名前(``:a:b`` なら ``b``)を返す。

        Returns:
            str: 区切りの ``:`` を含まない最後の階層名。ルートでは ``":"``。
        """
        if self._name == ":":
            return ":"
        return self._name.rsplit(":", 1)[-1]

    def split(self):
        """階層ごとの名前のリスト(``:a:b`` なら ``["a", "b"]``)を返す。

        Returns:
            list[str]: 上位から順の階層名。ルートでは空リスト。
        """
        if self._name == ":":
            return []
        return self._name[1:].split(":")

    def getChildren(self, recurse=False):
        """子Namespaceを取得する。

        Args:
            recurse (bool): ``True`` の場合は孫以下の子孫も含める(親が子より先に並ぶ)。既定は直下だけ。

        Returns:
            list[Namespace]: 子(recurse=Trueは子孫)。自身が存在しない場合は空リスト。

        Raises:
            TypeError: recurse が bool 以外の場合。
        """
        _require_bool(recurse, "recurse")
        if not self.exists():
            return []
        names = om2.MNamespace.getNamespaces(self._name, recurse) or []
        children = []
        prefix = self._name if self._name.endswith(":") else self._name + ":"
        for name in names:
            absolute_name = name if name.startswith(":") else prefix + name
            child = Namespace(absolute_name)
            if recurse or child.getParent() == self:
                children.append(child)
        return children

    def getNodes(self, recurse=False):
        """Namespace内のNodeをmlib wrapperとして返す。

        Args:
            recurse (bool): ``True`` の場合は子Namespace内も含める。

        Returns:
            list[Node]: 名前空間内のノードラッパー。自身が存在しない場合は空リスト。
        """
        if not self.exists():
            return []
        # nodes.nodeもcommon.namespaceを参照するため、
        # 循環回避のためここで遅延 import する（mlib で意図的な相互依存の一つ）。
        from ..nodes.node import Node

        mobjects = om2.MNamespace.getNamespaceObjects(self._name, recurse) or []
        # Node(mobject)と同じ解決(DAGは最初のパス)・型選択を、生成の入口の再判定なしで行う。
        return [Node._from_name(mobject) for mobject in mobjects]

    def getNode(self, name):
        """名前空間を付けた名前でノードを取得する(``Namespace(":char").getNode("root")`` は ``char:root``)。

        Args:
            name (str): 名前空間を除いたノード名。DAGパスは各階層に名前空間が要るため、
                ``"grp|char:child"`` のように2階層目以降は名前空間を付けて渡す。

        Returns:
            Node: 実際のノード型に対応するラッパー。

        Raises:
            TypeError: name が文字列以外の場合。
            ValueError: name が空文字列の場合。
            RuntimeError: ノードが存在しない、または一意でない場合。
        """
        if not isinstance(name, str):
            raise TypeError("name must be a str")
        if not name:
            raise ValueError("name must be a non-empty string")
        # nodes.nodeもcommon.namespaceを参照するため、循環回避のためここで遅延 import する。
        from ..nodes.node import Node

        full_name = self._name.rstrip(":") + ":" + name
        return Node._from_name(full_name)

    def setCurrent(self):
        """カレントNamespaceを自身へ切り替える。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Returns:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない場合。
        """
        with undoChunk("mlibNamespaceSetCurrent"):
            if not self.exists():
                raise RuntimeError(f"Namespace does not exist: {self._name}")
            cmds.namespace(set=self._name)
            return self

    @contextmanager
    def asCurrent(self):
        """カレントNamespaceを自身へ一時的に切り替える。

        終了時は例外の有無によらず復元を試みる。元の名前空間が削除済みなら復元しない。
        復元処理の失敗は送出され、ブロック内の例外を置き換え得る。

        Yields:
            Namespace: 自身。

        Raises:
            RuntimeError: 自身が存在しない、またはMayaが切替え・復元を拒否した場合。
        """
        previous = Namespace.getCurrent()
        self.setCurrent()
        try:
            yield self
        finally:
            if previous.exists():
                previous.setCurrent()

    def rename(self, name):
        """Namespace自身の名前を変更する。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            name (str | Namespace): 新しい名前。最後の階層名だけを使用し、現在の親は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの変更、または名前が不正な場合。
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        with undoChunk("mlibNamespaceRename"):
            if self._name == ":":
                raise ValueError("root namespace cannot be renamed")
            target = Namespace(name)
            parent = self.getParent()
            # ルートは先頭で拒否しているため、親は必ずある。
            assert parent is not None
            target = Namespace(f"{parent.name}:{target.name.rsplit(':', 1)[-1]}")
            self._move_contents(target)
            self._name = target.name
            return self

    def move(self, parent=":"):
        """Namespaceを指定した親Namespaceへ移動する。

        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            parent (str | Namespace): 移動先の既存の親名前空間。末尾の自身の名前は維持する。

        Returns:
            Namespace: 保持名を更新した自身。

        Raises:
            ValueError: ルートの移動、または parent が不正な場合。
            RuntimeError: 親が存在しない、移動先が既存、または Maya 操作が失敗した場合。
        """
        with undoChunk("mlibNamespaceMove"):
            if self._name == ":":
                raise ValueError("root namespace cannot be moved")
            parent_namespace = Namespace(parent)
            if not parent_namespace.exists():
                raise RuntimeError(f"Namespace does not exist: {parent_namespace.name}")
            leaf_name = self._name.rsplit(":", 1)[-1]
            target = Namespace(f"{parent_namespace.name}:{leaf_name}")
            self._move_contents(target)
            self._name = target.name
            return self

    def remove(self, destination=":", *, deleteContents=False):
        """内容を移動してNamespaceを削除する。``deleteContents=True`` は内容ごと削除する。

        名前が衝突するノードは、移動時にMayaの規則(cmdsのforce移動)で末尾に番号を付けて改名する。
        ``deleteContents=True`` は ``cmds.namespace(removeNamespace=..., deleteNamespaceContent=True)`` と同じで、
        名前空間内のノードと子Namespaceを削除する(読み込んだアセットの後始末)。名前空間外の子孫も、
        親のDAGノードと一緒に削除される。
        cmdsでUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            destination (str | Namespace): 内容を移動する既存の名前空間。既定はルート。
                deleteContents=True では使わない。
            deleteContents (bool): True なら内容を移動せず削除する。既定 False。

        Returns:
            Namespace | None: 内容を受け取った移動先。deleteContents=True では ``None``。
                自身の保持名は削除前のまま。

        Raises:
            TypeError: deleteContents が bool 以外の場合。
            ValueError: ルートの削除、または destination が不正な場合。
            RuntimeError: 自身・移動先が存在しない、または Maya 操作が失敗した場合。
        """
        _require_bool(deleteContents, "deleteContents")
        with undoChunk("mlibNamespaceRemove"):
            if self._name == ":":
                raise ValueError("root namespace cannot be removed")
            if deleteContents:
                if not self.exists():
                    raise RuntimeError(f"Namespace does not exist: {self._name}")
                cmds.namespace(removeNamespace=self._name, deleteNamespaceContent=True)
                return None
            destination_namespace = Namespace(destination)
            if not destination_namespace.exists():
                raise RuntimeError(f"Namespace does not exist: {destination_namespace.name}")
            cmds.namespace(moveNamespace=(self._name, destination_namespace.name), force=True)
            cmds.namespace(removeNamespace=self._name)
            return destination_namespace

    @classmethod
    def _create(cls, name, parent):
        """createの本体。Undoチャンクは呼出し側が管理する。

        Args:
            name (str | Namespace): createのname。
            parent (str | Namespace): createのparent。

        Returns:
            Namespace: 作成先の完全名を保持するラッパー。
        """
        namespace = cls(name)
        parent_namespace = cls(parent)
        raw_name = name.name if isinstance(name, Namespace) else name.replace("/", ":")
        if namespace.name != ":" and not raw_name.startswith(":"):
            raw_parent = parent.name if isinstance(parent, Namespace) else parent.replace("/", ":")
            if not raw_parent.startswith(":"):
                parent_namespace = cls(cls.getCurrent().name.rstrip(":") + parent_namespace.name)
            namespace = cls(parent_namespace.name.rstrip(":") + namespace.name)
        parent_namespace = namespace.getParent()
        if namespace.exists():
            return namespace
        if parent_namespace is None:
            raise ValueError("root namespace cannot be created")
        if not parent_namespace.exists():
            cls._create(parent_namespace, ":")
        leaf_name = namespace.name.rsplit(":", 1)[-1]
        created_name = cmds.namespace(add=leaf_name, parent=parent_namespace.name)
        if not created_name.startswith(":") and om2.MNamespace.relativeNames():
            created_name = cls.getCurrent().name.rstrip(":") + ":" + created_name
        return cls(created_name)

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

    def _move_contents(self, target):
        """Namespaceの内容を別Namespaceへ移し、元Namespaceを削除する。

        移動先を作成し、force=True で内容を移して元を削除する。自身の保持名はここでは更新しない。

        Args:
            target (Namespace): 新規作成する移動先。親は存在している必要がある。Undoチャンクは呼出し側が管理する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 移動先が既存、親が存在しない、または Maya 操作が失敗した場合。
        """
        if target.exists():
            raise RuntimeError(f"Namespace already exists: {target.name}")
        target_parent = target.getParent()
        if target_parent is None or not target_parent.exists():
            raise RuntimeError(f"Namespace does not exist: {target_parent}")
        leaf_name = target.name.rsplit(":", 1)[-1]
        cmds.namespace(add=leaf_name, parent=target_parent.name)
        cmds.namespace(moveNamespace=(self._name, target.name), force=True)
        cmds.namespace(removeNamespace=self._name)
