"""Mayaシーン内の単一対象を表す共通基底と、選択リストによる対象の判別補助。"""

import maya.api.OpenMaya as om2


#: PyMEL・maya.cmdsでよく使う名前と、mlibでの書き方の対応。値は (必要なメソッド名, 案内)、またはその組の列。
#: 必要なメソッドが対象のクラスに無い案内は表示せず、列では最初に当てはまる案内を使う(None は常に表示する)。
_MEMBER_HINTS = {
    "getAttr": ("getPlug", "use getPlug(name).get()"),
    "setAttr": ("getPlug", "use getPlug(name).set(value)"),
    "attr": ("getPlug", "use getPlug(name)"),
    "listAttr": ("getPlugs", "use getPlugs()"),
    "hasAttribute": ("hasAttr", "use hasAttr(name)"),
    "attributeExists": ("hasAttr", "use hasAttr(name)"),
    "addAttribute": ("addAttr", "use addAttr(name, ...)"),
    "deleteAttr": ("getPlug", "use getPlug(name).delete()"),
    "connectAttr": ("getPlug", "use getPlug(name).connectTo(destination)"),
    "disconnectAttr": ("getPlug", "use getPlug(name).disconnect()"),
    "lockAndHide": (("setAttrFlags", "use setAttrFlags(names, locked=True, keyable=False, channelBox=False)"),
                    ("setFlags", "use setFlags(locked=True, keyable=False, channelBox=False)")),
    "lockNode": ("setLocked", "use setLocked(True)"),
    "listConnections": ("getConnections", "use getConnections()"),
    "connections": ("getConnections", "use getConnections()"),
    "inputs": ("getSource", "use getSource()"),
    "outputs": ("getDestinations", "use getDestinations()"),
    "listRelatives": ("getChildren", "use getChildren() or getParent()"),
    "getAllChildren": ("getChildren", "use getChildren(allDescendents=True)"),
    "listHistory": ("getHistory", "use getHistory()"),
    "history": ("getHistory", "use getHistory()"),
    "firstParent": ("getParent", "use getParent()"),
    "getAllParents": ("getParents", "use getParents()"),
    "parent": ("setParent", "use setParent(parent) or getParent()"),
    "nodeType": ("getType", "use getType()"),
    "type": ("getType", "use getType()"),
    "name": ("getName", "use getName(), or getNodeName() for the name without the DAG path"),
    "nodeName": ("getNodeName", "use getNodeName()"),
    "longName": ("getFullName", "use getFullName()"),
    "fullPath": ("getFullName", "use getFullName()"),
    "fullPathName": ("getFullName", "use getFullName()"),
    "shortName": ("getNodeName", "use getNodeName()"),
    "exists": ("isValid", "use isValid()"),
    "getTranslate": ("getTranslation", "use getTranslation(), or t.get() for the translate channel"),
    "setTranslate": ("setTranslation", "use setTranslation((x, y, z)), or t.set((x, y, z)) for the translate channel"),
    "getRotation": ("getRotate", "use getRotate()"),
    "setRotation": ("setRotate", "use setRotate((x, y, z))"),
    "xform": ("setMatrix", "use getMatrix()/setMatrix() or getTranslation()/setTranslation()"),
    "getTransformation": ("getMatrix", "use getMatrix()"),
    "setTransformation": ("setMatrix", "use setMatrix(matrix)"),
    "orientJoint": ("orient", "use orient()"),
    "getValue": ("get", "use get()"),
    "setValue": ("set", "use set(value)"),
    "lock": ("setLocked", "use setLocked(True)"),
    "connect": ("connectTo", "use connectTo(destination)"),
    "select": (None, "use mlib.select(obj)"),
    "duplicate": (None, "use mlib.duplicate(obj)"),
}


def _exists(name):
    """名前がシーンの対象に解決できるか、選択リストへの追加で調べる。

    一意な完全名に対しては ``cmds.objExists`` と同じ結果になる(範囲外のコンポーネント番号や
    マルチアトリビュートの未作成要素も True)。

    Args:
        name (str): 調べる完全名。

    Returns:
        bool: 選択リストへ追加できた場合 True。
    """
    try:
        om2.MSelectionList().add(name)
    except RuntimeError:
        return False
    return True


def _selection_plug(selection, index):
    """選択リストの要素がアトリビュートなら、そのMPlugを取得する。

    ``MSelectionList.getPlug`` はノード・コンポーネントの要素で RuntimeError または
    TypeError(Mayaの版で異なる)になるため、両方をNoneに読み替える。

    Args:
        selection (om2.MSelectionList): 選択リスト。
        index (int): 要素の番号。

    Returns:
        om2.MPlug | None: アトリビュートの要素ならMPlug。それ以外、またはnullのMPlugならNone。
    """
    try:
        plug = selection.getPlug(index)
    except (RuntimeError, TypeError):
        return None
    if plug.isNull:
        return None
    return plug


def _selection_component(selection, index):
    """選択リストの要素がコンポーネントなら、所有DAGパスとコンポーネントを取得する。

    ``MSelectionList.getComponent`` はDGノードの要素で RuntimeError または TypeError になり、
    DAGノード単体ではnullのコンポーネントを返すため、どちらもNoneに読み替える。

    Args:
        selection (om2.MSelectionList): 選択リスト。
        index (int): 要素の番号。

    Returns:
        tuple[om2.MDagPath, om2.MObject] | None: コンポーネントの要素なら(所有DAGパス, コンポーネント)。
            DGノード・DAGノード単体ならNone。
    """
    try:
        path, component = selection.getComponent(index)
    except (RuntimeError, TypeError):
        return None
    if component.isNull():
        return None
    return path, component


def _missing_member_message(obj, name, what="method"):
    """存在しないメソッド・アトリビュートを参照したときのAttributeErrorの文言を作る。

    クラスの公開メンバーから近い名前を候補に挙げ、PyMEL・maya.cmdsの名前にはmlibでの
    書き方を案内する。

    Args:
        obj (object): 参照した対象。
        name (str): 参照した名前。
        what (str): 文言に使う種類(``"method or Maya attribute"`` 等)。

    Returns:
        str: 例外の文言。
    """
    # difflibは失敗時の文言を作るときだけ使うため、import mlibの時間に含めない。
    import difflib

    cls = type(obj)
    message = f"'{cls.__name__}' has no {what} '{name}'"
    hint = _MEMBER_HINTS.get(name, ())
    for required, text in (hint if hint and isinstance(hint[0], tuple) else (hint,) if hint else ()):
        if required is None or hasattr(cls, required):
            message += f"; {text}"
            break
    public = sorted({member for member in dir(cls) if not member.startswith("_")})
    close = difflib.get_close_matches(name, public, n=3, cutoff=0.6)
    if close:
        message += ". Did you mean: " + ", ".join(close) + "?"
    return message


class _ObjectType(type):
    """Objectへの入力だけを振り分け、派生クラスの構築は通常通り行う。"""

    def __call__(cls, *args, **kwargs):
        """Objectの呼出しだけを参照の型判別へ渡し、派生クラスは通常どおり構築する。

        Objectが解決したNode・Plug・Componentへ、再び初期化を行わない。

        Args:
            *args: Objectでは単一の参照入力。派生クラスではその構築に渡す位置引数。
            **kwargs: 参照の入力解決、または派生クラスの構築に渡すキーワード引数。

        Returns:
            Object: 解決した参照、または構築した派生クラスのインスタンス。
        """
        if cls is Object:
            return cls._resolve_input(*args, **kwargs)
        return super().__call__(*args, **kwargs)


class Object(metaclass=_ObjectType):
    """Node・Plug・単数Componentの共通基底。

    対象の検索には :func:`~mlib.ls` を使う。
    入力した単一対象の種類を保って解決し、所有ノードへの変換は行わない。
    既存のObjectは削除済みでも同じインスタンスを返す。
    複数対象は受け付けず、ノード作成・複製・選択変更は行わない。
    """

    def asString(self):
        """現在の対象名を文字列へ変換する。

        Node・Plug・Componentそれぞれの ``str()`` と同じ名前を返す。
        名前変更や親子付け替えに追従し、名前をキャッシュしない。
        無効な参照の扱いも各型の ``str()`` に従う。

        Returns:
            str: Mayaコマンドへ渡す対象名。

        Raises:
            RuntimeError: 各型の文字列変換が無効な参照を拒否する場合。
        """
        return str(self)

    @staticmethod
    def _resolve_input(value):
        """単一対象をNode・Plug・Componentへ解決する。

        Args:
            value (str | Object | om2.MObject | om2.MDagPath | om2.MPlug | tuple):
                名前・既存ラッパー・API参照。APIコンポーネントは ``(MDagPath, MObject)`` の組。

        Returns:
            Object: 既存ラッパーなら無効でも同じインスタンス。それ以外は種類に応じた新しい参照。

        Raises:
            TypeError: 入力型・MObjectの種類・APIコンポーネントの組や種類が未対応の場合。
            ValueError: 空文字列・空MPlug、またはコンポーネントが単一要素でない場合。
            IndexError: APIコンポーネントの番号がシェイプの範囲外の場合。
            RuntimeError: 名前が存在しない・一意でない、またはAPI参照が無効の場合。
        """
        from ..nodes.node import Node
        from ..plugs.plug import Plug
        from ..components.component import Component
        if isinstance(value, Object):
            return value
        if isinstance(value, om2.MPlug):
            return Plug._resolve_input(value)
        if isinstance(value, (om2.MObject, om2.MDagPath)):
            return Node._resolve_input(value)
        if isinstance(value, tuple):
            return Component._resolve_input(value)
        if not isinstance(value, str):
            raise TypeError("Expected a scene object reference or name")
        if not value:
            raise ValueError("Expected a non-empty object name")
        selection = om2.MSelectionList()
        selection.add(value)
        if selection.length() != 1:
            raise RuntimeError(f"Object requires one unambiguous target: {value}")
        if _selection_plug(selection, 0) is not None:
            return Plug._resolve_input(value)
        found = _selection_component(selection, 0)
        if found is not None:
            return Component._resolve_input(found)
        return Node._resolve_input(value)

    @staticmethod
    def _classes():
        """循環 import を避けるため、判定に使う mlib クラスを呼び出し時に取得する。

        Returns:
            tuple[type, type, type, type]: Node、Plug、Component、Components。
        """
        from ..components.component import Component, Components
        from ..nodes.node import Node
        from ..plugs.plug import Plug

        return Node, Plug, Component, Components

    @staticmethod
    def _unsupported(value):
        """対応しない入力型の TypeError を作る。

        Args:
            value (object): 入力値。

        Returns:
            TypeError: 送出する例外。
        """
        return TypeError(
            f"Expected str, Node, Plug, Component, om2.MObject, om2.MDagPath or om2.MPlug, "
            f"not {type(value).__name__}"
        )

    @staticmethod
    def _name(value, node_class, plug_class, component_class):
        """単一の対象を名前へ変換する(Object._input_name の本体)。

        Args:
            value (object): 変換対象。
            node_class (type): Node クラス。
            plug_class (type): Plug クラス。
            component_class (type): Component クラス。

        Returns:
            str: maya.cmds へ渡せる名前。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 空文字列、または無効な対象の場合。
        """
        from ..nodes.node import Node as _InputNode
        from ..plugs.plug import Plug as _InputPlug
        if isinstance(value, str):
            name = value
        elif isinstance(value, node_class):
            name = value.getFullName()
            if not name:
                raise ValueError("Cannot use an invalid (deleted) Node")
        elif isinstance(value, plug_class):
            name = value.getFullName()
            if not name:
                raise ValueError("Cannot use an invalid Plug (its node or attribute was deleted)")
        elif isinstance(value, component_class):
            try:
                name = value.getFullName()
            except (RuntimeError, IndexError) as error:
                raise ValueError(f"Cannot use an invalid Component: {error}") from error
        elif isinstance(value, om2.MPlug):
            name = _InputPlug._mplug_name(value)
        elif isinstance(value, om2.MDagPath):
            if not value.isValid() or not om2.MObjectHandle(value.node()).isValid():
                raise ValueError("Cannot use an invalid (deleted) MDagPath")
            name = value.fullPathName()
        elif isinstance(value, om2.MObject):
            name = _InputNode._mobject_name(value)
        else:
            raise Object._unsupported(value)
        if not name:
            raise ValueError("Expected a non-empty object name")
        return name

    @staticmethod
    def _input_name(value):
        """単一の対象を maya.cmds へ渡せる一意な名前へ変換する。

        文字列は解決せず(Maya へ問い合わせず)そのまま返す。解決済みの Node が
        必要な場合は Node._resolve_input を使う。変換規則はモジュールの説明を参照。

        Args:
            value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                変換対象。

        Returns:
            str: maya.cmds で解決できる名前。

        Raises:
            TypeError: 対応しない型、依存ノード以外を指す MObject、または
                Components などの複数の対象を渡した場合(Object._input_names を使う)。
            ValueError: 空文字列、または無効な(削除済み・範囲外の)対象の場合。
        """
        node_class, plug_class, component_class, _ = Object._classes()
        return Object._name(value, node_class, plug_class, component_class)

    @staticmethod
    def _flatten_inputs(values):
        """対象列を一度だけ展開する。型別の混在規則は呼出し側が検証する。

        Args:
            values (object): 単数参照または入れ子の反復可能な対象列。

        Returns:
            list: 順序を保持した対象。Componentsは範囲圧縮のため展開しない。

        Raises:
            TypeError: 未対応型の場合。
        """
        singles = (str,) + Object._classes() + (om2.MObject, om2.MDagPath, om2.MPlug)
        result = []

        def collect(value):
            """単数参照を保持し、容器だけを展開する。"""
            if isinstance(value, singles):
                result.append(value)
                return
            try:
                iterator = iter(value)
            except TypeError:
                raise Object._unsupported(value) from None
            for item in iterator:
                collect(item)

        collect(values)
        return result

    @staticmethod
    def _input_names(values, allow_plugs=True):
        """単一の対象・コレクション・反復可能オブジェクトを名前のリストへ正規化する。

        単一の対象(Object._input_name が受け付ける型)は1要素のリストになる。``Components``・
        ``Selection``・``Joints`` などのコレクションと、list/tuple/set/ジェネレーター
        などの反復可能オブジェクトは、入れ子も含めて保持順に展開する。
        ``MultiPlug`` は要素へ展開せず、マルチアトリビュートそのものの名前として扱う。
        ``Components`` は全番号をまとめて1回だけ検証し、保持順で連続する番号を
        ``|cube|cubeShape.vtx[0:9]`` のような範囲指定の名前にまとめる(要素数が多くても
        maya.cmds へ渡す名前が増えない)。

        Args:
            values (object): 変換対象。単一の対象、または対象を要素に持つ反復可能オブジェクト。
            allow_plugs (bool): False の場合、Plug(``MultiPlug`` を含む)と ``om2.MPlug`` を
                TypeError にする(アトリビュートを渡しても maya.cmds が何もしないコマンド用。文字列は
                解決しないため対象外)。

        Returns:
            list[str]: 正規化した名前のリスト。空の反復可能オブジェクトは空リスト。

        Raises:
            TypeError: いずれかの要素が対応しない型の場合。allow_plugs が False で、
                Plug・MPlug が含まれる場合。同じ対象列に文字列とNodeが混在する場合。
            ValueError: いずれかの要素が空文字列、または無効な対象の場合。
        """
        from ..nodes.node import Nodes as _InputNodes
        node_class, plug_class, component_class, components_class = Object._classes()
        singles = (str, node_class, plug_class, component_class, om2.MObject, om2.MDagPath, om2.MPlug)
        names = []

        def collect(value):
            """単数参照を名前にし、Componentsは範囲名へまとめ、容器だけを展開する。"""
            if not allow_plugs and isinstance(value, (plug_class, om2.MPlug)):
                raise TypeError(
                    f"Attributes (Plug, MPlug) are not accepted here: {type(value).__name__} "
                    "(pass plug.getNode() to target the owning node)"
                )
            if isinstance(value, singles):
                names.append(Object._name(value, node_class, plug_class, component_class))
                return
            if isinstance(value, components_class):
                try:
                    # 全番号の検証はコレクションごとに1回だけ行い、連続する番号は範囲指定にまとめる。
                    names.extend(value.getCompactNames())
                except (RuntimeError, IndexError) as error:
                    raise ValueError(f"Cannot use an invalid Component: {error}") from error
                return
            try:
                iterator = iter(value)
            except TypeError:
                raise Object._unsupported(value) from None
            for item in iterator:
                collect(item)

        items = Object._flatten_inputs(values)
        _InputNodes._validate_inputs(items)
        collect(items)
        return names
