"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

from hlib.object import Object

import contextlib
import inspect
from typing import Any

from .._core.collection import bulk_api
from .._core.flags import normalize_flags
from .._core.registry import collection_export

from ..decorators._fast import fast_edit

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from ..utils import raise_with_notify


def _resolve_node(node):
    """ノードを表す入力を MObject と MDagPath へ解決する。

    Node.__new__ (ラッパー型の選択)と Node._resolve が共有する下位の解決処理。
    Node(...) の生成では __new__ で1回だけ呼び、結果を __init__ へ引き継ぐ。Plug・MPlug は
    所有ノード、コンポーネント(単体・複数形)は所有シェイプへ解決する。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
            ``"node.attribute"`` や ``"pCube1.vtx[0]"`` のような文字列も所有ノードへ解決する
            (インスタンス化されたノードは、名前が指すインスタンスのパスを保持する)。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (:class:`hlib.plugs.plug.DeletedAttributeError`。``RuntimeError`` の派生でもある)。
        RuntimeError: 名前を解決できない(存在しない、または複数の対象に一致する)場合、
            または空・無効な(削除済みの)ラッパーや om2 オブジェクトを指定した場合。
    """
    from hlib.plugs.plug import Plug as _InputPlug
    from hlib.plugs.plug import DeletedAttributeError
    if isinstance(node, str):
        selection = om2.MSelectionList()
        try:
            selection.add(node)
        except RuntimeError as original_error:
            # MSelectionList は複数のノードに一致する名前も「存在しない」として拒否するため、
            # 利用者が原因を判別できるよう maya.cmds で一致数を確かめてからメッセージを選ぶ。
            if node and len(cmds.ls(node) or []) > 1:
                message = f"名前が一意ではありません(複数のノードに一致します): {node}"
            else:
                message = f"ノードが見つかりません: {node}"
            raise_with_notify(RuntimeError, message, from_exception=original_error)
        if selection.length() != 1:
            # "dup.tx" のようなプラグ名・コンポーネント名は、同名ノードがあると複数の要素になる。
            raise_with_notify(
                RuntimeError,
                f"名前が一意ではありません(複数の対象に一致します): {node}",
                from_exception=None,
            )
        return Node._selection_owner(selection, 0, node)
    if isinstance(node, om2.MDagPath):
        if not node.isValid() or not om2.MObjectHandle(node.node()).isValid():
            raise RuntimeError("無効な(削除済みの)MDagPath からノードは解決できません")
        dagPath = om2.MDagPath(node)
        return dagPath.node(), dagPath
    if isinstance(node, om2.MObject):
        if node.isNull():
            raise RuntimeError("空の MObject からノードは解決できません")
        if not om2.MObjectHandle(node).isValid():
            raise RuntimeError("削除済みノードの MObject からノードは解決できません")
        if not node.hasFn(om2.MFn.kDependencyNode):
            raise TypeError("MObject には依存ノードを指定してください(アトリビュート・コンポーネント・データは不可)")
        mobject = om2.MObject(node)
        dagPath = om2.MFnDagNode(mobject).getPath() if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dagPath
    if isinstance(node, om2.MPlug):
        if node.isNull:
            raise RuntimeError("空の MPlug からノードは解決できません")
        owner = node.node()
        # 所有ノードが有効でも、deleteAttr で削除されたアトリビュートの MPlug は削除済みの対象として扱う
        # (hlib のコマンドと同じ。所有ノードが削除済みなら下の MObject の解決で RuntimeError)。
        if om2.MObjectHandle(owner).isValid() and not _InputPlug._mplug_attribute_exists(node, owner):
            raise DeletedAttributeError("削除済みのアトリビュートの MPlug からノードは解決できません")
        return _resolve_node(owner)
    if isinstance(node, Node):
        if not node.isValid():
            raise RuntimeError("無効な(削除済みの)ノードは指定できません")
        dagPath = node._current_dag_path()
        return om2.MObject(node._mobject), om2.MDagPath(dagPath) if dagPath is not None else None
    # plugs/components は nodes を逆方向に import するため、循環回避のため遅延 import する。
    from ..components.component import Component, Components
    from ..plugs.plug import Plug

    if isinstance(node, Plug):
        error = _InputPlug._deleted_attribute_error(node)
        if error is not None:
            raise error
        return _resolve_node(node.node)
    if isinstance(node, (Component, Components)):
        return _resolve_node(node.shape)
    raise TypeError(
        "node には名前、Node、Plug、Component、MObject、MDagPath、または MPlug を指定してください"
    )


def _is_deleted_api_object(value):
    """om2 オブジェクトが削除済みのノードを指すか判定する(空のオブジェクトは False)。

    Args:
        value (object): 判定する値。om2 の MObject・MDagPath・MPlug 以外は False。

    Returns:
        bool: 削除済みのノードを指す MObject・MDagPath・MPlug の場合は True。
            無効な MDagPath は、空のパスも含めて True(``Node(...)`` も区別しない)。
    """
    if isinstance(value, om2.MPlug):
        if value.isNull:
            return False
        value = value.node()
    if isinstance(value, om2.MDagPath):
        return not value.isValid() or not om2.MObjectHandle(value.node()).isValid()
    if isinstance(value, om2.MObject):
        return not value.isNull() and not om2.MObjectHandle(value).isValid()
    return False


def _query_target(other):
    """判定メソッド(``isParentOf`` など)の対象をノードへ解決する。

    ``hlib.nodes.Node._resolve_input`` と同じ規則で解決し、削除済みの対象(削除済みの Node、
    所有ノードが削除済みの Plug・Component、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug、
    削除済みのノードを指す om2 オブジェクト)は例外にせず None を返す(判定は False)。

    Args:
        other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            判定対象。

    Returns:
        Node | None: 解決した有効なノード。削除済みの対象は None。

    Raises:
        TypeError: 対応しない型の場合。
        RuntimeError: 名前を解決できない(存在しない、または複数のノードに一致する)場合、
            または空の MObject・MPlug の場合。
    """
    from hlib.plugs.plug import DeletedAttributeError

    try:
        node = Node._resolve_input(other)
    except DeletedAttributeError:
        return None
    except RuntimeError:
        if _is_deleted_api_object(other):
            return None
        raise
    return node if node.isValid() else None


_MOVABLE_NUMERIC_TYPES = {
    om2.MFnNumericData.kBoolean: "bool",
    om2.MFnNumericData.kByte: "byte",
    om2.MFnNumericData.kShort: "short",
    om2.MFnNumericData.kInt: "long",
    om2.MFnNumericData.kLong: "long",
    om2.MFnNumericData.kFloat: "float",
    om2.MFnNumericData.kDouble: "double",
}  #: moveAttributeOrder() が再作成できる数値アトリビュート型と cmds.addAttr(attributeType=) の対応。


def _dump_movable_attr(plug):
    """並び替え対応の単純な動的アトリビュートから再作成に必要な情報を集める。

    数値(bool/byte/short/long/float/double)、enum、文字列型の非複合・非配列
    トップレベル動的アトリビュートのみ対応する。

    Args:
        plug (Plug): ダンプ対象の動的アトリビュートプラグ。

    Returns:
        dict: addAttribute() での再作成と値・状態の復元に必要な情報。

    Raises:
        TypeError: 複合・配列アトリビュート、または対応しないアトリビュート型の場合。
    """
    if plug.isArray() or plug.isCompound():
        raise TypeError(f"Cannot reorder compound or array attributes: {plug.fullName()}")
    attr = plug.mplug().attribute()
    info = {
        "longName": plug.attributeName(),
        "niceName": plug.niceName(),
        "hidden": plug.isHidden(),
        "keyable": plug.isKeyable(),
        "channelBox": bool(cmds.getAttr(plug.fullName(), channelBox=True)),
        "locked": plug.isLocked(),
        "value": plug.get(),
        "source": plug.source(),
        "destinations": plug.destinations(),
    }
    if attr.hasFn(om2.MFn.kNumericAttribute):
        numeric_type = om2.MFnNumericAttribute(attr).numericType()
        type_name = _MOVABLE_NUMERIC_TYPES.get(numeric_type)
        if type_name is None:
            raise TypeError(f"Unsupported numeric attribute type for reordering: {plug.fullName()}")
        info["attributeType"] = type_name
        if plug.hasMin():
            info["min"] = plug.min()
        if plug.hasMax():
            info["max"] = plug.max()
        info["defaultValue"] = plug.default()
    elif attr.hasFn(om2.MFn.kEnumAttribute):
        info["attributeType"] = "enum"
        info["enumName"] = cmds.attributeQuery(plug.attributeName(), node=plug.node.fullName(), listEnum=True)[0]
        info["defaultValue"] = plug.default()
    elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
        info["dataType"] = "string"
    else:
        raise TypeError(f"Unsupported attribute type for reordering: {plug.fullName()}")
    return info


def _create_movable_attr(node, info):
    """_dump_movable_attr() が集めた情報からアトリビュートを再作成し、値・状態を復元する。

    Args:
        node (Node): アトリビュートを追加する対象ノード。
        info (dict): _dump_movable_attr() が返した情報。

    Returns:
        Plug: 再作成したアトリビュートプラグ。
    """
    kwargs = {"hidden": info["hidden"]}
    if info["niceName"]:
        kwargs["niceName"] = info["niceName"]
    if "min" in info:
        kwargs["minValue"] = info["min"]
    if "max" in info:
        kwargs["maxValue"] = info["max"]
    if "enumName" in info:
        kwargs["enumName"] = info["enumName"]
    plug = node.addAttribute(
        info["longName"],
        attributeType=info.get("attributeType"),
        dataType=info.get("dataType"),
        defaultValue=info.get("defaultValue"),
        **kwargs,
    )
    plug.set(info["value"])
    plug.setFlags(keyable=info["keyable"])
    if not info["keyable"]:
        plug.setFlags(channelBox=info["channelBox"])
    if info["source"] is not None:
        info["source"].connect(plug)
    for destination in info["destinations"]:
        plug.connect(destination)
    if info["locked"]:
        plug.setFlags(locked=True)
    return plug


class Node(Object):
    """Maya の依存ノード・DAG ノードを表す共通ラッパー。

    生成時は登録済みのノード型に対応するラッパーを選択する。
    ``Node(value)`` の value には名前、MObject、MDagPath に加え、既存の Node
    (同じノードを指す新しいラッパー)、Plug・MPlug(所有ノード)、
    Component・Components(所有シェイプ)も指定できる。名前が存在しない・
    複数の対象に一致する場合や、空・削除済みの対象は RuntimeError になる
    (``"bulk*"`` のように複数のノードに一致するパターンも最初の一致を返さない。
    パターンは ``hlib.ls`` を使う)。所有ノードは有効でアトリビュートだけが ``deleteAttr`` で
    削除された Plug・MPlug は ValueError(``hlib.plugs.plug.DeletedAttributeError``。
    RuntimeError の派生でもあるため、従来どおり RuntimeError としても捕捉できる)。

    インスタンス化されたノードは、指定されたインスタンスの DAG パスを保持する。
    そのインスタンスだけが削除された場合は、パスを使う操作がRuntimeErrorになる。
    別インスタンスへ暗黙に切り替えない。ノード自体の有効性はis_validで照会する。

    ``str(node)`` は maya.cmds で一意に解決できる最短名(:meth:`name`)を返すため、
    Node はそのまま ``cmds.select(node)`` のように maya.cmds へ渡せる。名前は
    呼び出すたびに再計算するため、名前変更・親子付け替えに追従する。
    削除済みのノードは空文字列になる。"""

    @staticmethod
    def _selection_owner(selection, index, name=None):
        """MSelectionList の要素を所有するノードの MObject と DAG パスを返す。

        ノード・コンポーネントの要素は選択されたインスタンスの DAG パスを返す。
        アトリビュート(プラグ)の要素は ``MSelectionList.getDagPath()`` を使えず、選択リスト自体も
        インスタンスの情報を持たないため、インスタンス化された DAG ノードのアトリビュートは
        次の順にノード部分からインスタンスのパスを求める。

        1. name(要素を追加したときの文字列)。``|grpB|box1|boxShape.castsShadows`` は
           ``|grpB|box1|boxShape`` のインスタンスを指す。
        2. 選択文字列。``worldMatrix[1]`` のようなインスタンスごとのアトリビュートは、要素番号の
           インスタンスが選択文字列に現れる。

        ``|box1.castsShadows`` のように transform の名前でシェイプのアトリビュートを指す文字列は、
        ノード部分が指す transform のパスを所有シェイプまで伸ばす(``|box1|boxShape``)。
        どちらからも求められない場合は最初のインスタンスのパスを返す。

        Args:
            selection (om2.MSelectionList): 対象を含む選択リスト。
            index (int): 要素の位置。
            name (str | None): 要素を追加したときの文字列。分かっている場合に指定する。

        Returns:
            tuple[om2.MObject, om2.MDagPath | None]: 所有ノードの MObject と、DAG ノードで
                あれば DAG パス(DG ノードは None)。
        """
        mobject = selection.getDependNode(index)
        if not mobject.hasFn(om2.MFn.kDagNode):
            return mobject, None
        try:
            return mobject, selection.getDagPath(index)
        except (RuntimeError, TypeError):
            pass
        fn = om2.MFnDagNode(mobject)
        if fn.isInstanced():
            candidates = [name] if name else []
            candidates.extend(selection.getSelectionStrings(index))
            for text in candidates:
                # ノード名には "." を含められないため、最初の "." までがノード部分になる。
                owner = om2.MSelectionList()
                try:
                    owner.add(text.split(".", 1)[0])
                    dagPath = owner.getDagPath(0)
                except (RuntimeError, TypeError):
                    continue
                if dagPath.node() == mobject:
                    return mobject, dagPath
                # transform の名前でシェイプのアトリビュートを指す場合は、名前が指す transform の
                # インスタンスの下にある所有シェイプまでパスを伸ばす。
                for child in range(dagPath.childCount()):
                    if dagPath.child(child) == mobject:
                        dagPath.push(mobject)
                        return mobject, dagPath
        return mobject, fn.getPath()

    @staticmethod
    def _unique_node_name(mobject):
        """ノードの MObject から maya.cmds で一意に解決できる最短名を返す。

        DAG ノードは最初のインスタンスの最短一意パス(``MDagPath.partialPathName()``)、
        DG ノードはノード名を返す。``Node.name()`` と同じ規則。

        Args:
            mobject (om2.MObject): 依存ノードの MObject。

        Returns:
            str: 最短一意名。
        """
        if mobject.hasFn(om2.MFn.kDagNode):
            return om2.MFnDagNode(mobject).getPath().partialPathName()
        return om2.MFnDependencyNode(mobject).name()

    @staticmethod
    def _mobject_name(mobject):
        """依存ノードの MObject を完全 DAG パスまたは DG ノード名へ変換する。

        Args:
            mobject (om2.MObject): 変換対象。

        Returns:
            str: 完全 DAG パス(最初のインスタンス)、または DG ノード名。

        Raises:
            ValueError: 空、または削除済みノードの MObject の場合。
            TypeError: アトリビュート・コンポーネント・データなど依存ノード以外を指す場合。
        """
        if mobject.isNull():
            raise ValueError("空の MObject は指定できません")
        if not om2.MObjectHandle(mobject).isValid():
            raise ValueError("削除済みノードの MObject は指定できません")
        if not mobject.hasFn(om2.MFn.kDependencyNode):
            raise TypeError("MObject には依存ノードを指定してください(アトリビュート・コンポーネント・データは不可)")
        if mobject.hasFn(om2.MFn.kDagNode):
            return om2.MFnDagNode(mobject).getPath().fullPathName()
        return om2.MFnDependencyNode(mobject).name()

    @staticmethod
    def _resolve_input(value):
        """対象を Node インスタンスへ変換する。

        Plug・MPlug は所有ノード、Component・Components は所有シェイプへ解決する。

        Args:
            value (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                変換対象。

        Returns:
            Node: value が Node ならそのまま、Plug なら ``plug.node``、コンポーネントなら
                ``shape``。それ以外は ``Node(value)`` (Maya へ解決し、型に応じたラッパーを返す)。
                削除済みの Node と、所有ノードが削除済みの Plug・Component は例外にせずそのまま
                返す(``Node.isValid()`` が ``False``。扱いは呼び出し側で決める)。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (:class:`DeletedAttributeError`。``RuntimeError`` の派生でもある)。
            RuntimeError: 名前を解決できない(存在しない、または複数のノードに一致する)場合、
                または空・削除済みのノードを指す om2 オブジェクトの場合(``Node(value)`` と同じ)。
        """
        from hlib.object import Object as _InputObject
        from hlib.plugs.plug import Plug as _InputPlug
        node_class, plug_class, component_class, components_class = _InputObject._classes()
        if isinstance(value, node_class):
            return value
        if isinstance(value, plug_class):
            error = _InputPlug._deleted_attribute_error(value)
            if error is not None:
                raise error
            return value.node
        if isinstance(value, (component_class, components_class)):
            return value.shape
        if isinstance(value, (str, om2.MObject, om2.MDagPath, om2.MPlug)):
            return node_class(value)
        raise _InputObject._unsupported(value)

    @staticmethod
    def _input_name(value):
        """ノードが必要な単一の引数(``parent`` など)を、所有ノードの完全パスへ変換する。

        Node._resolve_input と同じ規則で解決する(Plug・MPlug は所有ノード、Component は所有シェイプ)。
        ``"node.attribute"`` 形式の文字列も所有ノードになるため、maya.cmds のように
        プラグ名の ``parent`` が黙って無視されることはない。

        Args:
            value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug): 変換対象。

        Returns:
            str: 所有ノードの完全 DAG パス(DG ノードはノード名)。

        Raises:
            TypeError: 対応しない型、または Components などの複数の対象を渡した場合。
            ValueError: 空文字列、または無効な(削除済みの。アトリビュートだけが削除された Plug・MPlug を
                含む)対象の場合。
            RuntimeError: 文字列を解決できない(存在しない、または複数のノードに一致する)場合。
        """
        from hlib.object import Object as _InputObject
        # 型と有効性の検査は Object._input_name と同じ規則(TypeError / ValueError)にそろえる。
        _InputObject._input_name(value)
        return Node._resolve_input(value).fullName()


    _registry = None  #: hlib.__init__ が構築後に注入する NodeRegistry。
    _fn_cache = None  #: _dependency_fn() が初回に作る MFnDependencyNode(ノードごとに1つ)。

    def shadingEngines(self):
        """自身から直接接続されているShadingEngineを重複なしで返す。

        Returns:
            list[ShadingEngine]: 直接接続先。テクスチャから履歴を辿る操作ではない。
        """
        from .shadingEngine import ShadingEngine
        names = cmds.listConnections(self.fullName(), source=False, destination=True,
                                     type="shadingEngine") or []
        return list(dict.fromkeys(ShadingEngine(name) for name in names))

    def assignedObjects(self):
        """接続先ShadingEngineのメンバーを重複なしで取得する。

        Returns:
            list[Node | Face]: 割り当て先オブジェクトまたはフェース。
        """
        result = []
        for group in self.shadingEngines():
            for member in group.members():
                if member not in result:
                    result.append(member)
        return result

    def materials(self):
        """接続/割り当て先のサーフェスマテリアルを取得する。

        Returns:
            list[Node]: 重複なしのマテリアル。未接続のShadingEngineは除く。
        """
        result = []
        for group in self.shadingEngines():
            material = group.getShader()
            if material is not None and material not in result:
                result.append(material)
        return result

    @classmethod
    @undo_chunk("hlib.nodes.node.create")
    def create(cls, type, **kwargs):
        """ノードを作成し、対応する hlib wrapper として返す。

        Args:
            type (str): Maya の nodeType 名。
            **kwargs: ``maya.cmds.createNode`` に渡すキーワード引数。``parent``/``p`` は
                Node・Plug・Component・MObject・MDagPath・MPlug も受け付ける。

        Returns:
            Node: 作成したノードに対応する wrapper。

        Raises:
            ValueError: type が空文字列または文字列以外の場合、または parent が
                削除済みの対象の場合。
            TypeError: parent が対応しない型の場合。
            RuntimeError: parent の名前を解決できない場合、または Maya が作成を拒否した場合。

        ``parent`` はノードが必要な引数として ``hlib.nodes.Node._input_name`` で
        所有ノードの完全パスへ変換する。Plug・MPlug・``"node.attribute"`` は所有ノード、
        Component は所有シェイプを親にする(シェイプを親にした場合の配置は
        ``maya.cmds.createNode`` と同じ)。
        """

        if not isinstance(type, str) or not type:
            raise ValueError("type must be a non-empty string")
        from hlib.environment import Plugin
        Plugin.ensure_node_plugin(type)
        for key in ("parent", "p"):
            if kwargs.get(key) is not None:
                kwargs[key] = Node._input_name(kwargs[key])
        created_name = cmds.createNode(type, **kwargs)
        return cls(created_name)

    def __new__(cls, node, *args, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        入力を一度だけ解決する。Nodeは登録済みの型を自動選択する。
        具体的なクラスを指定した場合は、そのクラスの派生型以外を拒否する。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。
            *args (object): 選んだクラスの ``__init__`` へ渡す位置引数。
            **kwargs (object): 選んだクラスの ``__init__`` へ渡すキーワード引数。

        Returns:
            Node: 登録済みの適合クラスのインスタンス。

        Raises:
            TypeError: ノード入力が対応しない型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノードを解決できない場合。
        """
        registry = cls._registry
        if registry is None:
            return super().__new__(cls)
        # 入力の解決(名前の検索など)は1回だけ行い、結果を __init__ へ引き継ぐ。
        resolved = _resolve_node(node)
        resolved_class = registry.wrapper_class(om2.MFnDependencyNode(resolved[0]).typeName)
        if cls is not Node and not issubclass(resolved_class, cls):
            raise TypeError("{} requires a compatible node, got {}".format(cls.__name__, resolved_class.__name__))
        instance = super().__new__(resolved_class)
        instance._pending_resolution = resolved
        return instance

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        既存の Node を渡した場合は、同じ MObject と DAG パス(インスタンス)を
        指す新しいラッパーになる。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノード名を解決できない場合。
        """
        # __new__ が解決済みの結果を引き継いだ場合は、同じ入力を再び解決しない。
        resolved = self.__dict__.pop("_pending_resolution", None)
        if resolved is None:
            self._mobject = None
            self._dag_path = None
            self._handle = None
            self._resolve(node)
            return
        self._mobject, self._dag_path = resolved
        # 有効性の判定は名前の取得のたびに行うため、ハンドルは一度だけ作って再利用する。
        self._handle = om2.MObjectHandle(self._mobject)
        self._identity_hash = self._handle.hashCode()

    def _resolve(self, node):
        """ノードを表す入力を内部 API オブジェクトへ変換する。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードを表す入力(_resolve_node と同じ)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject, self._dag_path = _resolve_node(node)
        # 有効性の判定は名前の取得のたびに行うため、ハンドルは一度だけ作って再利用する。
        self._handle = om2.MObjectHandle(self._mobject)
        self._identity_hash = self._handle.hashCode()
        self._fn_cache = None

    def _dependency_fn(self):
        """保持するノードの MFnDependencyNode を返す(作成は初回の1回だけ)。

        名前・アトリビュートの問い合わせのたびに関数セットを作り直さないためのキャッシュ。
        ノードが有効(:meth:`isValid`)であることを呼び出し側で確かめてから使う。

        Returns:
            om2.MFnDependencyNode: このノードの関数セット。
        """
        fn = self._fn_cache
        if fn is None:
            fn = self._fn_cache = om2.MFnDependencyNode(self._mobject)
        return fn

    def _current_dag_path(self):
        """保持パスを返す。消失したインスタンスを別パスへ切り替えない。

        Returns:
            om2.MDagPath | None: 保持しているパス。非DAGはNone。
        Raises:
            RuntimeError: 保持しているDAGインスタンスが削除された場合。
        """
        dagPath = self._dag_path
        if dagPath is not None and not dagPath.isValid():
            raise RuntimeError("The referenced DAG instance no longer exists")
        return dagPath

    def __hash__(self):
        """生成時のMayaハンドルのハッシュを返す。改名・削除後も変化しない。"""
        return self._identity_hash

    def __eq__(self, other):
        """生存中の同じ対象を比較する。DAGはインスタンスのパスも区別する。"""
        if not isinstance(other, Node):
            return NotImplemented
        if not self.isAlive() or not other.isAlive():
            return False
        if self._dag_path is not None and other._dag_path is not None:
            return self._dag_path == other._dag_path
        return self._mobject == other._mobject

    def sameNode(self, other):
        """別インスタンスも含め、同じ生存中のMayaノードを指すか返す。"""
        return (isinstance(other, Node) and self.isAlive() and other.isAlive()
                and self._mobject == other._mobject)

    def sameInstance(self, other):
        """同じ生存中のDAGインスタンスか返す。非DAGノードはFalse。"""
        return (isinstance(other, Node) and self._dag_path is not None
                and other._dag_path is not None and self == other)

    def isValid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        handle = self._handle
        return handle is not None and handle.isValid()

    def isAlive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        handle = self._handle
        return handle is not None and handle.isAlive()

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

    def typeId(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。
        """
        return om2.MFnDependencyNode(self._mobject).typeId.id()

    def pluginName(self):
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

    def isType(self, node_type):
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``isType("shape")`` で True になる。

        Args:
            node_type (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに node_type が含まれる場合は True。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not self.isValid():
            return False
        return node_type in (cmds.nodeType(self.fullName(), inherited=True) or [])

    def isLocked(self):
        """ノード自体がロックされているか判定する。

        アトリビュート単位のロックは Plug.isLocked() を参照する。

        Returns:
            bool: ロックされている場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isLocked

    def isReferenced(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isFromReferencedFile

    def isAncestorOf(self, other):
        """other が自身の DAG 階層上の子孫か判定する。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身より下の階層にある場合は True。自身自身や
                非DAGノード、無効なノード、削除済みの対象(アトリビュートが削除済みの Plug・MPlug、
                削除済みのノードを指す om2 オブジェクトを含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.fullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.fullName()
        return other_full != self_full and other_full.startswith(self_full + "|")

    def isParentOf(self, other):
        """other が自身の直接の子か判定する（孫以下は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の子の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.fullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.fullName()
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    def isChildOf(self, other):
        """other が自身の直接の親か判定する（祖父母以上は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の親の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        if other_node is None:
            return False
        return other_node.isParentOf(self)

    def attributeCount(self):
        """ノードが持つアトリビュートの総数を取得する。

        Returns:
            int: アトリビュート数。
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
        dagPath = self._current_dag_path()
        if dagPath is None:
            raise RuntimeError("DAG ノードではありません")
        if full:
            return dagPath.fullPathName()
        return dagPath.partialPathName()

    def isRoot(self):
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        dagPath = self._current_dag_path()
        if dagPath is None:
            raise RuntimeError("DAG ノードではありません")
        return dagPath.length() == 1

    def nodeName(self, remove_namespace=False):
        """DAG パスを除いたノード名を返す。

        Args:
            remove_namespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``remove_namespace`` が ``True`` の場合は
                namespaceを含まないノード名。
        """
        nodeName = om2.MFnDependencyNode(self._mobject).name()
        if remove_namespace:
            nodeName = nodeName.rsplit(":", 1)[-1]
        return nodeName

    def namespace(self):
        """ノードが属するネームスペースを返す。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        # namespaces.namespace が ..nodes を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from hlib.scene import Namespace

        nodeName = self.nodeName()
        if ":" not in nodeName:
            return Namespace(":")
        return Namespace(nodeName.rsplit(":", 1)[0])

    @undo_chunk("hlibNodeDelete")
    def delete(self):
        """自身をMaya標準の規則で削除する。

        DAGの子も削除し、一回のUndoで戻せる。
        派生クラスはこのメソッドを上書きして専用の削除処理を実装できる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 対象が無効、またはMayaが削除を拒否した場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot delete an invalid node")
        cmds.delete(self.fullName())

    @undo_chunk("hlibNodeRename")
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

    @undo_chunk("hlibNodeSetNamespace")
    def setNamespace(self, namespace):
        """ノードを指定したネームスペースへ移動する。

        Args:
            namespace (str | Namespace): 移動先のnamespace名。末尾の ``":"`` は任意。

        Returns:
            str: Mayaが確定したnamespace付きノード名。

        Raises:
            ValueError: namespaceが空文字列または文字列でない場合。
            RuntimeError: namespace移動に失敗した場合。
        """
        # namespaces.namespace ⇔ nodes の相互依存を避けるための遅延 import。namespace() と同じ理由。
        from hlib.scene import Namespace

        if isinstance(namespace, Namespace):
            target_namespace = namespace
        elif isinstance(namespace, str) and namespace:
            target_namespace = Namespace(namespace)
        else:
            raise ValueError("namespace must be a non-empty string")
        if not target_namespace.exists() and target_namespace.name != ":":
            target_namespace = Namespace.create(target_namespace)
        namespace_name = target_namespace.name
        nodeName = self.nodeName(True)
        new_name = (
            f"{namespace_name}:{nodeName}"
            if namespace_name != ":"
            else nodeName
        )
        return cmds.rename(self.name(), new_name)

    def _connected_plugs(self, as_source, as_destination, type=None):
        """ノードの指定方向に接続された外部Plugを収集する。

        Args:
            as_source (bool): 接続元Plugを検索対象に含めるかどうか。
            as_destination (bool): 接続先Plugを検索対象に含めるかどうか。
            type (str | None): 指定した場合、接続先ノードの nodeType が
                ``isType`` で一致するものだけに絞り込む(継承チェーンも判定)。

        Returns:
            list[Plug]: 接続先の外部Plugを重複なしで格納したリスト。
        """
        from hlib.plugs.plug import Plug as _InputPlug
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..plugs.plug import Plug

        plugs = []
        seen = set()
        for mplug in om2.MFnDependencyNode(self._mobject).getConnections():
            for connected in mplug.connectedTo(as_source, as_destination):
                # MPlug.name() は短いノード名しか含まず、同名ノード(grp1|dup と grp2|dup)の
                # プラグを同一視してしまうため、所有ノードの一意な名前とアトリビュートパスで重複を判定する
                # (MObjectHandle.hashCode() は別ノードで衝突しうるため使わない)。
                key = (Node._unique_node_name(connected.node()), _InputPlug._plug_path(connected))
                if key in seen:
                    continue
                node = Node(connected.node())
                if type is not None and not node.isType(type):
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
            list[Plug]: 入力元の外部プラグ。同じノードの同じアトリビュートは1件にまとめる。接続がなければ空リスト。
        """
        return self._connected_plugs(True, False, type=type)

    def outputs(self, type=None):
        """このノードから出力する接続先Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 出力先の外部プラグ。同じノードの同じアトリビュートは1件にまとめる。接続がなければ空リスト。
        """
        return self._connected_plugs(False, True, type=type)

    def connections(self, type=None):
        """このノードに接続された外部Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 入力元と出力先の外部プラグ。一意なプラグ名(``fullName()``)で
                重複を除外する。接続がなければ空リスト。
        """
        plugs = []
        seen = set()
        for plug in self.inputs(type=type) + self.outputs(type=type):
            if plug.fullName() in seen:
                continue
            seen.add(plug.fullName())
            plugs.append(plug)
        return plugs

    def history(self, type=None, future=False):
        """構築履歴を検索し、対応するノードラッパーを返す。

        Args:
            type (str | None): 継承型を含むノード型フィルター。Noneは全型。
            future (bool): Trueは下流、Falseは上流を検索する。

        Returns:
            list[Node]: Mayaの履歴順。自身と重複を除く。該当なしなら空リスト。

        Raises:
            RuntimeError: 無効なノード、またはMayaの履歴検索が失敗した場合。
        """
        names = cmds.listHistory(self.fullName(), future=future) or []
        result, seen = [], {self.uuid()}
        for name in names:
            node = Node(name)
            if node.uuid() in seen:
                continue
            seen.add(node.uuid())
            if type is None or node.isType(type):
                result.append(node)
        return result

    @undo_chunk("hlibNodeResetAttrs")
    def resetAttributes(self, attributes=None):
        """指定アトリビュート、または書き込み可能なキー設定対象アトリビュートを既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): アトリビュート名。Noneはキー設定可能な
                数値・単位・enumアトリビュートを対象とし、ロック・入力接続・非対応型は除外する。
                明示指定したアトリビュートのエラーは除外せず送出する。

        Returns:
            list[Plug]: リセットしたアトリビュート。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 明示指定したアトリビュートがリセット非対応の場合。
            RuntimeError: 明示指定したアトリビュートがロック・接続済みなどで書き込みできない場合。
        """
        if attributes is None:
            plugs = [plug for plug in self.plugs(keyable=True, scalar=True)
                     if plug.default() is not None and not plug.isDestination()
                     and cmds.getAttr(plug.fullName(), settable=True)]
        else:
            if isinstance(attributes, str):
                attributes = [attributes]
            plugs = [self.plug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return plugs

    @fast_edit
    @undo_chunk("hlibNodeSetAttrFlags")
    def setAttributeFlags(self, attributes, locked=None, keyable=None, channelBox=None, *, fast=False):
        """指定したアトリビュートのロック・キー設定可否・Channel Box表示をまとめて変更する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            attributes (str | Iterable[str]): アトリビュート名。選択状態やChannel Box選択は使用しない。
                複合アトリビュートの子まで変更する場合は子アトリビュート名を明示する。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channelBox (bool | None): Channel Box表示。Noneは変更しない。
                keyable=TrueのアトリビュートはMayaの仕様により表示される。

        Returns:
            Node: 自身。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。全アトリビュートを変更前に解決する。
            TypeError: 状態にboolまたはNone以外を指定した場合。
            RuntimeError: Mayaが変更を拒否した場合。途中の変更は自動では戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        from ..plugs.plug import Plug
        flags = Plug._validated_flags(locked, keyable, channelBox)
        if isinstance(attributes, str):
            attributes = [attributes]
        plugs = [self.plug(name) for name in attributes]
        if flags:
            for plug in plugs:
                plug.setFlags(locked=locked, keyable=keyable, channelBox=channelBox)
        return self

    def plugs(self, **kwargs):
        """ノードのアトリビュートを Plug のリストとして列挙する。

        Args:
            kwargs: ``cmds.listAttr`` にそのまま渡す追加フラグ
                (``keyable=True``、``visible=True``、``write=True`` など)。

        Returns:
            list[Plug]: 該当するアトリビュートの Plug。``cmds.listAttr`` が返す名前のうち
                実際には評価できないもの（未確保の要素を持つ配列複合アトリビュートの子など）は
                黙ってスキップする。該当なしの場合は空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        names = cmds.listAttr(self.fullName(), **kwargs) or []
        plugs = []
        for name in names:
            try:
                plugs.append(self.plug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
        return plugs

    def aliases(self):
        """このノードのアトリビュートエイリアスを取得する。

        Returns:
            list[tuple[str, Plug]]: ``(エイリアス名, 対応するPlug)`` のリスト。
                エイリアスが無ければ空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("無効なノードのエイリアスは取得できません")
        # 配列・複合パスの解決はplug()へ集約し、Mayaコマンドと名前再解決を避ける。
        return [(alias, self.plug(name)) for alias, name in self._dependency_fn().getAliasList()]

    @undo_chunk("hlibNodeAddAttr")
    def addAttribute(
        self,
        longName,
        attributeType=None,
        dataType=None,
        defaultValue=None,
        **kwargs,
    ):
        """アトリビュートを追加し、追加したPlugを返す。

        attributeTypeがdouble2/double3/float2/float3ならXYZの子も自動作成する。
        任意構成のcompoundはMaya標準addAttrで子まで定義してからplugで取得する。

        Args:
            longName (str): 追加するアトリビュートのロング名。
            attributeType (str | None): addAttr の attributeType。dataType と少なくとも一方が必要。
            dataType (str | None): addAttr の dataType。
            defaultValue (object | None): 初期値。単位型はcm/rad/秒またはAPIの単位型。
                Noneなら指定しない。timeのdefaultValueはMayaのaddAttrの制限に従う。
            **kwargs (object): addAttrへ渡す長名・短名フラグ。重複指定は拒否する。
                minValue/maxValue/softMinValue/softMaxValueも内部単位で受け取る。

        Returns:
            Plug: 追加したアトリビュートの型に対応するプラグ。

        Raises:
            ValueError: longName が空または文字列以外、あるいはアトリビュート型の指定がない場合。
            RuntimeError: Maya がアトリビュート追加を拒否した場合。
        """
        if not isinstance(longName, str) or not longName:
            raise ValueError("longName must be a non-empty string")
        from .._core.flags import normalize_flags
        add_kwargs = normalize_flags("addAttr", kwargs)
        if add_kwargs.get("query") or add_kwargs.get("edit"):
            raise ValueError("addAttr supports creation only")
        if "longName" in add_kwargs:
            raise TypeError("longName and ln cannot be specified together")
        add_kwargs["longName"] = longName
        if attributeType is not None:
            if "attributeType" in add_kwargs:
                raise TypeError("Specify attributeType or at, not both")
            add_kwargs["attributeType"] = attributeType
        if dataType is not None:
            if "dataType" in add_kwargs:
                raise TypeError("Specify dataType or dt, not both")
            add_kwargs["dataType"] = dataType
        if defaultValue is not None:
            if "defaultValue" in add_kwargs:
                raise TypeError("Specify defaultValue or dv, not both")
            add_kwargs["defaultValue"] = defaultValue
        if not (add_kwargs.get("attributeType") or add_kwargs.get("dataType")):
            raise ValueError("attributeType or dataType is required")
        unit_type = {
            "doubleAngle": (om2.MAngle, om2.MAngle.kRadians),
            "doubleLinear": (om2.MDistance, om2.MDistance.kCentimeters),
            "time": (om2.MTime, om2.MTime.kSeconds),
        }.get(add_kwargs.get("attributeType"))
        if unit_type:
            cls, internal = unit_type
            for flag in ("defaultValue", "minValue", "maxValue", "softMinValue", "softMaxValue"):
                if flag in add_kwargs:
                    value = add_kwargs[flag]
                    quantity = value if isinstance(value, cls) else cls(value, internal)
                    add_kwargs[flag] = quantity.asUnits(cls.uiUnit() if cls is om2.MTime else internal)
        vector_type = add_kwargs.get("attributeType")
        if vector_type in ("double2", "double3", "float2", "float3"):
            # Mayaは子が揃うまで複合Plugを公開しないため、XYZの子も同時に作る。
            if "numberOfChildren" in add_kwargs:
                raise ValueError("Vector child count is determined by attributeType")
            cmds.addAttr(self.fullName(), **add_kwargs)
            for axis in "XYZ"[:int(vector_type[-1])]:
                cmds.addAttr(self.fullName(), longName=longName + axis,
                             attributeType=vector_type[:-1], parent=longName,
                             keyable=bool(add_kwargs.get("keyable", False)))
            return self.plug(longName)
        return self._add_attribute(self, **add_kwargs)

    @staticmethod
    def _add_attribute(target, **kwargs):
        """Maya形式のフラグで追加し、Plugを返す共通実装。

        Args:
            target (str | Node | Plug): 操作対象。
            **kwargs (object): 正規化済みのMaya長名フラグ。
        Returns:
            Plug: 追加した参照。
        Raises:
            ValueError: 照会・編集、または名前の指定が不正な場合。
            RuntimeError: Mayaが追加を拒否した場合。
        """
        from hlib.object import Object as _InputObject
        from hlib.plugs.plug import Plug as _InputPlug

        if kwargs.get("query") or kwargs.get("edit"):
            raise ValueError("addAttr supports creation only")
        name = _InputObject._input_name(target)
        if (
            not kwargs.get("query")
            and "." not in name
            and not (kwargs.get("longName") or kwargs.get("shortName"))
        ):
            raise ValueError("Specify longName or shortName")
        cmds.addAttr(name, **kwargs)
        if "." in name:
            return _InputPlug._resolve_input(name)
        attribute = kwargs.get("longName") or kwargs.get("shortName")
        if not attribute:
            raise ValueError("Specify longName or shortName")
        return Node._resolve_input(target).plug(attribute)

    def getExtraAttributes(self, include_children=False):
        """ユーザー追加のエクストラアトリビュートを型付きPlugで取得する。

        Args:
            include_children (bool): Trueは複合アトリビュートの子も含める。

        Returns:
            list[Plug]: Mayaの列挙順のプラグ。配列はArrayPlugとして返す。
                非表示・非keyableも含む。個別取得はplug("名前")を使用する。

        Raises:
            TypeError: include_childrenがboolでない場合。
            RuntimeError: ノードが無効な場合。またはinclude_children=Trueで、
                番号を指定しない複合配列の子が含まれる場合。
        """
        if not isinstance(include_children, bool):
            raise TypeError("include_children must be a bool")
        if not self.isValid():
            raise RuntimeError("Cannot list attributes on an invalid node")
        # 名前へ変換して再検索せず、定義から型付きPlugを作る。配列の要素は展開しない。
        from ..plugs.plug import Plug
        return [Plug(self, om2.MPlug(self._mobject, attribute))
                for attribute in self._user_attributes(include_children)]

    def _user_attributes(self, include_children=False):
        """動的アトリビュートの定義を追加順に列挙する。

        Args:
            include_children (bool): Trueなら複合型の子の定義も含める。

        Yields:
            om2.MObject: アトリビュート定義。配列要素の取得・作成は行わない。
        """
        fn = self._dependency_fn()
        for index in range(fn.attributeCount()):
            attribute = fn.attribute(index)
            definition = om2.MFnAttribute(attribute)
            if definition.dynamic and (include_children or definition.parent.isNull()):
                yield attribute

    def userAttributeNames(self):
        """トップレベルのユーザー定義アトリビュート名を現在の並び順で取得する。

        複合アトリビュートの子は含まない。

        Returns:
            list[str]: ロング名のリスト。並び順はMayaへの追加順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        return [om2.MFnAttribute(attribute).name for attribute in self._user_attributes()]

    @undo_chunk("hlibNodeMoveAttribute")
    def moveAttributeOrder(self, name, offset):
        """ユーザー定義アトリビュートを Channel Box 上で前後に移動する。

        Maya にはアトリビュートの並び替え API が無いため、移動元と移動先のうち手前側の
        位置から末尾までのアトリビュートをまとめて削除し、新しい順序で再作成すること
        で実現する(移動先より後ろにある、移動と無関係なアトリビュートも再作成対象に
        含まれる。数値・enum・文字列型の非複合・非配列トップレベル動的アトリビュート
        のみ対応。対応しないアトリビュートが再作成対象に含まれる場合は何も変更せず
        例外を送出する)。

        Args:
            name (str): 移動するユーザー定義アトリビュートのロング名。
            offset (int): 正の値で末尾方向、負の値で先頭方向へ移動する位置数。
                範囲を超える指定は先頭・末尾で止まる。

        Returns:
            Node: 自身。全変更を一回の Undo にまとめる。

        Raises:
            ValueError: name がトップレベルのユーザー定義アトリビュート一覧に無い場合。
            TypeError: 移動範囲に複合・配列アトリビュート、または対応しないアトリビュート型が
                含まれる場合。
            RuntimeError: ノードが無効な場合。
        """
        names = self.userAttributeNames()
        if name not in names:
            raise ValueError(f"{name} is not a top-level user-defined attribute of {self.fullName()}")
        old_index = names.index(name)
        new_index = max(0, min(len(names) - 1, old_index + offset))
        if new_index == old_index:
            return self
        names.remove(name)
        names.insert(new_index, name)
        window_start = min(old_index, new_index)
        to_recreate = names[window_start:]

        infos = [_dump_movable_attr(self.plug(attr_name)) for attr_name in to_recreate]
        for attr_name in to_recreate:
            self.plug(attr_name).deleteAttribute(force=True)
        for info in infos:
            _create_movable_attr(self, info)
        return self

    def plug(self, name):
        """アトリビュートを扱う Plug オブジェクトを取得する。

        ノードのアトリビュート操作には、このメソッドを使用します。
        返された Plug で値の取得・設定や、ほかのプラグとの接続を行えます。

        アトリビュート名(ロング名・ショート名・エイリアス)に加え、配列要素と子アトリビュートを含むアトリビュートパス
        (``input1D[3]``、``worldMatrix[0]``、``pnts[2].pntx``、
        ``inputTarget[0].inputTargetGroup[7].inputTargetItem[6000].inputComponentsTarget``)を
        指定できる。形式は ``str(plug)`` のアトリビュート部分(``Plug.fullName()`` の ``.`` 以降)と同じ。
        配列インデックスは 0〜2147483647(``MPlug.logicalIndex()`` の範囲)で指定する。
        存在しない配列要素の Plug を取得しても要素は作られない(値によって型が変わるアトリビュートの
        評価を除き、シーンを変更しない。:doc:`/cmds_interop` を参照)。

        Args:
            name (str): アトリビュート名またはアトリビュートパス(このノード自身のアトリビュートに限る)。

        Returns:
            Plug: 解決したアトリビュートプラグ。

        Raises:
            ValueError: 空文字列または文字列以外を指定した場合。
            RuntimeError: ノードが無効な場合。アトリビュート名が配列複合アトリビュートの子を配列要素の番号なしで
                指す場合(``input3Dx`` のような maya.cmds で解決できないプラグ。
                ``input3D[0].input3Dx`` のように番号を含めて指定する)。
            AttributeError: アトリビュート・アトリビュートパスを解決できない場合。配列インデックスが
                2147483647 を超える場合(``input1D[4294967296]`` のような番号を別の要素へ
                読み替えない)も含む。
        """
        from hlib.plugs.plug import Plug as _InputPlug
        from hlib.plugs.plug import MAX_LOGICAL_INDEX
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でないアトリビュートパスを指定してください")
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        # plugs.plug ⇔ nodes の相互依存を避けるための遅延 import。inputs()/outputs() と同じ理由。
        from ..plugs.plug import Plug

        if "[" not in name:
            # 配列インデックスを含まない名前(``boundingBox.boundingBoxMin`` のような子アトリビュートの
            # パスを含む)は、従来どおり findPlug で解決する。
            try:
                mplug = self._dependency_fn().findPlug(name, False)
            except RuntimeError:
                mplug = None  # エイリアス名は findPlug で解決できないため、下で解決する。
            if mplug is not None:
                return Plug(self, mplug)

        mplug = _InputPlug._attribute_path_plug(self._mobject, name)
        if mplug is None:
            if _InputPlug._has_out_of_range_index(name):
                raise AttributeError(
                    f"配列インデックスは 0〜{MAX_LOGICAL_INDEX} で指定してください: {self.name()}.{name}"
                )
            raise AttributeError(f"アトリビュートが見つかりません: {self.name()}.{name}")
        return Plug(self, mplug)

    def hasAttribute(self, name):
        """アトリビュートパスを解決できるか判定する。

        Args:
            name (str): アトリビュート名またはアトリビュートパス。

        Returns:
            bool: アトリビュートを解決できる場合は ``True``。
        """
        try:
            self.plug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

    def uuid(self):
        """ノードの Maya UUID を返す。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        if not self.isValid():
            return None
        return om2.MFnDependencyNode(self._mobject).uuid().asString()

    def name(self):
        """Maya の最短一意ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dagPath = self._dag_path
        if dagPath is None:
            return self._dependency_fn().name()
        if not dagPath.isValid():
            dagPath = self._current_dag_path()
        return dagPath.partialPathName()

    def fullName(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dagPath = self._dag_path
        if dagPath is None:
            return self._dependency_fn().name()
        if not dagPath.isValid():
            dagPath = self._current_dag_path()
        return dagPath.fullPathName()

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。

        maya.cmds は文字列以外の引数に ``str()`` を適用するため、Node をそのまま
        ``cmds.select(node)`` のように渡せる。呼び出すたびに再計算するため、
        名前変更・親子付け替えに追従する。

        Returns:
            str: 最短一意名。無効なノードでは空文字列。
        """
        return self.name()

    def __repr__(self):
        """デバッグ用にクラス名とノード名を含む表現を返す。

        Returns:
            str: 有効なら型名とノード名、無効なら型名と invalid を含む文字列。
        """
        if self.isValid():
            return f"{type(self).__name__}({self.name()!r})"
        return f"<{type(self).__name__} invalid>"

    def __getattr__(self, name) -> Any:
        """通常アトリビュートにない名前を Maya Plug として動的に解決する。

        静的解析では、具象クラス(BlendShape 等)のメソッドを基底の Node 型で呼んだ場合に
        Plug 型と誤判定しないよう、戻り値の注釈は Any としている。

        Args:
            name (str): 取得しようとした Python アトリビュート名。

        Returns:
            Plug: 解決した Maya アトリビュートプラグ。

        Raises:
            AttributeError: 非公開名または存在しない Maya アトリビュートを指定した場合。
                :meth:`plug` が RuntimeError にする名前(``input3Dx`` のような、配列要素の
                番号を含まない配列複合アトリビュートの子)も、``hasattr``/``getattr(node, name, default)``
                が使えるよう AttributeError にする(原因の RuntimeError を ``__cause__`` に持つ)。
            RuntimeError: ノードが無効な場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        try:
            return self.plug(name)
        except (AttributeError, RuntimeError) as error:
            raise AttributeError(f"アトリビュートが見つかりません: {self.name()}.{name}") from error




@collection_export()
@bulk_api(
    Node,
    reads=(
        'shadingEngines',
        'assignedObjects',
        'materials',
        'sameNode',
        'sameInstance',
        'isValid',
        'isAlive',
        'mobject',
        'type',
        'typeId',
        'pluginName',
        'classification',
        'isType',
        'isLocked',
        'isReferenced',
        'isAncestorOf',
        'isParentOf',
        'isChildOf',
        'attributeCount',
        'path',
        'isRoot',
        'nodeName',
        'namespace',
        'rename',
        'inputs',
        'outputs',
        'connections',
        'history',
        'resetAttributes',
        'plugs',
        'aliases',
        'addAttribute',
        'getExtraAttributes',
        'userAttributeNames',
        'plug',
        'hasAttribute',
        'uuid',
        'name',
        'fullName',
    ),
    writes=(
        'delete',
        'setNamespace',
        'setAttributeFlags',
        'moveAttributeOrder',
    ),
)
class Nodes:
    """型を検証し、入力順のノード参照を保持するコレクション。

    同一ノード・同一DAGパスの重複だけを除外する。異なるインスタンスパスは保持する。
    コピーやスライスは参照を共有し、シーンのノードは複製しない。
    """

    @staticmethod
    def _resolve_inputs(values):
        """対象列を一度だけ展開し、名前とNodeの混在を変換前に拒否する。

        Args:
            values (object): 単体、または対象の反復可能列。既存のAPI型も保持する。
        Returns:
            list: 入力順の対象。空列は空のまま返す。
        Raises:
            TypeError: 同じ対象列に文字列とNodeが混在している場合。
        """
        result = Object._flatten_inputs(values)
        Nodes._validate_inputs(result)
        return result

    @staticmethod
    def _validate_inputs(values):
        """展開済み対象列の名前とNodeの混在を拒否する。

        Args:
            values (list): Objectが展開した対象列。値の変換は行わない。
        Raises:
            TypeError: 名前とNodeが混在する場合。
        """
        if any(isinstance(value, str) for value in values) and any(isinstance(value, Node) for value in values):
            raise TypeError("Names and Node objects cannot be mixed in the same target collection")



    item_class = Node

    def __iter__(self):
        """保持順に要素を反復する。

        Returns:
            Iterator: 保持している要素のイテレータ。
        """
        return iter(self._items)

    def __len__(self):
        """int: 保持要素数。"""
        return len(self._items)

    def callEach(self, method, arguments, keyword_arguments=None):
        """各要素へ異なる引数を渡す。メソッド名は単体の公開インスタンスメソッドのみ。

        Args:
            method (str): set_translate等。create・特殊メソッドは不可。
            arguments (Iterable[tuple]): 要素数と同じ数の位置引数タプル。
            keyword_arguments (Iterable[dict] | None): 要素別キーワード引数。省略時は空。
        Returns:
            list | Nodes: 照会・結果を返す操作は保持順のリスト、更新は自身。
                ネストしたリストもそのまま保持する。
        Raises:
            ValueError: メソッド名・件数が不正な場合。
            TypeError: 引数のシグネチャが不正な場合。実行前に全件確認する。
            RuntimeError: 単体の処理が失敗した場合。対象番号を含み、後続は実行しない。

        シーン編集は1回のUndoにまとめる。自動ロールバックはしない。
        ファイルI/OはUndo対象外。
        """
        functions, args, kwargs = self._prepare_calls(method, arguments, keyword_arguments)
        return self._execute_calls(method, functions, args, kwargs)

    def _execute_calls(self, method, functions, args, kwargs):
        """検証済み呼出しを実行し、更新操作では不要な結果配列を作らない。"""
        all_fast = bool(kwargs) and all(flags.get("fast") is True for flags in kwargs)
        context = undo_chunk("hlibBulk_" + method) if self._bulk_undo and not all_fast else contextlib.nullcontext()
        result = [] if self._bulk_returns[method] != "self" else None
        with context:
            for index, (function, row, flags) in enumerate(zip(functions, args, kwargs)):
                try:
                    value = function(*row, **flags)
                    if result is not None:
                        result.append(value)
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.{method} failed at item {index}: {exc}") from exc
        return self if result is None else result

    def _dispatch_shared(self, method, args, kwargs):
        """単体APIの転送先を決める。独自call_eachのoverrideを維持する。"""
        if type(self).callEach is not Nodes.callEach:
            return self.callEach(method, [args] * len(self), [kwargs] * len(self))
        return self._call_shared(method, args, kwargs)

    def _call_shared(self, method, args, kwargs):
        """同じ入力の検証を実関数ごとに共有し、全件検証後に実行する。

        共有はこの呼出し内だけに限定する。派生overrideと個体callableは別に
        検証し、クラス差替え・reload後の古いメソッドを保持しない。
        """
        functions = [getattr(item, method) for item in self._items]
        shared = {}
        signatures = {}
        keywords = []
        for function in functions:
            key = function.__func__ if inspect.ismethod(function) else None
            if key is not None and key in shared:
                flags = shared[key]
            else:
                flags = normalize_flags(function, kwargs)
                self._signature(function, signatures).bind(*args, **flags)
                if key is not None:
                    shared[key] = flags
            keywords.append(flags)
        return self._execute_calls(method, functions, [args] * len(functions), keywords)

    def _prepare_calls(self, method, arguments, keyword_arguments):
        """全要素の引数を実行前に解決・検証する。

        Args:
            method (str): 登録済みの単体メソッド名。
            arguments (Iterable[tuple]): 要素別の位置引数。
            keyword_arguments (Iterable[dict] | None): 要素別のキーワード引数。

        Returns:
            tuple: 呼出先・位置引数・正規化済みキーワード引数の各リスト。

        Raises:
            ValueError: メソッド名または件数が不正な場合。
            TypeError: 引数が各呼出先のシグネチャと一致しない場合。
        """
        if method not in self._bulk_methods:
            raise ValueError(f"Unsupported instance method: {method}")
        args = [tuple(row) for row in arguments]
        kwargs = [{} for _ in self._items] if keyword_arguments is None else [dict(row) for row in keyword_arguments]
        if len(args) != len(self) or len(kwargs) != len(self):
            raise ValueError("Argument count must match collection length")
        functions = [getattr(item, method) for item in self._items]
        kwargs = [normalize_flags(function, flags) for function, flags in zip(functions, kwargs)]
        # この呼出内だけ共有し、reloadやクラスの差替え後に古いsignatureを保持しない。
        signatures = {}
        for function, row, flags in zip(functions, args, kwargs):
            self._signature(function, signatures).bind(*row, **flags)
        return functions, args, kwargs

    @staticmethod
    def _signature(function, signatures):
        """一回の検証内で実メソッドのsignatureだけを共有する。

        Args:
            function (callable): 実際に呼び出すメソッドまたは個体callable。
            signatures (dict): 呼出し内だけで使うキャッシュ。

        Returns:
            inspect.Signature: 束縛済み引数に対応するsignature。
        """
        if not inspect.ismethod(function):
            return inspect.signature(function)
        key = function.__func__
        if key not in signatures:
            signatures[key] = inspect.signature(function)
        return signatures[key]


    def __init__(self, names=()):
        """ノード入力を解決して構築する。検索やシーン変更は行わない。

        Args:
            names (object | Iterable[object]): 名前・Node・API参照等、またはその列。
                単一の名前も受け付ける。解決はNodesの共通入力規則に従う。
        Raises:
            TypeError: 解決結果がitem_classの派生でない場合。
            RuntimeError: 名前を解決できない、または削除済みの対象の場合。
            ValueError: 共通入力解決が不正な参照を検出した場合。
        """
        if isinstance(names, (str, Node)):
            names = [names]
        else:
            try:
                names = iter(names)
            except TypeError:
                names = [names]
        names = Nodes._resolve_inputs(names)
        items, seen = [], set()
        for value in names:
            node = Node._resolve_input(value)
            if not node.isValid():
                raise RuntimeError("Cannot collect an invalid node")
            if not isinstance(node, self.item_class):
                raise TypeError(f"{type(self).__name__} requires {self.item_class.__name__}, got {type(node).__name__}")
            # 構築時だけキーを使用。以後の改名・親変更はNode参照が追跡する。
            key = (node.uuid(), node.fullName())
            if key not in seen:
                seen.add(key)
                items.append(node)
        self._items = items

    def __getitem__(self, index):
        """Node | Nodes: 単体参照または同じ具象型のスライスを返す。

        構築後に削除された参照も保持し、要素数を暗黙に変更しない。
        """
        if not isinstance(index, slice):
            return self._items[index]
        result = self.copy()
        result._items = self._items[index]
        return result

    def copy(self):
        """Nodes: 同じ参照を共有する、同じ具象型の独立した容器を返す。"""
        result = object.__new__(type(self))
        result.__dict__.update(self.__dict__)
        result._items = list(self._items)
        return result

    def names(self):
        """list[str]: 保持順の現在のノード名。"""
        return [node.name() for node in self]

    def __repr__(self):
        """str: 具象コレクション名と保持参照を表示する。"""
        return f"{type(self).__name__}({self._items!r})"

    @undo_chunk("hlibNodesDelete")
    def delete(self):
        """各ノードの専用deleteを呼び、親削除で消えた後続対象はスキップする。

        Returns:
            None: 空なら何もしない。Jointsは専用の階層・ウェイト処理を優先する。
        Raises:
            RuntimeError: 実行前に削除済みの参照がある、または削除失敗。
                途中までの変更は自動で戻さない。全体は一回のUndoで戻せる。
        """
        for index, node in enumerate(self):
            if not node.isValid():
                raise RuntimeError(f"{type(self).__name__}.delete invalid item {index}")
        for index, node in enumerate(self):
            if node.isValid():
                try:
                    node.delete()
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.delete failed at item {index}: {exc}") from exc
