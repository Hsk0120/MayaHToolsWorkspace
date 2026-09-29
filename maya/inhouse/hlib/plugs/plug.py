"""Maya API 2.0 の MPlug を属性ラッパーとして扱う。"""

from ..decorators._fast import fast_edit, is_fast
from .._core.attributeType import attribute_type, is_internal_data_type
from .._core.coerce import has_unresolved_index, to_plug
from .._core.fastWrite import set_attr
from .._core.fastWrite import set_plug

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk


#: cmds.setAttr へ値をそのまま(型名付きで、長さ指定なし)渡せば済むスカラー配列型。
_SCALAR_ARRAY_TYPES = frozenset(("doubleArray", "floatArray", "Int32Array", "Int64Array"))

#: cmds.setAttr へ ``長さ, *値, type=...`` の形で渡す必要がある配列型。
_LENGTH_PREFIXED_ARRAY_TYPES = frozenset((
    "stringArray", "vectorArray", "floatVectorArray", "pointArray", "matrixArray",
    "componentList",
))


def _instance_count(array):
    """ワールド空間属性の配列なら、所有 DAG ノードのインスタンス数を返す。

    ``worldMatrix`` などのワールド空間属性は、インスタンス番号(0～インスタンス数-1)の
    要素を評価前でも存在するものとして扱う(:class:`ArrayPlug` と同じ規則)。

    Args:
        array (om2.MPlug): 配列プラグ。

    Returns:
        int: 間接インスタンスを含むインスタンス数。ワールド空間属性でなければ 0。
    """
    node = array.node()
    if not node.hasFn(om2.MFn.kDagNode) or not om2.MFnAttribute(array.attribute()).worldSpace:
        return 0
    return om2.MFnDagNode(node).instanceCount(True)


#: ``MFnDependencyNode.attributeClass()`` が、ノードに無い属性(削除済みの動的属性など)に返す値。
_INVALID_ATTRIBUTE = om2.MFnDependencyNode.kInvalidAttr

#: ``MFnDependencyNode.attributeClass()`` が、ノード型に組み込みの(静的な)属性に返す値。
_NORMAL_ATTRIBUTE = om2.MFnDependencyNode.kNormalAttr


def _attribute_class(node, attribute_handle, attribute):
    """属性が所有ノードに存在するかと、静的な属性かを判定する。

    ``addAttr`` による動的属性(``addExtension`` による拡張属性を含む)は削除でき、削除済みの
    属性の MPlug で値を読み書きすると Maya が異常終了する。削除は Undo のために属性の
    MObject が保持されたままの場合があり、``MObjectHandle.isValid()`` だけでは判定できない
    ため、所有ノードの ``MFnDependencyNode.attributeClass()`` で確かめる(ノードに無い属性は
    ``kInvalidAttr``)。同じ名前で追加し直した属性は別の属性として扱い、Undo で削除を
    取り消した属性と名前を変更した属性は同じ属性のまま。

    Args:
        node (Node): 所有ノードのラッパー。有効(削除済みでない)であること。
        attribute_handle (om2.MObjectHandle): 属性の MObject のハンドル。
        attribute (om2.MObject): 属性の MObject。

    Returns:
        int: ``MFnDependencyNode`` の ``kNormalAttr``(静的属性)・``kLocalDynamicAttr``・
            ``kExtensionAttr``、またはノードに無い属性の ``kInvalidAttr``。
    """
    if not attribute_handle.isValid():
        return _INVALID_ATTRIBUTE
    return node._dependency_fn().attributeClass(attribute)


#: 値によって型が変わる属性の接続元を辿る最大の段数(循環する接続の保護)。
_MAX_SOURCE_DEPTH = 16


def _held_matrix_type(mplug, depth=0):
    """値によって型が変わる属性が行列を保持していれば ``"matrix"`` を返す。

    対象は generic 属性(``unitConversion.input`` など)と、任意のデータを受け付ける
    型付き属性(``MFnData.kAny``。``choice`` の ``input``/``output`` など)。
    ``cmds.getAttr(type=True)`` はこれらの型名を保持する値から求める(行列を保持する
    ``choice.output`` は ``matrix``)。Plug の派生クラスの選択を maya.cmds と合わせるため、
    次の順に保持する値の型を求め、行列なら ``MatrixPlug`` を選べるようにする。

    1. 読み取りできない属性(``MFnAttribute.readable`` が False。transform 系ノード共通の
       ``geometry`` など)と、存在しない要素(配列要素は既存の論理インデックスのもの)は
       値を読まない(評価も要素の作成も起こさない)。
    2. 入力接続があれば、接続元の属性の型を使う。接続元の型が属性定義で決まる場合
       (``worldMatrix[0]`` など)は値を読まず、接続元の評価も起こさない。接続元も値に
       よって型が変わる属性なら、接続元に同じ規則を適用して辿る。辿った先で入力接続の無い
       接続元は値を読むため、上流の評価が起こる(``choice2.input[0]`` ← ``choice1.output``、
       ``choice.input[0]`` ← ``unitConversion.output`` では接続元の出力を評価する)。
    3. 入力接続が無ければ値を読む。ノードが計算する出力(``choice.output`` など)は、
       ``cmds.getAttr(type=True)`` と同じく評価(compute)が起こる。評価によってワールド空間の
       出力の要素が作られる場合もある(インスタンス化されたシェイプの2つ目のインスタンスを
       拘束元にした geometryConstraint の ``constraintGeometry`` では、シェイプの
       ``worldMesh[0]`` が作られる)。

    ``double3`` などの数値の組を保持する場合は子を持たず、``Double3Plug`` では扱えない
    ため対象にしない(基底の Plug の ``get()`` が tuple を返す)。

    Args:
        mplug (om2.MPlug): 対象のプラグ。
        depth (int): 接続元を辿った段数(内部用)。

    Returns:
        str | None: 行列を保持していれば ``"matrix"``、それ以外は None。
    """
    if mplug.isArray or mplug.isCompound:
        return None
    attribute = mplug.attribute()
    if attribute.apiType() == om2.MFn.kTypedAttribute:
        if om2.MFnTypedAttribute(attribute).attrType() != om2.MFnData.kAny:
            return None
    elif not attribute.hasFn(om2.MFn.kGenericAttribute):
        return None
    if not om2.MFnAttribute(attribute).readable or not _plug_exists(mplug):
        return None
    sources = mplug.connectedTo(True, False)
    if sources:
        source = sources[0]
        if source.isArray:
            return None
        type_name = attribute_type(source)
        if type_name is not None:
            return "matrix" if type_name == "matrix" else None
        if depth >= _MAX_SOURCE_DEPTH:
            return None
        return _held_matrix_type(source, depth + 1)
    try:
        data = mplug.asMObject()
    except RuntimeError:
        return None  # 数値・文字列などデータオブジェクトを持たない値
    if not data.isNull() and data.hasFn(om2.MFn.kMatrixData):
        return "matrix"
    return None


def _read_angle(mplug):
    """角度属性の値を度で返す。

    UI の角度単位によらず度を返す(``cmds.getAttr`` の既定と同じ。角度の UI 単位が
    ラジアンの場合は ``cmds.getAttr`` の戻り値と異なる)。

    Args:
        mplug (om2.MPlug): 角度属性のプラグ。

    Returns:
        float: 度の値。
    """
    return mplug.asMAngle().asDegrees()


def _read_distance(mplug):
    """距離属性の値を現在の UI 単位で返す。

    Args:
        mplug (om2.MPlug): 距離属性のプラグ。

    Returns:
        float: UI 単位の値。
    """
    return mplug.asMDistance().asUnits(om2.MDistance.uiUnit())


def _read_time(mplug):
    """時間属性の値を現在の UI 単位で返す。

    Args:
        mplug (om2.MPlug): 時間属性のプラグ。

    Returns:
        float: UI 単位の値。
    """
    return mplug.asMTime().asUnits(om2.MTime.uiUnit())


#: 数値属性の ``numericType()`` と、値を読む MPlug のメソッド。
_NUMERIC_READERS = {
    om2.MFnNumericData.kBoolean: om2.MPlug.asBool,
    om2.MFnNumericData.kByte: om2.MPlug.asInt,
    om2.MFnNumericData.kShort: om2.MPlug.asInt,
    om2.MFnNumericData.kInt: om2.MPlug.asInt,
    om2.MFnNumericData.kLong: om2.MPlug.asInt,
    om2.MFnNumericData.kFloat: om2.MPlug.asDouble,
    om2.MFnNumericData.kDouble: om2.MPlug.asDouble,
}

#: 単位属性の ``unitType()`` と、値を読む関数。
_UNIT_READERS = {
    om2.MFnUnitAttribute.kAngle: _read_angle,
    om2.MFnUnitAttribute.kDistance: _read_distance,
    om2.MFnUnitAttribute.kTime: _read_time,
}

#: :func:`_value_reader` が「MPlug から直接読めない(``cmds.getAttr`` で読む)」ことを表す値。
_CMDS_READER = False


def _value_reader(attribute):
    """``Plug.get()`` が MPlug から直接値を読む関数を、属性定義から選ぶ。

    属性の型は属性ごとに変わらないため、Plug ごとに一度だけ求めて保持する。

    Args:
        attribute (om2.MObject): 属性の MObject。

    Returns:
        callable | bool: MPlug を受け取って値を返す関数。bool/int/float 系の数値属性、
            角度・距離・時間の単位属性、enum、文字列属性が対象。それ以外は
            ``_CMDS_READER`` (``cmds.getAttr`` で読む)。
    """
    if attribute.hasFn(om2.MFn.kNumericAttribute):
        return _NUMERIC_READERS.get(om2.MFnNumericAttribute(attribute).numericType(), _CMDS_READER)
    if attribute.hasFn(om2.MFn.kUnitAttribute):
        return _UNIT_READERS.get(om2.MFnUnitAttribute(attribute).unitType(), _CMDS_READER)
    if attribute.hasFn(om2.MFn.kEnumAttribute):
        return om2.MPlug.asInt
    if (attribute.hasFn(om2.MFn.kTypedAttribute)
            and om2.MFnTypedAttribute(attribute).attrType() == om2.MFnData.kString):
        return om2.MPlug.asString
    return _CMDS_READER


def _plug_exists(mplug):
    """プラグ(と経由する配列要素)がシーンに存在するか判定する。

    配列要素は、配列の既存の論理インデックス(``getExistingArrayAttributeIndices()``。
    値を持つ要素と接続された要素)に含まれる場合に存在する。値を読まないため、
    存在しない要素を作らない。

    Args:
        mplug (om2.MPlug): 判定するプラグ。

    Returns:
        bool: プラグと、経由するすべての配列要素が存在する場合は True。
    """
    current = mplug
    while True:
        if current.isElement:
            array = current.array()
            if current.logicalIndex() not in array.getExistingArrayAttributeIndices():
                return False
            current = array
        elif current.isChild:
            current = current.parent()
        else:
            return True


class Plug:
    """Maya API 2.0 の MPlug を保持する属性ラッパー。

    Plug(node, mplug) は配列・登録済み属性型・複合属性の順で
    専用クラスを選択する。基底クラスの書き込み・接続・ロック操作は
    Undo チャンクで囲まれる。派生クラス独自の経路は各メソッドを参照する。

    ``str(plug)`` と ``full_name()`` は maya.cmds で一意に解決できる
    ``<ノードの最短一意名>.<属性パス>`` を返すため、Plug はそのまま
    ``cmds.getAttr(plug)``/``cmds.connectAttr(a, b)`` などへ渡せる。
    短い名前が重複するノード(``grp1|dup`` と ``grp2|dup``)でも一意で、
    名前変更・親子付け替えにも追従する。ただし ``ArrayPlug`` は ``[]`` で要素を
    取得できるため maya.cmds がシーケンスとして展開しようとして失敗する。
    配列属性全体を渡す場合は ``str(plug)`` か ``plug.full_name()`` を渡す。

    所有ノードが削除された、または動的属性が ``deleteAttr`` で削除された Plug は
    無効になり(:meth:`is_valid`)、``str()``・:meth:`full_name`・:meth:`name` は空文字列、
    値の取得・設定、属性の情報・接続の問い合わせ、要素・子・親の取得は RuntimeError に
    なる(削除済みの MPlug を Maya へ渡すと異常終了する場合があるため)。
    Undo でノード・属性が戻れば再び有効になる。"""

    _registry = None  #: initialize_plug_api() が構築後に注入する PlugRegistry。
    _reader = None  #: get() が値を読む関数。初回の get() で属性定義から選ぶ(_value_reader)。

    def __new__(cls, node, mplug):
        """配列・登録属性型・複合属性の順にラッパー型を選ぶ。

        登録属性型の判定には ``cmds.getAttr(type=True)`` と同じ型名を使う。型名は
        属性定義から求め(:func:`hlib._core.attributeType.attribute_type`)、maya.cmds へ
        問い合わせないため、存在しない配列要素の Plug を作っても要素は作られない。
        値によって型が変わる属性(generic 属性など)は、存在する要素が行列を保持していれば
        ``cmds.getAttr(type=True)`` と同じく ``matrix`` として扱う(``MatrixPlug``)。
        保持する値の型は、入力接続があれば接続元の属性の型から求め、無ければ値を読む。
        値を読む場合(接続元も値によって型が変わる属性で、その接続元を辿って値を読む場合を
        含む)は、ノードが計算する出力の評価が起こり、評価でワールド空間の出力の要素などが
        作られる場合がある(規則は :func:`_held_matrix_type`)。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            Plug: 適切な派生クラスのインスタンス。派生クラスから直接呼んだ場合はそのクラスを割り当てる。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。削除済みの
                Plug から要素・子・親の Plug を取得した場合も含む(``Node.plug()`` と同じ規則)。
                プラグが未確定(-1)の配列インデックスを経由する場合(``cmp[-1].child`` や
                ``inputTarget[-1].inputTargetGroup`` のような maya.cmds で解決できないプラグ)。
                MPlug の所有ノードが node と異なる場合(静的属性・動的属性とも。所有ノードでは
                ない node を渡した誤用)。
        """
        if cls is Plug:
            # ArrayPlug/CompoundPlug との循環importを避けるため呼び出し時に遅延importする。
            from .arrayPlug import ArrayPlug
            from .compoundPlug import CompoundPlug

            handle = node._handle
            if handle is None or not handle.isValid():
                raise RuntimeError("所有ノードが無効な(削除済みの)属性の Plug は作成できません")
            if not mplug.isNull and mplug.node() != node._mobject:
                # 所有ノードではない node を渡した誤用。静的属性は同じ型の別ノードにも存在し
                # attributeClass() では検出できないため、MPlug の所有ノードと比べる。
                raise RuntimeError("MPlug は指定したノードの属性ではありません(所有ノードを指定してください)")
            attribute = mplug.attribute()
            attribute_class = _attribute_class(node, om2.MObjectHandle(attribute), attribute)
            if attribute_class == _INVALID_ATTRIBUTE:
                raise RuntimeError("削除済みの属性の Plug は作成できません")
            if has_unresolved_index(mplug):
                raise RuntimeError(
                    "配列要素のインデックスが未確定(-1)の属性の Plug は作成できません: "
                    + mplug.partialName(False, True, True, True, False, True)
                )
            target = cls
            if mplug.isArray:
                target = ArrayPlug
            else:
                resolved_class = None
                if cls._registry is not None:
                    type_name = attribute_type(mplug)
                    if type_name is None:
                        type_name = _held_matrix_type(mplug)
                    resolved_class = cls._registry.lookup(type_name)
                if resolved_class is not None:
                    target = resolved_class
                elif mplug.isCompound:
                    target = CompoundPlug
            # 選んだクラスの __new__ だけを呼び、__init__ は呼び出し元(Plug(...))の1回に任せる。
            instance = target.__new__(target, node, mplug) if target is not cls else super().__new__(cls)
            # 静的属性かどうかの判定結果を __init__ へ引き継ぎ、判定を繰り返さない。
            instance._pending_static_attribute = attribute_class == _NORMAL_ATTRIBUTE
            return instance
        return super().__new__(cls)

    def __init__(self, node, mplug):
        """所有ノードと API 2.0 MPlug のコピー、属性の有効性を判定するハンドルを保持する。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            None: 値を返さない。
        """
        self._node = node
        self._mplug = om2.MPlug(mplug)
        attribute = self._attribute = self._mplug.attribute()
        # 属性が破棄されたこと(Undo の対象から外れた削除)を検出するためのハンドル。
        self._attribute_handle = om2.MObjectHandle(attribute)
        # 静的属性は削除されない(ノードが有効な間は常に存在する)ため、判定は一度だけ行う。
        static = self.__dict__.pop("_pending_static_attribute", None)
        if static is None:
            handle = node._handle
            static = (handle is not None and handle.isValid()
                      and _attribute_class(node, self._attribute_handle, attribute) == _NORMAL_ATTRIBUTE)
        self._static_attribute = static

    def _attribute_exists(self):
        """属性が所有ノードに存在し続けているか判定する(所有ノードは有効であること)。

        頻繁に呼ばれる :meth:`_require_valid`・:meth:`full_name` は、呼び出しの負荷を
        避けるため同じ判定を直接書いている(変更する場合はそろえること)。

        Returns:
            bool: 静的属性、または削除されていない動的属性の場合は True。
        """
        if self._static_attribute:
            return True
        return (self._attribute_handle.isValid()
                and self._node._dependency_fn().attributeClass(self._attribute) != _INVALID_ATTRIBUTE)

    def is_valid(self):
        """所有ノードと属性がシーンに存在し、値を読み書きできるか判定する。

        Returns:
            bool: 所有ノードが有効で、属性(動的属性は ``deleteAttr`` で削除されうる)が
                存在する場合は ``True``。Undo でノード・属性が戻れば再び ``True`` になる。
        """
        handle = self._node._handle
        return handle is not None and handle.isValid() and self._attribute_exists()

    def _require_valid(self):
        """所有ノードと属性が有効か確かめる。

        削除済みの動的属性の MPlug で値を読み書きすると Maya が異常終了し、削除済みノードの
        MPlug は古い値を返す(Undo の対象から外れた削除では問い合わせで異常終了する場合も
        ある)ため、MPlug・属性を扱う前に必ず確かめる。静的属性はノードが有効な間は常に
        存在するため、ノードの確認だけで済む。動的属性は所有ノードの
        ``MFnDependencyNode.attributeClass()`` で存在を確かめる(:meth:`_attribute_exists`)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        node = self._node
        handle = node._handle
        if handle is None or not handle.isValid():
            raise RuntimeError("所有ノードが無効な(削除済みの)属性は扱えません")
        if not self._static_attribute:
            # _attribute_exists() と同じ判定。get()/set() のたびに呼ばれるため直接書く。
            fn = node._fn_cache
            if fn is None:
                fn = node._dependency_fn()
            if not self._attribute_handle.isValid() or fn.attributeClass(self._attribute) == _INVALID_ATTRIBUTE:
                raise RuntimeError("削除済みの属性は扱えません")

    def mplug(self):
        """内部で保持する Maya API 2.0 MPlug を返す。

        Returns:
            om2.MPlug: ラップ対象のプラグ。
        """
        return self._mplug

    @property
    def node(self):
        """この Plug を所有する hlib ノードを取得する。

        Returns:
            Node: 所有ノード。
        """
        return self._node

    def name(self):
        """ノード名を含まない短いプラグ名を取得する。

        Returns:
            str: 必要な multi インデックスを含むプラグ名。所有ノードが無効(削除済み)、
                または属性が削除済みの場合は空文字列(:meth:`full_name` と同じ)。
        """
        if not self.is_valid():
            return ""
        return self._mplug.partialName(
            includeNodeName=False,
            includeNonMandatoryIndices=True,
            useLongNames=False,
        )

    def full_name(self):
        """maya.cmds で一意に解決できる、ノード名を含む完全修飾プラグ名を取得する。

        ``<ノードの最短一意名>.<属性パス>`` の形式。ノード名は ``Node.name()``
        (``str(node)``)と同じで、呼び出すたびに再計算するため名前変更や
        親子付け替えに追従する。短い名前が重複するノードでも ``grp1|dup.translateX``
        のように一意になる。属性パスはロング名で、必要な配列インデックス
        (``worldMatrix[0]``、``pnts[2].pntx`` 等)を含み、エイリアスがあれば
        エイリアス名を使う(``MPlug.name()`` の属性部分と同じ表記)。

        短い名前が一意なノード(DG ノードと、インスタンス化されていないアンダーワールド以外の
        DAG ノード)は、ノード名が短い名前と一致するため ``MPlug.name()`` をそのまま返す。
        DAG ノードでは短い名前が一意かを毎回問い合わせる(``hasUniqueName()``)ため、
        ``MPlug.name()`` だけを返していた従来より 1 回あたり約 1µs 遅い(同名ノードでも
        一意な名前を返すために必要な処理。:doc:`/development` の性能の項を参照)。

        Returns:
            str: 完全修飾プラグ名。所有ノードが無効(削除済み)、または属性が削除済みの
                場合は空文字列(:meth:`is_valid` が ``False``)。
        """
        node = self._node
        handle = node._handle
        if handle is None or not handle.isValid():
            return ""
        fn = node._fn_cache
        if fn is None:
            fn = node._dependency_fn()
        if not self._static_attribute and (
                not self._attribute_handle.isValid()
                or fn.attributeClass(self._attribute) == _INVALID_ATTRIBUTE):
            return ""  # _attribute_exists() と同じ判定(str() のたびに呼ばれるため直接書く)。
        dag_path = node._dag_path
        if dag_path is None:
            # DG ノードの名前はシーン内で一意(Maya は DAG ノードとの重複も許さない)。
            return self._mplug.name()
        # インスタンス化されたノードとアンダーワールドのノード(``shape->node``)は、
        # Node.name() がパスを含むため、同じ表記になるよう下の経路で求める。
        if dag_path.isValid() and not dag_path.isInstanced() and dag_path.pathCount() == 1 and fn.hasUniqueName():
            return self._mplug.name()
        # plug_path() と同じ引数。頻繁に呼ばれるため関数呼び出しを省いて直接問い合わせる。
        return node.name() + "." + self._mplug.partialName(False, True, True, True, False, True)

    #: ``str(plug)`` は :meth:`full_name` と同じ(maya.cmds は文字列以外の引数に ``str()`` を
    #: 適用するため、Plug をそのまま ``cmds.getAttr(plug)`` のように渡せる)。頻繁に呼ばれるため、
    #: 呼び出しを1段省けるよう同じ関数を割り当てる。
    __str__ = full_name

    def attribute_name(self):
        """基になる Maya 属性のロング名を取得する。

        Returns:
            str: MFnAttribute が返す属性名。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).name

    def nice_name(self):
        """UI 表示用のニース名を取得する。

        Returns:
            str: Attribute Editor 等で使われる表示名(例: ``translateX`` は
                ``"Translate X"``)。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return cmds.attributeName(self.full_name(), nice=True)

    def type(self):
        """このプラグを表す現在の hlib クラスを返す。

        Returns:
            type: 解決済みの Plug サブクラス（例: ``DoubleLinearPlug``）。
        """
        return type(self)

    def data_type(self):
        """属性定義からMayaのデータ型名を取得する。値の評価は行わない。

        Returns:
            str | None: doubleLinear等のMaya型名。値なしでは判定不能なgeneric等はNone。

        Note:
            type()はPythonラッパークラスを返す。未作成の配列要素を生成しない。
        """
        self._require_valid()
        return attribute_type(self._mplug)

    def is_array(self):
        """multi 属性か判定する。

        ``is_array``/``is_compound``/``is_element``/``is_child`` はプラグの構造だけを返すため、
        無効な Plug(:meth:`is_valid` が ``False``)でも例外にしない。

        Returns:
            bool: array プラグの場合は ``True``。
        """
        return self._mplug.isArray

    def is_compound(self):
        """compound 属性か判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        return self._mplug.isCompound

    def is_element(self):
        """multi 属性の要素プラグか判定する。

        Returns:
            bool: array 要素の場合は ``True``。
        """
        return self._mplug.isElement

    def is_child(self):
        """compound 属性の子プラグか判定する。

        Returns:
            bool: 子プラグの場合は ``True``。
        """
        return self._mplug.isChild

    def parent(self):
        """compound 属性の子プラグであれば、その親プラグを取得する。

        Returns:
            Plug | None: 親プラグ。子プラグでない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合
                (子プラグかどうかにかかわらず。削除済みの MPlug は子かどうかを正しく返さないため)。
        """
        self._require_valid()
        if not self._mplug.isChild:
            return None
        return Plug(self._node, self._mplug.parent())

    def is_keyable(self):
        """チャンネルボックスでキー可能な属性か判定する。

        setAttr(keyable=...) によるプラグ単位の動的な上書きを反映する
        （属性定義の既定値だけを見る MFnAttribute.keyable とは異なる）。

        Returns:
            bool: キー可能な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isKeyable



    @staticmethod
    def _validated_flags(locked=None, keyable=None, channel_box=None):
        """状態値を全件検証し、Mayaのフラグ名へ変換する。

        Args:
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー可能状態。
            channel_box (bool | None): Channel Box表示状態。

        Returns:
            dict: 指定されたMayaフラグだけを含む辞書。

        Raises:
            TypeError: boolまたはNone以外の状態がある場合。
        """
        flags = {}
        for name, value in (("lock", locked), ("keyable", keyable), ("channelBox", channel_box)):
            if value is not None:
                if not isinstance(value, bool):
                    raise TypeError(f"{name} must be bool or None")
                flags[name] = value
        return flags

    @fast_edit
    @undo_chunk("hlibPlugSetFlags")
    def set_flags(self, *, locked=None, keyable=None, channel_box=None, fast=False):
        """属性の状態をまとめて変更する。省略した状態は変更しない。

        Args:
            locked (bool | None): ロック状態。
            keyable (bool | None): キー設定可否。
            channel_box (bool | None): Channel Box表示。キー可能な属性はFalseでも表示される。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: 状態がbool/None以外の場合。
            RuntimeError: 属性が無効、またはMayaが更新を拒否した場合。
        """
        flags = self._validated_flags(locked, keyable, channel_box)
        self._require_valid()
        if flags:
            set_attr(self.full_name(), **flags)
        return self

    def is_connected(self):
        """入出力接続を持つか判定する。

        Returns:
            bool: 何らかの接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isConnected

    def is_source(self):
        """出力接続元か判定する。

        Returns:
            bool: 他のプラグへの出力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isSource

    def is_destination(self):
        """入力接続先か判定する。

        Returns:
            bool: 他のプラグからの入力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isDestination

    def is_hidden(self):
        """UI から隠された属性か判定する。

        Returns:
            bool: 隠し属性の場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).hidden

    def is_dynamic(self):
        """動的に追加された属性（addAttr によるカスタム属性等）か判定する。

        Returns:
            bool: 動的属性の場合は ``True``。静的（ノード型に組み込み）の属性は ``False``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).dynamic

    def is_readable(self):
        """値を取得できる属性か判定する。

        Returns:
            bool: 読み取り可能な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).readable

    def is_writable(self):
        """値を設定できる属性か判定する。

        Returns:
            bool: 書き込み可能な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).writable

    def is_storable(self):
        """シーンファイルへ値が保存される属性か判定する。

        Returns:
            bool: 保存対象の場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).storable

    def has_min(self):
        """最小値制限を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最小値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMin()
        return False

    def has_max(self):
        """最大値制限を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最大値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMax()
        return False

    def min(self):
        """設定されている最小値を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。
        誤った単位換算を避けるため、内部でのラジアン/センチメートル変換は行わない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最小値。
                制限が無い、または対応しない属性型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getMin() if fn.hasMin() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getMin() if fn.hasMin() else None
        return None

    def max(self):
        """設定されている最大値を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最大値。
                制限が無い、または対応しない属性型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getMax() if fn.hasMax() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getMax() if fn.hasMax() else None
        return None

    def has_soft_min(self):
        """ソフト最小値（UIスライダーの下限）を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最小値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMin()
        return False

    def has_soft_max(self):
        """ソフト最大値（UIスライダーの上限）を持つ属性か判定する。

        数値属性、角度・距離・時間属性のみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最大値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMax()
        return False

    def soft_min(self):
        """設定されているソフト最小値（UIスライダーの下限）を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最小値。
                制限が無い、または対応しない属性型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getSoftMin() if fn.hasSoftMin() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getSoftMin() if fn.hasSoftMin() else None
        return None

    def soft_max(self):
        """設定されているソフト最大値（UIスライダーの上限）を取得する。

        数値属性は ``float``、角度・距離・時間属性は対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最大値。
                制限が無い、または対応しない属性型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attr)
            return fn.getSoftMax() if fn.hasSoftMax() else None
        if attr.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attr)
            return fn.getSoftMax() if fn.hasSoftMax() else None
        return None

    def default(self):
        """属性の既定値を取得する。

        数値属性は ``float``/``bool``、角度・距離・時間属性は対応する Maya API 2.0
        の単位付きオブジェクト、enum 属性は ``int`` をそのまま返す。

        Returns:
            object | None: 既定値。対応しない属性型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).default
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).default
        if attr.hasFn(om2.MFn.kEnumAttribute):
            return om2.MFnEnumAttribute(attr).default
        return None

    def enum_name(self):
        """enum 属性の現在値に対応するフィールド名を取得する。

        Returns:
            str: 現在値に対応するフィールド名。

        Raises:
            TypeError: enum 属性でない場合。
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enum_name は enum 属性にのみ使用できます")
        return om2.MFnEnumAttribute(attr).fieldName(int(self.get()))

    @undo_chunk("hlibPlugSetEnumNames")
    def set_enum_names(self, names):
        """enum属性の表示名を指定順に更新する。

        Args:
            names (Iterable[str]): 値0から順に対応する空でない名前列。

        Returns:
            Plug: 更新した自身。

        Raises:
            TypeError: enum属性でない、または名前が文字列でない場合。
            ValueError: 空の列、空の名前、区切り文字を含む名前の場合。
            RuntimeError: 属性が無効、またはMayaが変更を拒否した場合。
        """
        self._require_valid()
        if not self._mplug.attribute().hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("set_enum_names requires an enum attribute")
        if isinstance(names, str):
            raise TypeError("names must be a sequence of strings")
        names = list(names)
        if any(not isinstance(name, str) for name in names):
            raise TypeError("enum names must be strings")
        if not names or any(not name or ":" in name or "=" in name for name in names):
            raise ValueError("enum names must be non-empty and contain no ':' or '='")
        cmds.addAttr(self.full_name(), edit=True, enumName=":".join(names))
        return self

    def enum_value(self, name):
        """enum 属性のフィールド名に対応する値を取得する(enum_name の逆引き)。

        Args:
            name (str): 検索するフィールド名。

        Returns:
            int: name に対応する enum 値。

        Raises:
            TypeError: enum 属性でない場合。
            ValueError: name に一致するフィールドが無い場合。
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enum_value は enum 属性にのみ使用できます")
        enum_fn = om2.MFnEnumAttribute(attr)
        for value in range(enum_fn.getMin(), enum_fn.getMax() + 1):
            try:
                if enum_fn.fieldName(value) == name:
                    return value
            except RuntimeError:
                continue
        raise ValueError(f"No enum field named {name!r}")

    def is_locked(self):
        """プラグがロックされているか判定する。

        Returns:
            bool: ロックされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isLocked


    def is_muted(self):
        """アトリビュートがミュートされているか判定する。

        Returns:
            bool: ミュートされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return bool(cmds.mute(self.full_name(), query=True))

    @undo_chunk("hlibPlugSetMuted")
    def set_muted(self, state):
        """ミュート状態を設定する。Trueは現在値で固定し、Falseは解除する。

        Args:
            state (bool): ミュートする場合はTrue。

        Returns:
            Plug: 自身。

        Raises:
            RuntimeError: Maya がミュートを拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        if state:
            cmds.mute(self.full_name())
        else:
            cmds.mute(self.full_name(), disable=True, force=True)
        return self

    @undo_chunk("hlibPlugDeleteAttr")
    def delete_attribute(self, force=False):
        """この属性をノードから削除する。

        動的に追加された属性（addAttr によるカスタム属性）にのみ使用できる。
        静的（ノード型に組み込み）の属性を削除しようとすると Maya が拒否する。
        接続がある場合は force に関わらず Maya が自動的に切断してから削除する。

        Args:
            force (bool): True の場合、ロックされていれば一時的に解除してから
                削除する。False でロックされている属性を削除しようとすると
                RuntimeError になる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: force=False でロックされている場合や、静的属性の
                削除を試みた場合など、Maya が削除を拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        if force and self.is_locked():
            set_attr(self.full_name(), lock=False)
        cmds.deleteAttr(self.full_name())

    def get(self):
        """評価済みの Maya 属性値を取得する。

        bool/int/float 系の数値属性、角度・距離・時間の単位属性、enum、
        文字列属性は Maya API 2.0(MPlug)経由で直接読み取り、MEL コマンドの
        往復を避ける。角度は度、距離・時間は現在の UI 単位で返し、
        ``cmds.getAttr`` の既定挙動と一致させる。message 属性や mesh/カーブ等の
        複雑な typed data 属性のように対応する読み取り方法が無いものは
        ``cmds.getAttr`` にフォールバックする。

        Returns:
            object: 属性値。1要素のリストにタプルが入っている場合のみ、
                そのタプルを返す（cmds.getAttr フォールバック時のみ該当）。
                文字列、数値、配列、None など実際の属性型に依存する。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合
                (:meth:`is_valid` が ``False``。削除前の古い値は返さない)。
                Maya 内部のデータ型(nurbsSurface の ``patchUVIds`` など)の、存在しない
                配列要素の場合(値を読むと Maya が異常終了する場合があるため。
                :func:`hlib._core.attributeType.is_internal_data_type`)。
        """
        self._require_valid()
        reader = self._reader
        if reader is None:
            # 属性の型は変わらないため、読み方は Plug ごとに一度だけ選ぶ。
            reader = self._reader = _value_reader(self._attribute)
        if reader is not _CMDS_READER:
            return reader(self._mplug)

        if is_internal_data_type(self._mplug) and not _plug_exists(self._mplug):
            raise RuntimeError(
                f"Maya 内部のデータ型の存在しない要素の値は読めません: {self.full_name()}"
            )
        value = cmds.getAttr(self.full_name())
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    @fast_edit
    @undo_chunk("hlibPlugSet")
    def set(self, value, *, fast=False):
        """プラグ値を変更する。

        doubleArray/floatArray/Int32Array/Int64Array のようなスカラー配列型と、
        stringArray/vectorArray/floatVectorArray/pointArray/matrixArray/
        componentList のような長さ指定が必要な配列型は、``cmds.setAttr`` が
        要求する引数の形(単純な ``*value`` 展開ではなく、型名や要素数の
        明示)が数値コンパウンド(double3 等)や matrix と異なるため、
        属性定義から ``cmds.getAttr(..., type=True)`` と同じ属性型名を求めてから
        (:func:`hlib._core.attributeType.attribute_type`)対応する形で呼び出す。
        それ以外の型(数値コンパウンド、matrix 等)は従来通り ``*value`` で展開する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (object): 設定する Maya 互換値。

        Returns:
            Plug: 自身。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self._require_valid()
        if is_fast():
            set_plug(self._mplug, value)
            return self
        if isinstance(value, str):
            set_attr(self.full_name(), value, type="string")
            return self
        if isinstance(value, (tuple, list)):
            attr_type = attribute_type(self._mplug)
            if attr_type in _SCALAR_ARRAY_TYPES:
                set_attr(self.full_name(), value, type=attr_type)
            elif attr_type in _LENGTH_PREFIXED_ARRAY_TYPES:
                set_attr(self.full_name(), len(value), *value, type=attr_type)
            else:
                set_attr(self.full_name(), *value)
            return self
        set_attr(self.full_name(), value)
        return self

    @undo_chunk("hlibPlugSetIfChanged")
    def set_if_changed(self, value, *, unlock=False):
        """スカラー値が変わる場合だけ更新し、不要な属性通知を避ける。

        Args:
            value (bool | int | float | str): 比較・設定する値。数値は厳密比較。
            unlock (bool): ロックを一時解除する。失敗時も元のロックへ戻す。

        Returns:
            bool: 値を更新した場合はTrue。

        Raises:
            TypeError: スカラー以外を指定した場合。
            RuntimeError: Mayaが属性更新を拒否した場合。
        """
        if not isinstance(value, (bool, int, float, str)):
            raise TypeError("set_if_changed supports scalar values only")
        if self.get() == value:
            return False
        locked = self.is_locked()
        if unlock and locked:
            self.set_flags(locked=False)
        try:
            self.set(value)
        finally:
            if unlock and locked:
                self.set_flags(locked=True)
        return True

    @fast_edit
    @undo_chunk("hlibPlugReset")
    def reset(self, *, fast=False):
        """数値・単位・enum属性を定義上の既定値へ戻す。

        単位属性は現在のMaya表示単位へ変換する。複合属性は子ごとに処理する。
        接続の切断やロック解除はしない。失敗前の変更は自動では戻さない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Plug: 自身。一回のUndoで全変更を戻せる。

        Raises:
            TypeError: 配列全体・文字列・messageなど既定値を扱えない属性の場合。
            RuntimeError: ロック・入力接続などで変更できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if self.is_array():
            raise TypeError("Reset an array element instead of the array plug")
        self._require_valid()
        if self._mplug.isCompound:
            for index in range(self._mplug.numChildren()):
                Plug(self._node, self._mplug.child(index)).reset()
            return self
        value = self.default()
        if value is None:
            raise TypeError(f"No supported default value for {self.full_name()}")
        if isinstance(value, om2.MAngle):
            value = value.asUnits(om2.MAngle.uiUnit())
        elif isinstance(value, om2.MDistance):
            value = value.asUnits(om2.MDistance.uiUnit())
        elif isinstance(value, om2.MTime):
            value = value.asUnits(om2.MTime.uiUnit())
        self.set(value)
        return self

    def source(self):
        """入力接続元の Plug を取得する。

        Returns:
            Plug | None: 接続元。入力接続がない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        sources = self._mplug.connectedTo(True, False)
        return Plug(self._node_from_mplug(sources[0]), sources[0]) if sources else None

    def anim_curve(self):
        """このプラグに直接接続された animCurve ノードを取得する。

        pairBlend やアニメーションレイヤーを介した間接的な animCurve は解決しない
        （直接の入力接続だけを対象とする）。

        Returns:
            Node | None: 接続されている animCurve ノード。無ければ ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        sources = self._mplug.connectedTo(True, False)
        if not sources:
            return None
        source_mobject = sources[0].node()
        if not source_mobject.hasFn(om2.MFn.kAnimCurve):
            return None
        return self._node_from_mplug(sources[0])

    def destinations(self):
        """出力接続先の Plug をすべて取得する。

        Returns:
            list[Plug]: 接続先プラグ。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、または属性が削除済みの場合。
        """
        self._require_valid()
        return [Plug(self._node_from_mplug(plug), plug) for plug in self._mplug.connectedTo(False, True)]

    def is_connected_to(self, other):
        """指定したプラグと接続されているか判定する。

        入力・出力いずれの向きでも一致すれば True を返す。

        Args:
            other (Plug | om2.MPlug | str): 判定対象のプラグ。文字列は
                ``"node.attribute"`` 形式の属性名。

        Returns:
            bool: 接続されている場合は True。

        Raises:
            TypeError: other が Plug・MPlug・属性名のいずれでもない場合、または文字列が
                属性を指していない場合。
            ValueError: other が空文字列、または空の MPlug の場合(``to_plug`` と同じ)。
            RuntimeError: 自身の所有ノードが無効(削除済み)、または属性が削除済みの場合。
                other の文字列を解決できない(存在しない、または複数の属性に一致する)場合、
                other の MPlug の所有ノードまたは属性が削除済みの場合。
        """
        self._require_valid()
        other = self._coerce_plug(other)
        return any(
            connected == other.mplug()
            for connected in self._mplug.connectedTo(True, True)
        )

    @undo_chunk("hlibPlugConnect")
    def connect(self, target, force=False):
        """このプラグを別のプラグへ接続する。

        target がロックされている場合、``cmds.connectAttr(force=True)`` は
        既存の入力接続を置き換えられても、ロック自体は解除しないため失敗する。
        force=True 指定時は、target がロックされていれば接続の前後で
        一時的にアンロック・再ロックする(ロックされていなければ何もしない)。
        一連の操作は一回の Undo にまとまる。

        Args:
            target (Plug | om2.MPlug | str): 接続先プラグ。文字列は
                ``"node.attribute"`` 形式の属性名。
            force (bool): 既存入力接続を強制的に置き換えるか。ロックされた
                target への接続もこの場合のみ一時アンロックして許可する。

        Returns:
            Plug: 接続先プラグ(MPlug・文字列を渡した場合は変換した Plug)。

        Raises:
            TypeError: target が Plug・MPlug・属性名のいずれでもない場合、または文字列が
                属性を指していない場合。
            ValueError: target が空文字列、または空の MPlug の場合(``to_plug`` と同じ)。
            RuntimeError: 自身または target の所有ノードが無効(削除済み)、または属性が
                削除済みの場合。target の文字列を解決できない(存在しない、または複数の属性に
                一致する)場合。Maya が接続を拒否した場合。
        """
        self._require_valid()
        target = self._coerce_plug(target)
        should_unlock = force and target.is_locked()
        if should_unlock:
            target.set_flags(locked=False)
        try:
            cmds.connectAttr(self.full_name(), target.full_name(), force=force)
        finally:
            if should_unlock:
                target.set_flags(locked=True)
        return target

    @undo_chunk("hlibPlugDisconnect")
    def disconnect(self, target=None):
        """プラグ接続を解除する。

        Args:
            target (Plug | om2.MPlug | str | None): 明示的に解除する接続先。
                文字列は ``"node.attribute"`` 形式の属性名。省略時は入力元と
                全出力先を解除する。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: target が None・Plug・MPlug・属性名のいずれでもない場合、または
                文字列が属性を指していない場合。
            ValueError: target が空文字列、または空の MPlug の場合(``to_plug`` と同じ)。
            RuntimeError: 自身の所有ノードが無効(削除済み)、または属性が削除済みの場合。
                target の文字列を解決できない(存在しない、または複数の属性に一致する)場合、
                target の MPlug の所有ノードまたは属性が削除済みの場合。Maya が接続解除を
                拒否した場合(削除済みの target の Plug を渡した場合を含む)。
        """
        self._require_valid()
        if target is not None:
            target = self._coerce_plug(target)
            cmds.disconnectAttr(self.full_name(), target.full_name())
            return self
        source = self.source()
        if source is not None:
            cmds.disconnectAttr(source.full_name(), self.full_name())
        for destination in self.destinations():
            cmds.disconnectAttr(self.full_name(), destination.full_name())
        return self

    def __repr__(self):
        """デバッグ用に完全修飾プラグ名を含む表現を返す。

        Returns:
            str: Plug と完全修飾プラグ名を含む文字列表現。所有ノードが無効、または属性が削除済みなら
                ``<Plug invalid>``。
        """
        name = self.full_name()
        if not name:
            return "<Plug invalid>"
        return f"Plug({name!r})"

    @staticmethod
    def _coerce_plug(value):
        """接続先入力を Plug へ変換する。

        Args:
            value (Plug | om2.MPlug | str): Plug、MPlug、または ``"node.attribute"``
                形式の属性名。

        Returns:
            Plug: value が Plug なら同じオブジェクト、それ以外は変換した Plug。

        Raises:
            TypeError: 対応しない型、または文字列が属性を指していない場合。
            ValueError: 空文字列、または空の MPlug の場合。
            RuntimeError: 文字列を解決できない(存在しない、または複数の属性に一致する)場合、
                または MPlug の所有ノード・属性が削除済みの場合。
        """
        return to_plug(value)

    @staticmethod
    def _node_from_mplug(mplug):
        """MPlug の所有 MObject から汎用 Node ラッパーを生成する。

        Args:
            mplug (om2.MPlug): 所有ノードを取得するプラグ。

        Returns:
            Node: 所有ノードの型登録に従って解決したラッパー。
        """
        # nodes.node が ..plugs.plug を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..nodes.node import Node

        return Node(mplug.node())
