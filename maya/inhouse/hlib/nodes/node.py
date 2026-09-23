"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorators.undo import undoable
from ..utils import raise_with_notify


def _resolve_node(node):
    """ノード名、MObject、または MDagPath を MObject と MDagPath へ解決する。

    Node._resolve と _node_type_of が共有する下位の解決処理。

    Args:
        node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型の場合。
        RuntimeError: ノード名を解決できない場合。
    """
    if isinstance(node, str):
        selection = om2.MSelectionList()
        try:
            selection.add(node)
        except RuntimeError as original_error:
            raise_with_notify(RuntimeError, f"ノードが見つかりません: {node}", from_exception=original_error)
        mobject = selection.getDependNode(0)
        dag_path = selection.getDagPath(0) if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dag_path
    if isinstance(node, om2.MDagPath):
        dag_path = om2.MDagPath(node)
        return dag_path.node(), dag_path
    if isinstance(node, om2.MObject):
        mobject = om2.MObject(node)
        dag_path = om2.MFnDagNode(mobject).getPath() if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dag_path
    raise TypeError("node には名前、MObject、または MDagPath を指定してください")


def _node_type_of(node):
    """ノード名、MObject、または MDagPath から Maya nodeType 名を得る。

    Args:
        node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

    Returns:
        str: Maya のノード型名。

    Raises:
        TypeError: 対応しない入力型の場合。
        RuntimeError: ノード名を解決できない場合。
    """
    mobject, _ = _resolve_node(node)
    return om2.MFnDependencyNode(mobject).typeName


class Node:
    """Maya の依存ノード・DAG ノードを表す共通ラッパー。

    生成時は登録済みのノード型に対応するラッパーを選択する。"""

    _registry = None  #: hlib.__init__ が構築後に注入する NodeRegistry。

    @classmethod
    def create(cls, type, **kwargs):
        """ノードを作成し、対応する hlib wrapper として返す。

        Args:
            type (str): Maya の nodeType 名。
            **kwargs: ``maya.cmds.createNode`` に渡すキーワード引数。

        Returns:
            Node: 作成したノードに対応する wrapper。

        Raises:
            ValueError: type が空文字列または文字列以外の場合。
        """
        if not isinstance(type, str) or not type:
            raise ValueError("type must be a non-empty string")
        created_name = cmds.createNode(type, **kwargs)
        return cls(created_name)

    def __new__(cls, node, *args, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。
            *args (object): 別の登録クラスに委譲する位置引数。
            **kwargs (object): 別の登録クラスに委譲するキーワード引数。

        Returns:
            Node: 登録クラスのインスタンス。登録情報がなければ呼び出したクラスの未初期化インスタンス。

        Raises:
            TypeError: ノード入力が対応しない型の場合。
            RuntimeError: ノードを解決できない場合。
        """
        registry = cls._registry
        if registry is not None:
            node_type = _node_type_of(node)
            resolved_class = registry.wrapper_class(node_type)
            if resolved_class is not cls:
                return resolved_class(node, *args, **kwargs)
        return super().__new__(cls)

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject = None
        self._dag_path = None
        self._resolve(node)

    def _resolve(self, node):
        """ノード名、MObject、または MDagPath を内部 API オブジェクトへ変換する。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject, self._dag_path = _resolve_node(node)

    def is_valid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isValid()
        )

    def is_alive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isAlive()
        )

    def mobject(self):
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        return self._mobject

    def type(self):
        """Maya の nodeType 名を返す。

        Returns:
            str: 対応する Maya nodeType。
        """
        return om2.MFnDependencyNode(self._mobject).typeName

    @property
    def type_id(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。
        """
        return om2.MFnDependencyNode(self._mobject).typeId.id()

    @property
    def plugin_name(self):
        """ノード型がプラグイン由来の場合、そのプラグイン名を取得する。

        Returns:
            str: プラグイン名。Maya組み込みのノード型では空文字列。
        """
        return om2.MFnDependencyNode(self._mobject).pluginName

    def classification(self):
        """ノード型の分類文字列を取得する。

        Returns:
            list[str]: ``cmds.getClassification`` が返す分類文字列のリスト。
                該当が無い nodeType では空リスト。
        """
        return cmds.getClassification(self.type())

    def is_type(self, node_type):
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``is_type("shape")`` で True になる。

        Args:
            node_type (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに node_type が含まれる場合は True。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not self.is_valid():
            return False
        return node_type in (cmds.nodeType(self.full_name, inherited=True) or [])

    @property
    def is_locked(self):
        """ノード自体がロックされているか判定する。

        属性単位のロックは Plug.is_locked を参照する。

        Returns:
            bool: ロックされている場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isLocked

    @property
    def is_referenced(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isFromReferencedFile

    def is_ancestor_of(self, other):
        """other が自身の DAG 階層上の子孫か判定する。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身より下の階層にある場合は True。自身自身や
                非DAGノード、無効なノードでは False。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        self_full = self.full_name
        other_full = other_node.full_name
        if not self_full or not other_full:
            return False
        return other_full != self_full and other_full.startswith(self_full + "|")

    def is_parent_of(self, other):
        """other が自身の直接の子か判定する（孫以下は対象外）。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身の直接の子の場合は True。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        self_full = self.full_name
        other_full = other_node.full_name
        if not self_full or not other_full:
            return False
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    def is_child_of(self, other):
        """other が自身の直接の親か判定する（祖父母以上は対象外）。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身の直接の親の場合は True。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        return other_node.is_parent_of(self)

    def attribute_count(self):
        """ノードが持つ属性の総数を取得する。

        Returns:
            int: 属性数。
        """
        return om2.MFnDependencyNode(self._mobject).attributeCount()

    def path(self, full=False):
        """DAG ノードのパス名を返す。

        Args:
            full (bool): ``True`` の場合はフルDAGパス、``False`` の場合は
                パーシャルパスを返す。

        Returns:
            str: 指定形式の DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        if self._dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        if full:
            return self._dag_path.fullPathName()
        return self._dag_path.partialPathName()

    def partial_path(self):
        """DAG ノードのパーシャルパス名を返す互換メソッド。

        Returns:
            str: 指定形式の DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        return self.path()

    def full_path(self):
        """DAG ノードのフルパス名を返す互換メソッド。

        Returns:
            str: 完全 DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        return self.path(full=True)

    def is_root(self):
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        if self._dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        return self._dag_path.length() == 1

    def node_name(self, remove_namespace=False):
        """DAG パスを除いたノード名を返す。

        Args:
            remove_namespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``remove_namespace`` が ``True`` の場合は
                namespaceを含まないノード名。
        """
        node_name = om2.MFnDependencyNode(self._mobject).name()
        if remove_namespace:
            node_name = node_name.rsplit(":", 1)[-1]
        return node_name

    def namespace(self):
        """ノードが属するネームスペースを返す。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        # scene.namespace が ..nodes を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..scenes import Namespace

        node_name = self.node_name()
        if ":" not in node_name:
            return Namespace(":")
        return Namespace(node_name.rsplit(":", 1)[0])

    @undoable("hlibNodeRename")
    def rename(self, name, ignore_shape=False):
        """ノード名を変更し、変更後の名前を返す。

        Args:
            name (str): 新しいノード名。
            ignore_shape (bool): ``True`` の場合はShapeの名前変更を抑制する。

        Returns:
            str: Mayaが確定した変更後のノード名。

        Raises:
            RuntimeError: ノード名を変更できない場合。
        """
        return cmds.rename(self.name(), name, ignoreShape=ignore_shape)

    @undoable("hlibNodeSetNamespace")
    def set_namespace(self, namespace):
        """ノードを指定したネームスペースへ移動する。

        Args:
            namespace (str | Namespace): 移動先のnamespace名。末尾の ``":"`` は任意。

        Returns:
            str: Mayaが確定したnamespace付きノード名。

        Raises:
            ValueError: namespaceが空文字列または文字列でない場合。
            RuntimeError: namespace移動に失敗した場合。
        """
        # scene.namespace ⇔ nodes の相互依存を避けるための遅延 import。namespace() と同じ理由。
        from ..scenes import Namespace

        if isinstance(namespace, Namespace):
            target_namespace = namespace
        elif isinstance(namespace, str) and namespace:
            target_namespace = Namespace(namespace)
        else:
            raise ValueError("namespace must be a non-empty string")
        if not target_namespace.exists() and target_namespace.name() != ":":
            target_namespace = Namespace.create(target_namespace)
        namespace_name = target_namespace.name()
        node_name = self.node_name(True)
        new_name = (
            f"{namespace_name}:{node_name}"
            if namespace_name != ":"
            else node_name
        )
        return cmds.rename(self.name(), new_name)

    def _connected_plugs(self, as_source, as_destination, type=None):
        """ノードの指定方向に接続された外部Plugを収集する。

        Args:
            as_source (bool): 接続元Plugを検索対象に含めるかどうか。
            as_destination (bool): 接続先Plugを検索対象に含めるかどうか。
            type (str | None): 指定した場合、接続先ノードの nodeType が
                ``is_type`` で一致するものだけに絞り込む(継承チェーンも判定)。

        Returns:
            list[Plug]: 接続先の外部Plugを重複なしで格納したリスト。
        """
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..plugs.plug import Plug

        plugs = []
        seen = set()
        for mplug in om2.MFnDependencyNode(self._mobject).getConnections():
            for connected in mplug.connectedTo(as_source, as_destination):
                key = connected.name()
                if key in seen:
                    continue
                node = Node(connected.node())
                if type is not None and not node.is_type(type):
                    continue
                seen.add(key)
                plugs.append(Plug(node, connected))
        return plugs

    def inputs(self, type=None):
        """このノードへ入力する接続元Plugを返す。

        Args:
            type (str | None): 指定した場合、接続元ノードの nodeType で絞り込む
                (継承チェーンも判定。例: ``type="animCurve"``)。

        Returns:
            list[Plug]: 入力元の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        return self._connected_plugs(True, False, type=type)

    def outputs(self, type=None):
        """このノードから出力する接続先Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 出力先の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        return self._connected_plugs(False, True, type=type)

    def connections(self, type=None):
        """このノードに接続された外部Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 入力元と出力先の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        plugs = []
        seen = set()
        for plug in self.inputs(type=type) + self.outputs(type=type):
            if plug.full_name in seen:
                continue
            seen.add(plug.full_name)
            plugs.append(plug)
        return plugs

    def plugs(self, **kwargs):
        """ノードの属性を Plug のリストとして列挙する。

        Args:
            kwargs: ``cmds.listAttr`` にそのまま渡す追加フラグ
                (``keyable=True``、``visible=True``、``write=True`` など)。

        Returns:
            list[Plug]: 該当する属性の Plug。``cmds.listAttr`` が返す名前のうち
                実際には評価できないもの（未確保の要素を持つ配列複合属性の子など）は
                黙ってスキップする。該当なしの場合は空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性は列挙できません")
        names = cmds.listAttr(self.full_name, **kwargs) or []
        plugs = []
        for name in names:
            try:
                plugs.append(self.plug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
        return plugs

    def aliases(self):
        """このノードの属性エイリアスを取得する。

        Returns:
            list[tuple[str, Plug]]: ``(エイリアス名, 対応するPlug)`` のリスト。
                エイリアスが無ければ空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードのエイリアスは取得できません")
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（plug() と同じ理由）。
        from ..plugs.plug import Plug

        flat = cmds.aliasAttr(self.full_name, query=True) or []
        pairs = []
        for index in range(0, len(flat), 2):
            alias_name, attribute_name = flat[index], flat[index + 1]
            # 配列要素(例: "weight[0]")は findPlug が解決できないため、
            # ブラケット付き属性パスも扱える MSelectionList 経由で解決する。
            selection = om2.MSelectionList()
            selection.add(f"{self.full_name}.{attribute_name}")
            pairs.append((alias_name, Plug(self, selection.getPlug(0))))
        return pairs

    @undoable("hlibNodeAddAttr")
    def add_attr(
        self,
        long_name,
        attribute_type=None,
        data_type=None,
        default_value=None,
        **kwargs,
    ):
        """属性を追加し、追加したPlugを返す。

        Args:
            long_name (str): 追加する属性のロング名。
            attribute_type (str | None): addAttr の attributeType。data_type と少なくとも一方が必要。
            data_type (str | None): addAttr の dataType。
            default_value (object | None): addAttr の defaultValue。None なら指定しない。
            **kwargs (object): addAttr に渡す追加フラグ。明示引数に対応する短縮フラグは上書きする。

        Returns:
            Plug: 追加した属性の型に対応するプラグ。

        Raises:
            ValueError: long_name が空または文字列以外、あるいは属性型の指定がない場合。
            RuntimeError: Maya が属性追加を拒否した場合。
        """
        if not isinstance(long_name, str) or not long_name:
            raise ValueError("long_name must be a non-empty string")
        if attribute_type is None and data_type is None:
            raise ValueError("attribute_type or data_type is required")
        add_kwargs = dict(kwargs)
        add_kwargs["ln"] = long_name
        if attribute_type is not None:
            add_kwargs["at"] = attribute_type
        if data_type is not None:
            add_kwargs["dt"] = data_type
        if default_value is not None:
            add_kwargs["dv"] = default_value
        cmds.addAttr(self.name(), **add_kwargs)
        return self.plug(long_name)

    def plug(self, name):
        """属性パスに対応する Plug を取得する。

        Args:
            name (str): 属性名または Maya が解決可能な属性パス。

        Returns:
            Plug: 解決した属性プラグ。

        Raises:
            ValueError: 空文字列または文字列以外を指定した場合。
            RuntimeError: ノードが無効な場合。
            AttributeError: 属性を解決できない場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でない属性パスを指定してください")
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性にはアクセスできません")
        # plugs.plug ⇔ nodes の相互依存を避けるための遅延 import。inputs()/outputs() と同じ理由。
        from ..plugs.plug import Plug

        try:
            mplug = om2.MFnDependencyNode(self._mobject).findPlug(name, False)
        except RuntimeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name()}.{name}") from error
        return Plug(self, mplug)

    def attr(self, name):
        """属性プラグを取得する ``plug`` の別名。

        Args:
            name (str): 属性名または属性パス。

        Returns:
            Plug: 解決した属性プラグ。
        """
        return self.plug(name)

    def has_attr(self, name):
        """属性パスを解決できるか判定する。

        Args:
            name (str): 属性名または属性パス。

        Returns:
            bool: 属性を解決できる場合は ``True``。
        """
        try:
            self.plug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

    @property
    def uuid(self):
        """ノードの Maya UUID を返す。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        if not self.is_valid():
            return None
        return om2.MFnDependencyNode(self._mobject).uuid().asString()

    def name(self):
        """Maya の最短一意ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.partialPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    @property
    def full_name(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.fullPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。

        Returns:
            str: 最短一意名。無効なノードでは空文字列。
        """
        return self.name()

    def __repr__(self):
        """デバッグ用にクラス名とノード名を含む表現を返す。

        Returns:
            str: 有効なら型名とノード名、無効なら型名と invalid を含む文字列。
        """
        if self.is_valid():
            return f"{type(self).__name__}({self.name()!r})"
        return f"<{type(self).__name__} invalid>"

    def __getattr__(self, name):
        """通常属性にない名前を Maya Plug として動的に解決する。

        Args:
            name (str): 取得しようとした Python 属性名。

        Returns:
            Plug: 解決した Maya 属性プラグ。

        Raises:
            AttributeError: 非公開名または存在しない Maya 属性を指定した場合。
            RuntimeError: ノードが無効な場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.plug(name)
        except AttributeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name()}.{name}") from error


