"""Maya API 2.0 の MPlug をアトリビュートラッパーとして扱う。"""

import re

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.attributeType import attributeType, is_internal_data_type, value_reader
from .._core.fastWrite import set_attr
from .._core.fastWrite import set_plug
from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias, _is_alias
from .._core.object import Object
from .._core.unitValue import convert
from ..common._fast import fast_edit, is_fast
from ..common._safe import safe_edit
from ..decorator import undoChunk

#: アトリビュートパスの1区切り(``pnts[2]``、``pntx`` など)。アトリビュート名と、続く論理インデックスの並び。
_PLUG_PATH_TOKEN = re.compile(r"(\w+)((?:\[\d+\])*)\Z")

#: 区切り内の論理インデックス(``[2]`` の ``2``)。
_PLUG_PATH_INDEX = re.compile(r"\[(\d+)\]")

#: 配列要素の論理インデックスの上限(``MPlug.logicalIndex()`` が返す符号付き 32 ビット整数の最大値)。
#: ``MPlug.elementByLogicalIndex()`` はこれを超える番号を黙って別の番号へ変換する
#: (``2147483648``〜``4294967295`` は負の番号、``4294967296`` は ``0``)ため、アトリビュートパスでは
#: 範囲外として扱う。
MAX_LOGICAL_INDEX = 2147483647

#: cmds.setAttr へ値をそのまま(型名付きで、長さ指定なし)渡せば済むスカラー配列型。
_SCALAR_ARRAY_TYPES = frozenset(("doubleArray", "floatArray", "Int32Array", "Int64Array"))

#: cmds.setAttr へ ``長さ, *値, type=...`` の形で渡す必要がある配列型。
_LENGTH_PREFIXED_ARRAY_TYPES = frozenset((
    "stringArray", "vectorArray", "floatVectorArray", "pointArray", "matrixArray",
    "componentList",
))

#: ``MFnDependencyNode.attributeClass()`` が、ノードに無いアトリビュート(削除済みの動的アトリビュートなど)に返す値。
_INVALID_ATTRIBUTE = om2.MFnDependencyNode.kInvalidAttr

#: ``MFnDependencyNode.attributeClass()`` が、ノード型に組み込みの(静的な)アトリビュートに返す値。
_NORMAL_ATTRIBUTE = om2.MFnDependencyNode.kNormalAttr

#: 値によって型が変わるアトリビュートの接続元を辿る最大の段数(循環する接続の保護)。
_MAX_SOURCE_DEPTH = 16


def _instance_count(array):
    """ワールド空間アトリビュートの配列なら、所有 DAG ノードのインスタンス数を返す。

    ``worldMatrix`` などのワールド空間アトリビュートは、インスタンス番号(0～インスタンス数-1)の
    要素を評価前でも存在するものとして扱う(:class:`ArrayPlug` と同じ規則)。

    Args:
        array (om2.MPlug): 配列プラグ。

    Returns:
        int: 間接インスタンスを含むインスタンス数。ワールド空間アトリビュートでなければ 0。
    """
    node = array.node()
    if not node.hasFn(om2.MFn.kDagNode) or not om2.MFnAttribute(array.attribute()).worldSpace:
        return 0
    return om2.MFnDagNode(node).instanceCount(True)


def _attribute_class(node, attribute_handle, attribute):
    """アトリビュートが所有ノードに存在するかと、静的なアトリビュートかを判定する。

    ``addAttr`` による動的アトリビュート(``addExtension`` による拡張アトリビュートを含む)は削除でき、削除済みの
    アトリビュートの MPlug で値を読み書きすると Maya が異常終了する。削除は Undo のためにアトリビュートの
    MObject が保持されたままの場合があり、``MObjectHandle.isValid()`` だけでは判定できない
    ため、所有ノードの ``MFnDependencyNode.attributeClass()`` で確かめる(ノードに無いアトリビュートは
    ``kInvalidAttr``)。同じ名前で追加し直したアトリビュートは別のアトリビュートとして扱い、Undo で削除を
    取り消したアトリビュートと名前を変更したアトリビュートは同じアトリビュートのまま。

    Args:
        node (Node): 所有ノードのラッパー。有効(削除済みでない)であること。
        attribute_handle (om2.MObjectHandle): アトリビュートの MObject のハンドル。
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        int: ``MFnDependencyNode`` の ``kNormalAttr``(静的アトリビュート)・``kLocalDynamicAttr``・
            ``kExtensionAttr``、またはノードに無いアトリビュートの ``kInvalidAttr``。
    """
    if not attribute_handle.isValid():
        return _INVALID_ATTRIBUTE
    return node._dependency_fn().attributeClass(attribute)


def _held_matrix_type(mplug, depth=0):
    """値によって型が変わるアトリビュートが行列を保持していれば ``"matrix"`` を返す。

    対象は generic アトリビュート(``unitConversion.input`` など)と、任意のデータを受け付ける
    型付きアトリビュート(``MFnData.kAny``。``choice`` の ``input``/``output`` など)。
    ``cmds.getAttr(type=True)`` はこれらの型名を保持する値から求める(行列を保持する
    ``choice.output`` は ``matrix``)。Plug の派生クラスの選択を maya.cmds と合わせるため、
    次の順に保持する値の型を求め、行列なら ``MatrixPlug`` を選べるようにする。

    1. 読み取りできないアトリビュート(``MFnAttribute.readable`` が False。transform 系ノード共通の
       ``geometry`` など)と、存在しない要素(配列要素は既存の論理インデックスのもの)は
       値を読まない(評価も要素の作成も起こさない)。
    2. 入力接続があれば、接続元のアトリビュートの型を使う。接続元の型がアトリビュート定義で決まる場合
       (``worldMatrix[0]`` など)は値を読まず、接続元の評価も起こさない。接続元も値に
       よって型が変わるアトリビュートなら、接続元に同じ規則を適用して辿る。辿った先で入力接続の無い
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
        type_name = attributeType(source)
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


class DeletedAttributeError(ValueError, RuntimeError):
    """``deleteAttr`` で削除されたアトリビュートの Plug・MPlug を、ノードが必要な引数に渡した場合の例外。

    所有ノードは有効なままアトリビュートだけが削除された Plug・MPlug は、所有ノードへ解決すると
    削除済みの対象を黙って受け付けてしまうため、``Node._resolve_input``・``Node(...)``/``hlib.getNode``・
    ``hlib.addConstraint`` の拘束元・拘束先などでも例外にする。hlib のコマンド(``Object._input_name``)と
    同じく ``ValueError`` として扱う。``Node(...)`` は解決できない対象をすべて
    ``RuntimeError`` にする規則のため、``RuntimeError`` としても捕捉できるようにしている
    (標準ライブラリの ``io.UnsupportedOperation`` が ``OSError`` と ``ValueError`` の両方を
    継承するのと同じ考え方)。
    """


class Plug(Object):
    """Maya API 2.0 の MPlug を保持するアトリビュートラッパー。

    Plug(node, mplug) は配列・登録済みアトリビュート型・複合アトリビュートの順で
    専用クラスを選択する。基底クラスの書き込み・接続・ロック操作は
    Undo チャンクで囲まれる。派生クラス独自の経路は各メソッドを参照する。

    ``str(plug)`` と ``getFullName()`` は maya.cmds で一意に解決できる
    ``<ノードの最短一意名>.<アトリビュートパス>`` を返すため、Plug はそのまま
    ``cmds.getAttr(plug)``/``cmds.connectAttr(a, b)`` などへ渡せる。
    短い名前が重複するノード(``grp1|dup`` と ``grp2|dup``)でも一意で、
    名前変更・親子付け替えにも追従する。ただし ``ArrayPlug`` と複合Plugは ``[]`` で要素を
    取得できるため maya.cmds がシーケンスとして展開しようとして失敗する。
    配列・複合アトリビュートを渡す場合は ``str(plug)`` か ``plug.getFullName()`` を渡す。

    所有ノードが削除された、または動的アトリビュートが ``deleteAttr`` で削除された Plug は
    無効になり(:meth:`isValid`)、``str()``・:meth:`fullName`・:meth:`name` は空文字列、
    値の取得・設定、アトリビュートの情報・接続の問い合わせ、要素・子・親の取得は RuntimeError に
    なる(削除済みの MPlug を Maya へ渡すと異常終了する場合があるため)。
    Undo でノード・アトリビュートが戻れば再び有効になる。"""

    _registry = None  #: initialize_plug_api() が構築後に注入する PlugRegistry。
    _reader = None  #: get() が値を読む関数。初回の get() でアトリビュート定義から選ぶ(value_reader)。

    def __new__(cls, node, mplug):
        """配列・登録アトリビュート型・複合アトリビュートの順にラッパー型を選ぶ。

        登録アトリビュート型の判定には ``cmds.getAttr(type=True)`` と同じ型名を使う。型名は
        アトリビュート定義から求め(:func:`hlib._core.attributeType.attributeType`)、maya.cmds へ
        問い合わせないため、存在しない配列要素の Plug を作っても要素は作られない。
        値によって型が変わるアトリビュート(generic アトリビュートなど)は、存在する要素が行列を保持していれば
        ``cmds.getAttr(type=True)`` と同じく ``matrix`` として扱う(``MatrixPlug``)。
        保持する値の型は、入力接続があれば接続元のアトリビュートの型から求め、無ければ値を読む。
        値を読む場合(接続元も値によって型が変わるアトリビュートで、その接続元を辿って値を読む場合を
        含む)は、ノードが計算する出力の評価が起こり、評価でワールド空間の出力の要素などが
        作られる場合がある(規則は :func:`_held_matrix_type`)。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            Plug: 適切な派生クラスのインスタンス。派生クラスから直接呼んだ場合はそのクラスを割り当てる。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。削除済みの
                Plug から要素・子・親の Plug を取得した場合も含む(``Node.getPlug()`` と同じ規則)。
                プラグが未確定(-1)の配列インデックスを経由する場合(``cmp[-1].child`` や
                ``inputTarget[-1].inputTargetGroup`` のような maya.cmds で解決できないプラグ)。
                MPlug の所有ノードが node と異なる場合(静的アトリビュート・動的アトリビュートとも。所有ノードでは
                ない node を渡した誤用)。
        """
        if cls is Plug:
            # ArrayPlug/CompoundPlug との循環importを避けるため呼び出し時に遅延importする。
            from .arrayPlug import ArrayPlug
            from .compoundPlug import CompoundPlug

            handle = node._handle
            if handle is None or not handle.isValid():
                raise RuntimeError("所有ノードが無効な(削除済みの)アトリビュートの Plug は作成できません")
            if not mplug.isNull and mplug.node() != node._mobject:
                # 所有ノードではない node を渡した誤用。静的アトリビュートは同じ型の別ノードにも存在し
                # attributeClass() では検出できないため、MPlug の所有ノードと比べる。
                raise RuntimeError("MPlug は指定したノードのアトリビュートではありません(所有ノードを指定してください)")
            attribute = mplug.attribute()
            attribute_class = _attribute_class(node, om2.MObjectHandle(attribute), attribute)
            if attribute_class == _INVALID_ATTRIBUTE:
                raise RuntimeError("削除済みのアトリビュートの Plug は作成できません")
            if Plug._has_unresolved_index(mplug):
                raise RuntimeError(
                    "配列要素のインデックスが未確定(-1)のアトリビュートの Plug は作成できません: "
                    + mplug.partialName(False, True, True, True, False, True)
                )
            target = cls
            if mplug.isArray:
                target = ArrayPlug
            else:
                resolved_class = None
                if cls._registry is not None:
                    type_name = attributeType(mplug)
                    if type_name is None:
                        type_name = _held_matrix_type(mplug)
                    resolved_class = cls._registry.lookup(type_name)
                if resolved_class is not None:
                    target = resolved_class
                elif mplug.isCompound:
                    target = CompoundPlug
            # 選んだクラスの __new__ だけを呼び、__init__ は呼び出し元(Plug(...))の1回に任せる。
            instance = target.__new__(target, node, mplug) if target is not cls else super().__new__(cls)
            # 静的アトリビュートかどうかの判定結果を __init__ へ引き継ぎ、判定を繰り返さない。
            instance._pending_static_attribute = attribute_class == _NORMAL_ATTRIBUTE
            return instance
        return super().__new__(cls)

    def __init__(self, node, mplug):
        """所有ノードと API 2.0 MPlug のコピー、アトリビュートの有効性を判定するハンドルを保持する。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            None: 値を返さない。
        """
        self._node = node
        self._mplug = om2.MPlug(mplug)
        self._identity_path = "." + mplug.partialName(includeNonMandatoryIndices=True, includeInstancedIndices=True)
        self._identity_hash = hash((hash(node), self._identity_path))
        attribute = self._attribute = self._mplug.attribute()
        # アトリビュートが破棄されたこと(Undo の対象から外れた削除)を検出するためのハンドル。
        self._attribute_handle = om2.MObjectHandle(attribute)
        # 静的アトリビュートは削除されない(ノードが有効な間は常に存在する)ため、判定は一度だけ行う。
        static = self.__dict__.pop("_pending_static_attribute", None)
        if static is None:
            handle = node._handle
            static = (handle is not None and handle.isValid()
                      and _attribute_class(node, self._attribute_handle, attribute) == _NORMAL_ATTRIBUTE)
        self._static_attribute = static

    def __eq__(self, other):
        """生存中の同じアトリビュート参照を比較する。削除済みのAPIへ照会しない。

        Args:
            other: 比較・演算の相手。
        """
        if not isinstance(other, Plug):
            return NotImplemented
        if not (self._node.isAlive() and other._node.isAlive()
                and self._attribute_handle.isAlive() and other._attribute_handle.isAlive()):
            return False
        return self._identity_path == other._identity_path and self._mplug == other._mplug

    def __hash__(self):
        """生成時の所有ノードとアトリビュートパスに基づく固定ハッシュを返す。"""
        return self._identity_hash

    def __repr__(self):
        """デバッグ用に完全修飾プラグ名を含む表現を返す。

        Returns:
            str: Plug と完全修飾プラグ名を含む文字列表現。所有ノードが無効、またはアトリビュートが削除済みなら
                ``<Plug invalid>``。
        """
        name = self.getFullName()
        if not name:
            return "<Plug invalid>"
        return f"Plug({name!r})"

    def getNode(self):
        """この Plug を所有する hlib ノードを取得する。

        Returns:
            Node: 所有ノード。
        """
        return self._node

    def isValid(self):
        """所有ノードとアトリビュートの参照が有効か判定する。

        ロック・接続・アトリビュート定義による読み書きの可否は判定しない。

        Returns:
            bool: 所有ノードが有効で、アトリビュート(動的アトリビュートは ``deleteAttr`` で削除されうる)が
                存在する場合は ``True``。Undo でノード・アトリビュートが戻れば再び ``True`` になる。
        """
        handle = self._node._handle
        return handle is not None and handle.isValid() and self._attribute_exists()

    @_is_alias(isValid)
    def valid(self, *args, **kwargs):
        """isValidへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isValid(*args, **kwargs)

    def mplug(self):
        """内部で保持する Maya API 2.0 MPlug を返す。

        Returns:
            om2.MPlug: ラップ対象のプラグ。
        """
        return self._mplug

    def getName(self):
        """最短一意ノード名と短いアトリビュート名を含むPlug名を取得する。

        Returns:
            str: 必要な multi インデックスを含むプラグ名。所有ノードが無効(削除済み)、
                またはアトリビュートが削除済みの場合は空文字列(:meth:`fullName` と同じ)。
        """
        if not self.isValid():
            return ""
        return self.getNode().getName() + self.getAttrName()

    def getAttrName(self):
        """先頭ドットと必要な要素番号を含む短いアトリビュートパスを返す。

        Returns:
            str: ノード名を除いたPlug名。無効な場合は空文字列。
        """
        if not self.isValid():
            return ""
        return "." + self._mplug.partialName(
            includeNodeName=False,
            includeNonMandatoryIndices=True,
            useLongNames=False,
        )

    def getShortName(self):
        """要素番号や階層を含まないアトリビュートの短名。

        Returns:
            str: 要素番号や階層を含まないアトリビュートの短名。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).shortName

    def getPlugName(self, short=False, fullAttrPath=False):
        """ノード名を含むPlug名を取得する。

        Args:
            short (bool): アトリビュートの短名を使う。
            fullAttrPath (bool): コンパウンドの全階層を含める。
        Returns:
            str: Plug名。
        """
        self._require_valid()
        return self.getNode().getName() + "." + self._mplug.partialName(
            includeNonMandatoryIndices=True, includeInstancedIndices=True,
            useFullAttributePath=fullAttrPath, useLongNames=not short)

    def getFullName(self):
        """maya.cmds で一意に解決できる、ノード名を含む完全修飾プラグ名を取得する。

        ``<ノードの最短一意名>.<アトリビュートパス>`` の形式。ノード名は ``Node.getName()``
        (``str(node)``)と同じで、呼び出すたびに再計算するため名前変更や
        親子付け替えに追従する。短い名前が重複するノードでも ``grp1|dup.translateX``
        のように一意になる。アトリビュートパスはロング名で、必要な配列インデックス
        (``worldMatrix[0]``、``pnts[2].pntx`` 等)を含み、エイリアスがあれば
        エイリアス名を使う(``MPlug.name()`` のアトリビュート部分と同じ表記)。

        短い名前が一意なノード(DG ノードと、インスタンス化されていないアンダーワールド以外の
        DAG ノード)は、ノード名が短い名前と一致するため ``MPlug.name()`` をそのまま返す。
        DAG ノードでは短い名前が一意かを毎回問い合わせる(``hasUniqueName()``)ため、
        ``MPlug.name()`` だけを返していた従来より 1 回あたり約 1µs 遅い(同名ノードでも
        一意な名前を返すために必要な処理。:doc:`/development` の性能の項を参照)。

        Returns:
            str: 完全修飾プラグ名。所有ノードが無効(削除済み)、またはアトリビュートが削除済みの
                場合は空文字列(:meth:`isValid` が ``False``)。
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
        dagPath = node._dag_path
        if dagPath is None:
            # DG ノードの名前はシーン内で一意(Maya は DAG ノードとの重複も許さない)。
            return self._mplug.name()
        # インスタンス化されたノードとアンダーワールドのノード(``shape->node``)は、
        # Node.name() がパスを含むため、同じ表記になるよう下の経路で求める。
        if dagPath.isValid() and not dagPath.isInstanced() and dagPath.pathCount() == 1 and fn.hasUniqueName():
            return self._mplug.name()
        # plug_path() と同じ引数。頻繁に呼ばれるため関数呼び出しを省いて直接問い合わせる。
        return node.getName() + "." + self._mplug.partialName(False, True, True, True, False, True)

    #: ``str(plug)`` は :meth:`fullName` と同じ(maya.cmds は文字列以外の引数に ``str()`` を
    #: 適用するため、Plug をそのまま ``cmds.getAttr(plug)`` のように渡せる)。頻繁に呼ばれるため、
    #: 呼び出しを1段省けるよう同じ関数を割り当てる。
    __str__ = getFullName

    def getLongName(self):
        """基になる Maya アトリビュートのロング名を取得する。

        Returns:
            str: MFnAttribute が返すアトリビュート名。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).name

    def getNiceName(self):
        """UI 表示用のニース名を取得する。

        Returns:
            str: Attribute Editor 等で使われる表示名(例: ``translateX`` は
                ``"Translate X"``)。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return cmds.attributeName(self.getFullName(), nice=True)

    def getType(self):
        """このプラグを表す現在の hlib クラスを返す。

        Returns:
            type: 解決済みの Plug サブクラス（例: ``DoubleLinearPlug``）。
        """
        return type(self)

    def getDataType(self):
        """アトリビュート定義からMayaのデータ型名を取得する。値の評価は行わない。

        Returns:
            str | None: doubleLinear等のMaya型名。値なしでは判定不能なgeneric等はNone。

        Note:
            type()はPythonラッパークラスを返す。未作成の配列要素を生成しない。
        """
        self._require_valid()
        return attributeType(self._mplug)

    def isArray(self):
        """multi アトリビュートか判定する。

        ``isArray``/``isCompound``/``isElement``/``isChild`` はプラグの構造だけを返すため、
        無効な Plug(:meth:`isValid` が ``False``)でも例外にしない。

        Returns:
            bool: array プラグの場合は ``True``。
        """
        return self._mplug.isArray

    @_is_alias(isArray)
    def array(self, *args, **kwargs):
        """isArrayへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isArray(*args, **kwargs)

    def isCompound(self):
        """compound アトリビュートか判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        return self._mplug.isCompound

    @_is_alias(isCompound)
    def compound(self, *args, **kwargs):
        """isCompoundへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isCompound(*args, **kwargs)

    def isElement(self):
        """multi アトリビュートの要素プラグか判定する。

        Returns:
            bool: array 要素の場合は ``True``。
        """
        return self._mplug.isElement

    def isChild(self):
        """compound アトリビュートの子プラグか判定する。

        Returns:
            bool: 子プラグの場合は ``True``。
        """
        return self._mplug.isChild

    @_is_alias(isChild)
    def child(self, *args, **kwargs):
        """isChildへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isChild(*args, **kwargs)

    def getParent(self):
        """compound アトリビュートの子プラグであれば、その親プラグを取得する。

        Returns:
            Plug | None: 親プラグ。子プラグでない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合
                (子プラグかどうかにかかわらず。削除済みの MPlug は子かどうかを正しく返さないため)。
        """
        self._require_valid()
        if not self._mplug.isChild:
            return None
        return Plug(self._node, self._mplug.parent())

    def isKeyable(self):
        """チャンネルボックスでキー可能なアトリビュートか判定する。

        setAttr(keyable=...) によるプラグ単位の動的な上書きを反映する
        （アトリビュート定義の既定値だけを見る MFnAttribute.keyable とは異なる）。

        Returns:
            bool: キー可能な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isKeyable

    @_is_alias(isKeyable)
    def keyable(self, *args, **kwargs):
        """isKeyableへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isKeyable(*args, **kwargs)

    @undoChunk("hlibPlugSetKeyable")
    def setKeyable(self, val=True, leaf=False):
        """キー設定可否を設定する。

        Args:
            val (bool): キー設定可否。
            leaf (bool): コンパウンドの末端だけを設定する。
        Returns:
            Plug: 自身。
        """
        return self._set_flags(leaf, keyable=val)

    @fast_edit
    @undoChunk("hlibPlugSetFlags")
    def setFlags(self, *, locked=None, keyable=None, channelBox=None, fast=False):
        """アトリビュートの状態をまとめて変更する。省略した状態は変更しない。

        Args:
            locked (bool | None): ロック状態。
            keyable (bool | None): キー設定可否。
            channelBox (bool | None): Channel Box表示。キー可能なアトリビュートはFalseでも表示される。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: 状態がbool/None以外の場合。
            RuntimeError: アトリビュートが無効、またはMayaが更新を拒否した場合。
        """
        flags = self._validated_flags(locked, keyable, channelBox)
        self._require_valid()
        if flags:
            set_attr(self.getFullName(), **flags)
        return self

    def isChannelBox(self):
        """Channel Boxフラグ（keyableによる表示を含まない）。

        Returns:
            bool: Channel Boxフラグ（keyableによる表示を含まない）。
        """
        self._require_valid()
        return self.mplug().isChannelBox

    @_is_alias(isChannelBox)
    def channelBox(self, *args, **kwargs):
        """isChannelBoxへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isChannelBox(*args, **kwargs)

    @undoChunk("hlibPlugSetChannelBox")
    def setChannelBox(self, val=True, leaf=False):
        """Channel Box表示を設定する。

        Args:
            val (bool): 表示状態。有効時はkeyableを無効にする。
            leaf (bool): コンパウンドの末端だけを設定する。
        Returns:
            Plug: 自身。
        """
        return self._set_flags(leaf, channelBox=val)

    @undoChunk("hlibPlugUnlock")
    def unlock(self, below=False, undoable=True):
        """上位と必要な下位階層をアンロックする。

        Args:
            below (bool): 子階層も解除する。
            undoable (bool): FalseはOpenMayaによるUndoなしの更新。
        Returns:
            list[Plug]: 実際に解除したPlugを上位から返す。
        """
        self._require_valid()
        queue, mp = [], self.mplug()
        while True:
            queue.append(Plug(self.getNode(), mp))
            if mp.isChild:
                mp = mp.parent()
            elif mp.isElement:
                mp = mp.array()
            else:
                break
        result = []
        def unlock_one(plug):
            """継承ロックが解除された後の自身のロックだけを変更する。"""
            if plug.isLocked():
                plug.setFlags(locked=False, fast=not undoable)
                result.append(plug)
        for plug in reversed(queue):
            unlock_one(plug)
        def visit(plug):
            """下位階層を親から順に解除する。"""
            for child in plug.getElements() if plug.isArray() else plug.getChildren() if plug.isCompound() else []:
                unlock_one(child)
                visit(child)
        if below:
            visit(self)
        return result

    def mute(self):
        """ミュートを有効にして自身を返す。

        Returns:
            Plug: ミュートを有効にして自身を返す。
        """
        return self.setMuted(True)

    def unmute(self):
        """ミュートを解除して自身を返す。

        Returns:
            Plug: ミュートを解除して自身を返す。
        """
        return self.setMuted(False)

    def getNextAvailable(self, start=-1, asPlug=False, checkLocked=True, checkChildren=True):
        """入力接続できる次の配列要素を探す。

        Args:
            start (int): 探索開始番号。負数は最後の接続要素の次。
            asPlug (bool): 番号の代わりにPlugを返す。
            checkLocked (bool): ロックされた要素を避ける。
            checkChildren (bool): 子とその配列も調べる。
        Returns:
            int | Plug: 空き番号または要素。
        """
        self._require_valid()
        mp = self.mplug()
        if not mp.isArray:
            raise TypeError("Expected an array plug")
        if checkLocked and self.isLocked():
            raise RuntimeError("Array is locked: " + self.getFullName())
        if start < 0:
            count = mp.numConnectedElements()
            start = mp.connectionByPhysicalIndex(count - 1).logicalIndex() + 1 if count else 0
        index = self._validate_index(start)
        def occupied(value):
            """子階層を含む入力とロックを確認する。"""
            if value.isDestination or (checkLocked and value.isLocked):
                return True
            if checkChildren:
                if value.isArray:
                    return any(occupied(value.elementByLogicalIndex(i)) for i in value.getExistingArrayAttributeIndices())
                if value.isCompound:
                    return any(occupied(value.child(i)) for i in range(value.numChildren()))
            return False
        while index <= MAX_LOGICAL_INDEX:
            candidate = mp.elementByLogicalIndex(index)
            if not occupied(candidate):
                return Plug(self.getNode(), candidate) if asPlug else index
            index += 1
        raise IndexError("No available array index")

    @flag_aliases(index="idx")
    @undoChunk("hlibPlugAddElement")
    def addElement(self, idx=None):
        """指定要素と必要な上位要素を実体化し、下位から順に返す。

        Args:
            idx (int | None): 配列の論理番号。要素自身では省略可能。 別名 ``index`` も使用可能。
        Returns:
            list[Plug]: 新たに実体化した要素。既存の場合は空リスト。
        Note:
            Maya標準の評価で実体化するため、追加自体はUndo対象外。
            実体化だけを取り消すUndoには対応しない。
        """
        self._require_valid()
        mp = self.mplug()
        if idx is not None:
            if not mp.isArray:
                raise TypeError("Expected an array plug")
            mp = mp.elementByLogicalIndex(self._validate_index(idx))
        queue = []
        while True:
            if mp.isElement:
                parent = mp.array()
                if mp.logicalIndex() not in parent.getExistingArrayAttributeIndices():
                    queue.append(Plug(self.getNode(), mp))
                mp = parent
            elif mp.isChild:
                mp = mp.parent()
            else:
                break
        # 危険な内部型やmessageは評価前に拒否し、未作成を成功として返さない。
        for plug in queue:
            if is_internal_data_type(plug.mplug()) or plug.mplug().attribute().hasFn(om2.MFn.kMessageAttribute):
                raise NotImplementedError("Element materialization is unsupported for this attribute type")
        for plug in reversed(queue):
            cmds.getAttr(plug.getFullName(), type=True)
        for plug in queue:
            mp = plug.mplug()
            if mp.logicalIndex() not in mp.array().getExistingArrayAttributeIndices():
                raise RuntimeError("Maya did not materialize the array element: " + plug.getFullName())
        return queue

    @flag_aliases(source="src", destination="dst")
    def isConnected(self, *, src=True, dst=True):
        """指定方向の直接の接続を持つか判定する。

        Args:
            src (bool): 入力元からの接続を調べる。別名 ``source`` も使用可能。
            dst (bool): 出力先への接続を調べる。別名 ``destination`` も使用可能。

        Returns:
            bool: 指定方向に接続を持つ場合は ``True``。両Falseなら ``False``。

        Raises:
            TypeError: 方向指定がboolでない場合、または別名と重複指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        self._validate_connection_directions(src, dst)
        if src and dst:
            return self._mplug.isConnected
        return (src and self._mplug.isDestination) or (dst and self._mplug.isSource)

    @_is_alias(isConnected)
    def connected(self, *args, **kwargs):
        """isConnectedへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isConnected(*args, **kwargs)

    def isSource(self):
        """出力接続元か判定する。

        Returns:
            bool: 他のプラグへの出力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isSource

    def isDestination(self):
        """入力接続先か判定する。

        Returns:
            bool: 他のプラグからの入力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isDestination

    @_is_alias(isDestination)
    def destination(self, *args, **kwargs):
        """isDestinationへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isDestination(*args, **kwargs)

    def isHidden(self):
        """UI から隠されたアトリビュートか判定する。

        Returns:
            bool: 隠しアトリビュートの場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).hidden

    @_is_alias(isHidden)
    def hidden(self, *args, **kwargs):
        """isHiddenへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isHidden(*args, **kwargs)

    def isDynamic(self):
        """動的に追加されたアトリビュート（addAttr によるカスタムアトリビュート等）か判定する。

        Returns:
            bool: 動的アトリビュートの場合は ``True``。静的（ノード型に組み込み）のアトリビュートは ``False``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).dynamic

    @_is_alias(isDynamic)
    def dynamic(self, *args, **kwargs):
        """isDynamicへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isDynamic(*args, **kwargs)

    def isReadable(self):
        """アトリビュート定義の readable フラグを取得する。

        値の取得が成功することを保証する検査ではない。

        Returns:
            bool: 定義の readable が有効な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).readable

    @_is_alias(isReadable)
    def readable(self, *args, **kwargs):
        """isReadableへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isReadable(*args, **kwargs)

    def isWritable(self):
        """アトリビュート定義の writable フラグを取得する。

        ロックや入力接続を含めた現在の編集可否は判定しない。

        Returns:
            bool: 定義の writable が有効な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).writable

    @_is_alias(isWritable)
    def writable(self, *args, **kwargs):
        """isWritableへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isWritable(*args, **kwargs)

    def isStorable(self):
        """シーンファイルへ値が保存されるアトリビュートか判定する。

        Returns:
            bool: 保存対象の場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).storable

    @_is_alias(isStorable)
    def storable(self, *args, **kwargs):
        """isStorableへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isStorable(*args, **kwargs)

    def hasMin(self):
        """最小値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最小値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMin()
        return False

    def hasMax(self):
        """最大値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最大値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasMax()
        return False

    def getMin(self):
        """設定されている最小値を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。
        誤った単位換算を避けるため、内部でのラジアン/センチメートル変換は行わない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最小値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
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

    def getMax(self):
        """設定されている最大値を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクト（``MAngle``/``MDistance``/``MTime``）をそのまま返す。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最大値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
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

    def hasSoftMin(self):
        """ソフト最小値（UIスライダーの下限）を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最小値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMin()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMin()
        return False

    def hasSoftMax(self):
        """ソフト最大値（UIスライダーの上限）を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最大値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr).hasSoftMax()
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr).hasSoftMax()
        return False

    def getSoftMin(self):
        """設定されているソフト最小値（UIスライダーの下限）を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最小値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
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

    def getSoftMax(self):
        """設定されているソフト最大値（UIスライダーの上限）を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最大値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
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

    def getDefault(self):
        """アトリビュートの既定値を取得する。

        数値アトリビュートは ``float``/``bool``、角度・距離・時間アトリビュートは対応する Maya API 2.0
        の単位付きオブジェクト、enum アトリビュートは ``int`` をそのまま返す。

        Returns:
            object | None: 既定値。対応しないアトリビュート型では ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
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

    @undoChunk("hlibPlugSetAlias")
    def setAlias(self, name=None):
        """別名を設定または解除する。

        Args:
            name (str | None): 別名。Noneまたは空文字で解除。
        Returns:
            Plug: 自身。
        """
        self._require_valid()
        if name:
            cmds.aliasAttr(name, self.getFullName())
        elif cmds.aliasAttr(self.getFullName(), query=True):
            cmds.aliasAttr(self.getFullName(), remove=True)
        return self

    @undoChunk("hlibPlugSetKey")
    def setKey(self, **kwargs):
        """対象アトリビュートへキーを設定する。

        Args:
            **kwargs: Maya setKeyframeのフラグ。値・時間はMayaのUI単位。
        Returns:
            Plug: 自身。
        """
        self._require_valid()
        cmds.setKeyframe(self.getFullName(), **kwargs)
        return self

    def getAnimLayers(self, selected=False, exact=False):
        """入力チェーンのアニメーションレイヤー名を上位から取得する。

        Args:
            selected (bool): 選択レイヤーに限定する。
            exact (bool): selected時にベースレイヤーも選択状態で絞る。
        Returns:
            list[str]: レイヤー名。最後に条件に合うベースレイヤーを含む。
        """
        self._require_valid()
        current = self
        visited = set()
        result = []
        while om2.MFnAttribute(current.mplug().attribute()).isProxyAttribute:
            name = current.getFullName()
            if name in visited:
                return []
            visited.add(name)
            current = current.getSource()
            if current is None:
                return []
        axis = current.getShortName()[-1].upper()
        visited.clear()
        while True:
            source = current.getSource()
            if source is None or source.getFullName() in visited:
                break
            visited.add(source.getFullName())
            node = source.getNode()
            kind = cmds.nodeType(str(node))
            if kind == "mute":
                current = node.getPlug("input")
                continue
            if kind == "pairBlend":
                suffix = source.getShortName()[-2:]
                mode = node.getPlug("rm" if suffix.startswith("r") else suffix + "m").get()
                driver = mode if mode in (1, 2) else node.getPlug("currentDriver").get()
                current = node.getPlug("i" + suffix + ("2" if driver == 2 else "1"))
                continue
            layers = cmds.listConnections(str(node) + ".message", s=False, d=True,
                                          type="animLayer") or []
            if not layers or not node.hasAttr("inputA"):
                break
            layer = layers[0]
            if layer not in result and (not selected or cmds.animLayer(layer, q=True, selected=True)):
                result.append(layer)
            suffix = axis if kind == "animBlendNodeAdditiveRotation" else ""
            current = node.getPlug("inputA" + suffix)
        base = cmds.animLayer(q=True, root=True)
        if base and base not in result and (not (selected and exact) or cmds.animLayer(base, q=True, selected=True)):
            result.append(base)
        return result

    def getEnumName(self):
        """enum アトリビュートの現在値に対応するフィールド名を取得する。

        Returns:
            str: 現在値に対応するフィールド名。

        Raises:
            TypeError: enum アトリビュートでない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enumName は enum アトリビュートにのみ使用できます")
        return om2.MFnEnumAttribute(attr).fieldName(int(self.get()))

    @undoChunk("hlibPlugSetEnumNames")
    def setEnumNames(self, names):
        """enumアトリビュートの表示名を指定順に更新する。

        Args:
            names (Iterable[str]): 値0から順に対応する空でない名前列。

        Returns:
            Plug: 更新した自身。

        Raises:
            TypeError: enumアトリビュートでない、または名前が文字列でない場合。
            ValueError: 空の列、空の名前、区切り文字を含む名前の場合。
            RuntimeError: アトリビュートが無効、またはMayaが変更を拒否した場合。
        """
        self._require_valid()
        if not self._mplug.attribute().hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("setEnumNames requires an enum attribute")
        if isinstance(names, str):
            raise TypeError("names must be a sequence of strings")
        names = list(names)
        if any(not isinstance(name, str) for name in names):
            raise TypeError("enum names must be strings")
        if not names or any(not name or ":" in name or "=" in name for name in names):
            raise ValueError("enum names must be non-empty and contain no ':' or '='")
        cmds.addAttr(self.getFullName(), edit=True, enumName=":".join(names))
        return self

    def getEnumValue(self, name):
        """enum アトリビュートのフィールド名に対応する値を取得する(enumName の逆引き)。

        Args:
            name (str): 検索するフィールド名。

        Returns:
            int: name に対応する enum 値。

        Raises:
            TypeError: enum アトリビュートでない場合。
            ValueError: name に一致するフィールドが無い場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if not attr.hasFn(om2.MFn.kEnumAttribute):
            raise TypeError("enumValue は enum アトリビュートにのみ使用できます")
        enum_fn = om2.MFnEnumAttribute(attr)
        for value in range(enum_fn.getMin(), enum_fn.getMax() + 1):
            try:
                if enum_fn.fieldName(value) == name:
                    return value
            except RuntimeError:
                continue
        raise ValueError(f"No enum field named {name!r}")

    def isLocked(self):
        """プラグがロックされているか判定する。

        Returns:
            bool: ロックされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return self._mplug.isLocked

    @_is_alias(isLocked)
    def locked(self, *args, **kwargs):
        """isLockedへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isLocked(*args, **kwargs)

    @undoChunk("hlibPlugSetLocked")
    def setLocked(self, val=True, leaf=False):
        """ロックを設定する。

        Args:
            val (bool): ロック状態。
            leaf (bool): コンパウンドでは末端だけを設定する。
        Returns:
            Plug: 自身。
        """
        return self._set_flags(leaf, locked=val)

    lock = setLocked

    def isMuted(self):
        """アトリビュートがミュートされているか判定する。

        Returns:
            bool: ミュートされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return bool(cmds.mute(self.getFullName(), query=True))

    @_is_alias(isMuted)
    def muted(self, *args, **kwargs):
        """isMutedへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isMuted(*args, **kwargs)

    @undoChunk("hlibPlugSetMuted")
    def setMuted(self, state):
        """ミュート状態を設定する。Trueは現在値で固定し、Falseは解除する。

        Args:
            state (bool): ミュートする場合はTrue。

        Returns:
            Plug: 自身。

        Raises:
            RuntimeError: Maya がミュートを拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        if state:
            cmds.mute(self.getFullName())
        else:
            cmds.mute(self.getFullName(), disable=True, force=True)
        return self

    @flag_aliases(f="force")
    @undoChunk("hlibPlugDeleteAttr")
    def delete(self, force=False):
        """このアトリビュートをノードから削除する。

        動的に追加されたアトリビュート（addAttr によるカスタムアトリビュート）にのみ使用できる。
        静的（ノード型に組み込み）のアトリビュートを削除しようとすると Maya が拒否する。
        接続がある場合は force に関わらず Maya が自動的に切断してから削除する。

        Args:
            force (bool): True の場合、ロックされていれば一時的に解除してから
                削除する。False でロックされているアトリビュートを削除しようとすると
                RuntimeError になる。 別名 ``f`` も使用可能。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: force=False でロックされている場合や、静的アトリビュートの
                削除を試みた場合など、Maya が削除を拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        if force and self.isLocked():
            set_attr(self.getFullName(), lock=False)
        cmds.deleteAttr(self.getFullName())

    def get(self):
        """評価済みの Maya アトリビュート値を取得する。

        bool/int/float 系の数値アトリビュート、角度・距離・時間の単位アトリビュート、enum、
        文字列および対応する型付き配列は Maya API 2.0経由で直接読み取り、MEL コマンドの
        往復を避ける。角度はrad、距離はcm、時間は秒で返す。message アトリビュートや mesh/カーブ等の
        複雑な typed data アトリビュートのように対応する読み取り方法が無いものは
        ``cmds.getAttr`` にフォールバックする。

        Returns:
            object: アトリビュート値。1要素のリストにタプルが入っている場合のみ、
                そのタプルを返す（cmds.getAttr フォールバック時のみ該当）。
                文字列、数値、配列、None など実際のアトリビュート型に依存する。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合
                (:meth:`isValid` が ``False``。削除前の古い値は返さない)。
                Maya 内部のデータ型(nurbsSurface の ``patchUVIds`` など)の、存在しない
                配列要素の場合(値を読むと Maya が異常終了する場合があるため。
                :func:`hlib._core.attributeType.is_internal_data_type`)。
        """
        self._require_valid()
        reader = self._reader
        if reader is None:
            # アトリビュートの型は変わらないため、読み方は Plug ごとに一度だけ選ぶ。
            reader = self._reader = value_reader(self._attribute)
        if reader is not False:
            return reader(self._mplug)

        if is_internal_data_type(self._mplug) and not _plug_exists(self._mplug):
            raise RuntimeError(
                f"Maya 内部のデータ型の存在しない要素の値は読めません: {self.getFullName()}"
            )
        value = cmds.getAttr(self.getFullName())
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    @fast_edit
    @undoChunk("hlibPlugSet")
    @safe_edit
    def set(self, value, safe=False, *, fast=False):
        """プラグ値を変更する。

        doubleArray/floatArray/Int32Array/Int64Array のようなスカラー配列型と、
        stringArray/vectorArray/floatVectorArray/pointArray/matrixArray/
        componentList のような長さ指定が必要な配列型は、``cmds.setAttr`` が
        要求する引数の形(単純な ``*value`` 展開ではなく、型名や要素数の
        明示)が数値コンパウンド(double3 等)や matrix と異なるため、
        アトリビュート定義から ``cmds.getAttr(..., type=True)`` と同じアトリビュート型名を求めてから
        (:func:`hlib._core.attributeType.attributeType`)対応する形で呼び出す。
        それ以外の型(数値コンパウンド、matrix 等)は従来通り ``*value`` で展開する。

        Args:
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (object): 設定する値。距離cm、角度rad、時間秒。

        Returns:
            Plug | int: 自身。safe=Trueでは失敗した成分数。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self._require_valid()
        if is_fast():
            set_plug(self._mplug, value)
            return self
        value = convert(self._mplug, value)
        if isinstance(value, str):
            set_attr(self.getFullName(), value, type="string")
            return self
        if isinstance(value, (tuple, list)):
            attr_type = attributeType(self._mplug)
            if attr_type in _SCALAR_ARRAY_TYPES:
                set_attr(self.getFullName(), value, type=attr_type)
            elif attr_type in _LENGTH_PREFIXED_ARRAY_TYPES:
                set_attr(self.getFullName(), len(value), *value, type=attr_type)
            else:
                set_attr(self.getFullName(), *value)
            return self
        set_attr(self.getFullName(), value)
        return self

    def getu(self):
        """UI単位で値を取得する。角度・距離・時間は現在のシーン設定に従う。

        Returns:
            object: UI単位の値。複合値はtuple、配列はインデックス別dict。
        """
        if self.isArray():
            return {p.mplug().logicalIndex(): p.getu() for p in self.getElements()}
        return convert(self.mplug(), self.get())

    @fast_edit
    @undoChunk("hlibPlugSetUi")
    @safe_edit
    def setu(self, value, safe=False, *, fast=False):
        """UI単位の値を設定する。

        Args:
            value (object): 現在のシーン単位の値。
            safe (bool): 失敗を抑制し失敗した成分数を返す。
            fast (bool): Undoなしの直接更新。
        Returns:
            Plug | int: 自身。safe=Trueでは失敗数。
        """
        return self.set(convert(self.mplug(), value, to_ui=False), safe=safe)

    @undoChunk("hlibPlugSetIfChanged")
    def setIfChanged(self, value, *, unlock=False):
        """スカラー値が変わる場合だけ更新し、不要なアトリビュート通知を避ける。

        Args:
            value (bool | int | float | str): 比較・設定する値。数値は厳密比較。
            unlock (bool): ロックを一時解除する。失敗時も元のロックへ戻す。

        Returns:
            bool: 値を更新した場合はTrue。

        Raises:
            TypeError: スカラー以外を指定した場合。
            RuntimeError: Mayaがアトリビュート更新を拒否した場合。
        """
        if not isinstance(value, (bool, int, float, str)):
            raise TypeError("setIfChanged supports scalar values only")
        if self.get() == value:
            return False
        locked = self.isLocked()
        if unlock and locked:
            self.setFlags(locked=False)
        try:
            self.set(value)
        finally:
            if unlock and locked:
                self.setFlags(locked=True)
        return True

    @fast_edit
    @undoChunk("hlibPlugReset")
    def reset(self, *, fast=False):
        """数値・単位・enumアトリビュートを定義上の既定値へ戻す。

        単位アトリビュートは内部単位で扱う。複合アトリビュートは子ごとに処理する。
        接続の切断やロック解除はしない。失敗前の変更は自動では戻さない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Plug: 自身。一回のUndoで全変更を戻せる。

        Raises:
            TypeError: 配列全体・文字列・messageなど既定値を扱えないアトリビュートの場合。
            RuntimeError: ロック・入力接続などで変更できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if self.isArray():
            raise TypeError("Reset an array element instead of the array plug")
        self._require_valid()
        if self._mplug.isCompound:
            for index in range(self._mplug.numChildren()):
                Plug(self._node, self._mplug.child(index)).reset()
            return self
        value = self.getDefault()
        if value is None:
            raise TypeError(f"No supported default value for {self.getFullName()}")
        if isinstance(value, om2.MAngle):
            value = value.asRadians()
        elif isinstance(value, om2.MDistance):
            value = value.asCentimeters()
        elif isinstance(value, om2.MTime):
            value = value.asUnits(om2.MTime.kSeconds)
        self.set(value)
        return self

    def getEnumFieldName(self, val):
        """指定値のenumフィールド名を返す。

        Args:
            val (int): enum値。
        Returns:
            str: フィールド名。
        """
        self._require_valid()
        return om2.MFnEnumAttribute(self.mplug().attribute()).fieldName(val)

    def getSource(self, **kwargs):
        """unitConversionを飛ばして入力元を返す。

        Args:
            **kwargs: connectionsの絞り込み指定。
        Returns:
            Plug | Node | None: 入力元。未接続ならNone。
        """
        kwargs.update(skipConversionNodes=True, checkChildren=False,
                      checkElements=False, index=0)
        return self.getConnections(True, False, **kwargs)

    def getDestinations(self, **kwargs):
        """unitConversionを飛ばして出力先を返す。

        Args:
            **kwargs: connectionsの絞り込み指定。
        Returns:
            list: 出力先。
        """
        kwargs.update(skipConversionNodes=True, checkChildren=False, checkElements=False)
        return self.getConnections(False, True, **kwargs)

    def getInputs(self, **kwargs):
        """入力側の接続を指定条件で照会する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。方向のs/dは指定しない。

        Returns:
            list | Plug | Node | tuple | None: 通常はリスト。index指定時は一件、範囲外はNone。
        """
        return self.getConnections(True, False, **kwargs)

    def getOutputs(self, **kwargs):
        """出力側の接続を指定条件で照会する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。方向のs/dは指定しない。

        Returns:
            list | Plug | Node | tuple | None: 通常はリスト。index指定時は一件、範囲外はNone。
        """
        return self.getConnections(False, True, **kwargs)

    @flag_aliases(idx="index", src="source", dst="destination")
    def getConnections(self, s=True, d=True, c=False, t=None, et=False, scn=False,
                    source=True, destination=True, connections=False,
                    type=None, exactType=False, skipConversionNodes=False,
                    asPair=False, asNode=False, checkChildren=True,
                    checkElements=True, index=None, pcls=None):
        """接続先をPlug・Node・Plugペアとして照会する。

        Args:
            s (bool): 入力方向。sourceとANDする。
            d (bool): 出力方向。destinationとANDする。
            c (bool): asPairの短縮指定。
            t (str | None): typeの短縮指定。
            et (bool): exactTypeの短縮指定。
            scn (bool): skipConversionNodesの短縮指定。
            source (bool): 入力を含める。別名 ``src`` も使用可能。sとANDする。
            destination (bool): 出力を含める。別名 ``dst`` も使用可能。dとANDする。
            connections (bool): ペアを返す。
            type (str | None): 相手のノード型。
            exactType (bool): 派生型を含めない。
            skipConversionNodes (bool): unitConversion系を飛ばす。
            asPair (bool): 自身側Plugと接続先のペアを返す。
            asNode (bool): 接続先をNodeで返す。
            checkChildren (bool): 子アトリビュートも調べる。
            checkElements (bool): 配列要素も調べる。
            index (int | None): 結果の一件を指定する。範囲外はNone。 別名 ``idx`` も使用可能。
            pcls (type | None): 結果のPlugクラス。
        Returns:
            list | Plug | Node | tuple | None: 条件に合う結果。
        Raises:
            TypeError: source/srcまたはdestination/dstを重複指定した場合。
        """
        self._require_valid()
        pairs = []
        def visit(plug):
            """対象階層から直接または変換を飛ばした接続を集める。"""
            mp = plug.mplug()
            for incoming, enabled in ((True, s and source), (False, d and destination)):
                if not enabled:
                    continue
                if scn or skipConversionNodes:
                    if incoming:
                        src = mp.source()
                        targets = [] if src.isNull else [src]
                    else:
                        targets = mp.destinations()
                else:
                    targets = mp.connectedTo(incoming, not incoming)
                pairs.extend((plug, Plug(self._node_from_mplug(p), p)) for p in targets)
            if mp.isArray and checkElements:
                for element in plug.getElements():
                    visit(element)
            elif mp.isCompound and checkChildren:
                for child in plug.getChildren():
                    visit(child)
        visit(self)
        return self._connection_results(pairs, type or t, exactType or et,
                                        asPair or c or connections, asNode, index, pcls)

    def getSourceWithConversion(self, **kwargs):
        """変換ノードを省略せず、直接の入力接続元を取得する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。
                checkChildren/checkElementsはFalse、indexは0に固定する。
                scn等を明示した場合はconnections側の指定に従う。

        Returns:
            Plug | Node | tuple | None: 既定は接続元Plug。未接続はNone。
                asNode/asPairで返却形式が変わる。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        self._require_valid()
        if kwargs:
            kwargs.update(checkChildren=False, checkElements=False, index=0)
            return self.getConnections(True, False, **kwargs)
        sources = self._mplug.connectedTo(True, False)
        return Plug(self._node_from_mplug(sources[0]), sources[0]) if sources else None

    def getAnimCurve(self):
        """このプラグに直接接続された animCurve ノードを取得する。

        pairBlend やアニメーションレイヤーを介した間接的な animCurve は解決しない
        （直接の入力接続だけを対象とする）。

        Returns:
            Node | None: 接続されている animCurve ノード。無ければ ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        sources = self._mplug.connectedTo(True, False)
        if not sources:
            return None
        source_mobject = sources[0].node()
        if not source_mobject.hasFn(om2.MFn.kAnimCurve):
            return None
        return self._node_from_mplug(sources[0])

    def getDestinationsWithConversions(self, **kwargs):
        """変換ノードを省略せず、直接の出力接続先を取得する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。
                checkChildren/checkElementsはFalseに固定する。
                scn等を明示した場合はconnections側の指定に従う。

        Returns:
            list | Plug | Node | tuple | None: 既定は接続先Plugのリスト。未接続は空リスト。
                asNode/asPair/indexで返却形式が変わる。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        self._require_valid()
        if kwargs:
            kwargs.update(checkChildren=False, checkElements=False)
            return self.getConnections(False, True, **kwargs)
        return [Plug(self._node_from_mplug(plug), plug) for plug in self._mplug.connectedTo(False, True)]

    @flag_aliases(source="src", destination="dst")
    def isConnectedTo(self, other, *, src=True, dst=True):
        """指定したプラグと接続されているか判定する。

        既定では入力・出力いずれの向きでも一致すれば True を返す。
        子・配列要素の独立した接続や変換ノードの先の接続は展開しない。

        Args:
            other (Plug | om2.MPlug | str): 判定対象のプラグ。文字列は
                ``"node.attribute"`` 形式のアトリビュート名。
            src (bool): otherから自身への入力接続を調べる。別名 ``source`` も使用可能。
            dst (bool): 自身からotherへの出力接続を調べる。別名 ``destination`` も使用可能。

        Returns:
            bool: 指定方向で接続されている場合は True。両Falseなら False。

        Raises:
            TypeError: other が Plug・MPlug・アトリビュート名のいずれでもない場合、または文字列が
                アトリビュートを指していない場合。方向指定がboolでない、または別名と重複した場合。
            ValueError: other が空文字列、または空の MPlug の場合。
            RuntimeError: 自身の所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
                other の文字列を解決できない(存在しない、または複数のアトリビュートに一致する)場合、
                other のPlugまたはMPlugの所有ノード・アトリビュートが削除済みの場合。
        """
        self._require_valid()
        self._validate_connection_directions(src, dst)
        other = Plug._resolve_input(other)
        other._require_valid()
        return any(
            connected == other.mplug()
            for connected in self._mplug.connectedTo(src, dst)
        )

    @_is_alias(isConnectedTo)
    def connectedTo(self, *args, **kwargs):
        """isConnectedToへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isConnectedTo(*args, **kwargs)

    @flag_aliases(source="src")
    @undoChunk("hlibPlugConnect")
    def connect(self, src, force=False, f=False, lock=False, l=False,
                nextAvailable=False, na=False, *, unlock=True):
        """srcから自身へ接続する。接続先のPlugから呼び出す。

        Args:
            src (Plug | om2.MPlug | str): 接続元。 別名 ``source`` も使用可能。
            force (bool): 既存接続を置換し、一時アンロックする。
            f (bool): forceの短縮名。長名とORする。
            lock (bool): 接続後に接続先をロックする。
            l (bool): lockの短縮名。
            nextAvailable (bool): 配列の接続可能な空き要素を使う。
            na (bool): nextAvailableの短縮名。
            unlock (bool): Falseならforceでもロックを解除しない。
        Returns:
            Plug: 実際に接続した接続先。
        """
        self._require_valid()
        src = Plug._resolve_input(src)
        force, lock = force or f, lock or l
        if self.isLocked() and not (force and unlock):
            raise RuntimeError("Attribute is locked: " + self.getFullName())
        # 配列親を先に解除する。親がロックされたまま空き番号を探すと
        # 全要素がロック扱いになり、探索が終わらなくなる。
        unlocked = self._unlock_connection_path() if force and unlock else []
        target = self
        try:
            if self.isArray() and (nextAvailable or na):
                def occupied(plug):
                    """自身または子に入力接続・ロックがある要素を避ける。"""
                    if plug.isLocked() or plug.getSourceWithConversion() is not None:
                        return True
                    return plug.mplug().isCompound and any(occupied(p) for p in plug.getChildren())
                index = 0
                while True:
                    candidate = Plug(self.getNode(), self.mplug().elementByLogicalIndex(index))
                    if not occupied(candidate):
                        target = candidate
                        break
                    index += 1
            current = target.getSourceWithConversion()
            if current is not None and current.getFullName() == src.getFullName():
                raise RuntimeError("Already connected: " + src.getFullName() + " -> " + target.getFullName())
            target_name = target.getFullName()
            keep_self = target is self and not self.mplug().isNetworked
            cmds.connectAttr(src.getFullName(), target_name, force=force)
            if lock:
                cmds.setAttr(target_name, lock=True)
        finally:
            for plug in reversed(unlocked):
                plug.setFlags(locked=True)
        return self if keep_self else Plug._resolve_input(target_name)

    @undoChunk("hlibPlugDisconnectInput")
    def disconnectInput(self):
        """直接の入力だけを解除する。未接続なら何もせず自身を返す。"""
        source = self.getSourceWithConversion()
        if source is not None:
            self.disconnect(source)
        return self

    @flag_aliases(source="src", destination="dst")
    @undoChunk("hlibPlugDisconnect")
    def disconnect(self, src=None, force=False, f=False, nextAvailable=False, na=False,
                   *, dst=False):
        """入力元の指定またはブール方向指定で直接の接続を切断する。

        ``src=True`` は入力、``dst=True`` は出力を対象とする。
        出力だけなら ``src=False, dst=True``、両方向なら両方をTrueにする。
        ブール方向指定は未接続でも何もせず空リストを返す。
        子や配列要素の独立した接続は展開せず、変換ノードも削除しない。
        従来の ``disconnect()`` と入力元Plug指定は入力だけを切断する。

        Args:
            src (Plug | om2.MPlug | str | bool | None): 入力元または入力を切断するか。
                Noneは現在の入力。別名 ``source`` も使用可能。
            force (bool): 接続先のロックを一時解除する。
            f (bool): forceの短縮名。
            nextAvailable (bool): 入力元Plugを指定したとき、配列内でsrcに接続している
                要素を全て切断する。
            na (bool): nextAvailableの短縮名。
            dst (bool): 全ての直接の出力を切断する。キーワード専用。
                別名 ``destination`` も使用可能。
        Returns:
            Plug | list[Plug]: 従来の入力切断は入力元Plug、配列検索は接続先リスト。
                srcがboolまたはdst=Trueなら、切断した入力元と出力接続先のリスト。
                入力元Plugを指定した配列検索とdst=Trueの併用時は、従来の入力接続先
                リストに出力接続先を追加する。
        Raises:
            TypeError: dstがboolでない場合。
            RuntimeError: 従来の入力切断で接続がない場合、指定入力が未接続の場合、
                または接続先のロック等により切断できない場合。
        """
        self._require_valid()
        if not isinstance(dst, bool):
            raise TypeError("dst must be bool")
        if isinstance(src, bool) or dst:
            # 接続の編集後にネットワークMPlugを参照し続けないよう、名前を先に確保する。
            self_name = self.getFullName()
            destination_names = [plug.getFullName() for plug in
                                 self.getDestinationsWithConversions()] if dst else []
            results = []
            if not isinstance(src, bool) or src:
                source = self.getSourceWithConversion() if src is None or isinstance(src, bool) else src
                if source is not None:
                    search_array = src is not None and not isinstance(src, bool)
                    result = self.disconnect(source, force=force, f=f,
                                             nextAvailable=nextAvailable and search_array,
                                             na=na and search_array)
                    results.extend(result if isinstance(result, list) else [result])
            for name in destination_names:
                destination = Plug._resolve_input(name)
                destination.disconnect(self_name, force=force, f=f)
                results.append(Plug._resolve_input(name))
            return results
        if src is not None:
            src = Plug._resolve_input(src)
        if self.isArray() and (nextAvailable or na) and src is not None:
            targets = [p for p in self.getElements() if p.getSourceWithConversion() == src]
            if not targets:
                raise RuntimeError("Input connection not found: " + self.getFullName())
            names = [target.getFullName() for target in targets]
            for target in targets:
                target.disconnect(src, force=force or f)
            return [Plug._resolve_input(name) for name in names]
        if src is None:
            src = self.getSourceWithConversion()
        if src is None:
            raise RuntimeError("Input connection not found: " + self.getFullName())
        source_name = src.getFullName()
        unlocked = self._unlock_connection_path() if force or f else []
        try:
            cmds.disconnectAttr(src.getFullName(), self.getFullName())
        finally:
            for plug in reversed(unlocked):
                plug.setFlags(locked=True)
        return Plug._resolve_input(source_name)

    @flag_aliases(source="src", destination="dst")
    @undoChunk("hlibPlugDisconnectAll")
    def disconnectAll(self, *, src=True, dst=True):
        """指定方向の直接接続を全て切断し、自身を返す。

        子・配列要素の独立した接続は展開せず、変換ノードも削除しない。
        複数切断は1回のUndo/Redoで戻す。

        Args:
            src (bool): 入力接続を切断する。別名 ``source`` も使用可能。
            dst (bool): 全出力を切断する。別名 ``destination`` も使用可能。

        Returns:
            Plug: 自身。未接続または両Falseなら何も変更しない。

        Raises:
            TypeError: 方向指定がboolでない場合、または別名と重複指定した場合。
            RuntimeError: 無効なPlug、またはロック等により切断できない場合。
        """
        self._require_valid()
        self._validate_connection_directions(src, dst)
        if src:
            self.disconnectInput()
        if dst:
            for destination in self.getDestinationsWithConversions():
                destination.disconnect(self)
        return self

    @flag_aliases(destination="dst")
    def connectTo(self, dst, **kwargs):
        """自身からdstへ接続し、接続先Plugを返す。

        Args:
            dst (Plug | om2.MPlug | str): 接続先。 別名 ``destination`` も使用可能。
            **kwargs: connectのforce/f・lock/l・nextAvailable/na・unlock。
        Returns:
            Plug: 実際の接続先。
        """
        return Plug._resolve_input(dst).connect(self, **kwargs)

    @_getter_alias(getNode)
    def node(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNode(*args, **kwargs)

    @_getter_alias(getName)
    def name(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getName(*args, **kwargs)

    @_getter_alias(getAttrName)
    def attrName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAttrName(*args, **kwargs)

    @_getter_alias(getShortName)
    def shortName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShortName(*args, **kwargs)

    @_getter_alias(getPlugName)
    def plugName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlugName(*args, **kwargs)

    @_getter_alias(getFullName)
    def fullName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFullName(*args, **kwargs)

    @_getter_alias(getLongName)
    def longName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getLongName(*args, **kwargs)

    @_getter_alias(getNiceName)
    def niceName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNiceName(*args, **kwargs)

    @_getter_alias(getType)
    def type(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getType(*args, **kwargs)

    @_getter_alias(getDataType)
    def dataType(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDataType(*args, **kwargs)

    @_getter_alias(getParent)
    def parent(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParent(*args, **kwargs)

    @_getter_alias(getNextAvailable)
    def nextAvailable(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNextAvailable(*args, **kwargs)

    @_getter_alias(getMin)
    def min(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMin(*args, **kwargs)

    @_getter_alias(getMax)
    def max(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMax(*args, **kwargs)

    @_getter_alias(getSoftMin)
    def softMin(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSoftMin(*args, **kwargs)

    @_getter_alias(getSoftMax)
    def softMax(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSoftMax(*args, **kwargs)

    @_getter_alias(getDefault)
    def default(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDefault(*args, **kwargs)

    @_getter_alias(getAnimLayers)
    def animLayers(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAnimLayers(*args, **kwargs)

    @_getter_alias(getEnumName)
    def enumName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getEnumName(*args, **kwargs)

    @_getter_alias(getEnumValue)
    def enumValue(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getEnumValue(*args, **kwargs)

    @_getter_alias(getEnumFieldName)
    def enumFieldName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getEnumFieldName(*args, **kwargs)

    @_getter_alias(getSource)
    def source(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSource(*args, **kwargs)

    @_getter_alias(getDestinations)
    def destinations(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDestinations(*args, **kwargs)

    @_getter_alias(getInputs)
    def inputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputs(*args, **kwargs)

    @_getter_alias(getOutputs)
    def outputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputs(*args, **kwargs)

    @_getter_alias(getConnections)
    def connections(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getConnections(*args, **kwargs)

    @_getter_alias(getSourceWithConversion)
    def sourceWithConversion(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSourceWithConversion(*args, **kwargs)

    @_getter_alias(getAnimCurve)
    def animCurve(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAnimCurve(*args, **kwargs)

    @_getter_alias(getDestinationsWithConversions)
    def destinationsWithConversions(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDestinationsWithConversions(*args, **kwargs)

    def _set_flags(self, leaf, **flags):
        """指定階層の末端または自身へフラグを適用する。

        Args:
            leaf: 複合アトリビュートの末端へ適用するか。
            **flags: 呼出し先へ渡すキーワード引数。
        """
        if leaf and self.isCompound():
            for child in self.getChildren():
                child._set_flags(True, **flags)
        else:
            # Mayaのkeyable/channelBoxのUndo順序を保つ。
            if flags.get("keyable") and self.isChannelBox():
                self.setFlags(channelBox=False)
            if flags.get("channelBox"):
                flags["keyable"] = False
            self.setFlags(**flags)
        return self

    @staticmethod
    def _validate_connection_directions(src, dst):
        """接続方向のbool指定をシーンの編集前に検証する。

        Args:
            src (bool): 入力方向の指定。
            dst (bool): 出力方向の指定。

        Raises:
            TypeError: どちらかがboolでない場合。
        """
        if not isinstance(src, bool):
            raise TypeError("src must be bool")
        if not isinstance(dst, bool):
            raise TypeError("dst must be bool")

    @staticmethod
    def _connection_results(pairs, node_type, exact, as_pair, as_node, index, pcls):
        """Node/Plug共通の接続フィルタと戻り値変換。

        Args:
            pairs: 接続の両端を組にした列。
            node_type: 絞り込みまたは作成に使うMayaノード型。
            exact: 型や対象を完全一致で絞り込むか。
            as_pair: Trueは接続の両端を組として返す。
            as_node: Trueは接続先をノードとして返す。
            index: 対象要素の番号または探索開始番号。
            pcls: 結果に使うPlugクラス。
        """
        result, seen = [], set()
        for local, remote in pairs:
            node = remote.getNode()
            if node_type and not (node.type() == node_type if exact else node.isType(node_type)):
                continue
            key = (local.getFullName() if as_pair else None,
                   node.getFullName() if as_node else remote.getFullName())
            if key in seen:
                continue
            seen.add(key)
            target = node if as_node else pcls(remote.getNode(), remote.mplug()) if pcls else remote
            result.append((pcls(local.getNode(), local.mplug()) if pcls else local, target) if as_pair else target)
        if index is not None:
            try:
                return result[index]
            except IndexError:
                return None
        return result

    def _unlock_connection_path(self):
        """自身と上位のロックを一時解除し、復元対象を返す。"""
        chain, plug = [], self.mplug()
        while True:
            chain.append(Plug(self.getNode(), plug))
            if plug.isChild:
                plug = plug.parent()
            elif plug.isElement:
                plug = plug.array()
            else:
                break
        unlocked = []
        try:
            for item in reversed(chain):
                if item.isLocked():
                    item.setFlags(locked=False)
                    unlocked.append(item)
        except Exception:
            for item in reversed(unlocked):
                item.setFlags(locked=True)
            raise
        return unlocked

    @staticmethod
    def _plug_path(mplug):
        """ノード名を除いた、maya.cmds で解決できるアトリビュートパスを返す。

        ロング名と、必要な配列インデックス(``worldMatrix[0]``、``pnts[2].pntx`` 等)・
        インスタンス番号を含み、エイリアスがあればエイリアス名を使う
        (``MPlug.name()`` のアトリビュート部分と同じ表記)。

        Args:
            mplug (om2.MPlug): 対象のプラグ。

        Returns:
            str: ``translateX`` や ``worldMatrix[0]`` のようなアトリビュートパス。
        """
        # 名前付き引数より位置引数の方が呼び出しが速いため、位置で渡す。順に
        # includeNodeName, includeNonMandatoryIndices, includeInstancedIndices,
        # useAlias, useFullAttributePath, useLongNames。
        return mplug.partialName(False, True, True, True, False, True)

    @staticmethod
    def _mplug_attribute_exists(mplug, node=None):
        """MPlug のアトリビュートが所有ノードに存在するか判定する(所有ノードは有効であること)。

        ``deleteAttr`` で削除された動的アトリビュートの MPlug は、Undo のためにアトリビュートの MObject が保持された
        ままの場合があり ``MObjectHandle.isValid()`` だけでは判定できないため、所有ノードの
        ``MFnDependencyNode.attributeClass()`` で確かめる(ノードに無いアトリビュートは ``kInvalidAttr``)。

        Args:
            mplug (om2.MPlug): 判定するプラグ。
            node (om2.MObject | None): 所有ノード。分かっている場合に指定する。

        Returns:
            bool: アトリビュートが存在する場合は True。
        """
        attribute = mplug.attribute()
        if attribute.isNull() or not om2.MObjectHandle(attribute).isValid():
            return False
        if node is None:
            node = mplug.node()
        kind = om2.MFnDependencyNode(node).attributeClass(attribute)
        return kind != om2.MFnDependencyNode.kInvalidAttr

    @staticmethod
    def _mplug_name(mplug):
        """MPlug を ``Plug.getFullName()`` と同じ形式の一意なプラグ名へ変換する。

        所有ノードが Undo の対象から外れて削除された(``flushUndo`` 後・Undo 無効・シーンの
        切り替え)MPlug は、``MPlug.node()`` の時点で Maya が異常終了し、API では検出できない。
        MPlug を削除操作をまたいで保持せず、hlib の Plug を保持すること(:doc:`/cmds_interop`)。

        Args:
            mplug (om2.MPlug): 変換対象。

        Returns:
            str: ``<ノードの最短一意名>.<アトリビュートパス>``。

        Raises:
            ValueError: 空の MPlug、所有ノードが削除済み、またはアトリビュートが削除済み(``deleteAttr``)の場合。
        """
        from ..nodes.node import Node as _InputNode
        if mplug.isNull:
            raise ValueError("空の MPlug は指定できません")
        node = mplug.node()
        if not om2.MObjectHandle(node).isValid():
            raise ValueError("削除済みノードの MPlug は指定できません")
        if not Plug._mplug_attribute_exists(mplug, node):
            raise ValueError("削除済みのアトリビュートの MPlug は指定できません")
        return _InputNode._unique_node_name(node) + "." + Plug._plug_path(mplug)

    @staticmethod
    def _deleted_attribute_error(plug):
        """所有ノードが有効なままアトリビュートが削除された Plug の例外を返す(該当しなければ None)。

        Args:
            plug (Plug): 判定する hlib の Plug。

        Returns:
            DeletedAttributeError | None: アトリビュートが ``deleteAttr`` で削除済みなら送出する例外。
                所有ノードが削除済みの場合(無効な所有ノードとして扱う)と、有効な Plug は None。
        """
        if plug.getNode().isValid() and not plug.isValid():
            return DeletedAttributeError("削除済みのアトリビュートの Plug からノードは解決できません")
        return None

    @staticmethod
    def _find_plug(mobject, name):
        """ノードのアトリビュート名(ロング名・ショート名・エイリアス)から MPlug を求める。

        ``MFnDependencyNode.findPlug()`` はエイリアスを解決しないため、見つからない場合は
        エイリアスの一覧(``bs.smile`` → ``weight[0]`` など)からアトリビュートパスを求めて解決する。

        Args:
            mobject (om2.MObject): 所有ノード。
            name (str): アトリビュート名。

        Returns:
            om2.MPlug | None: プラグ。アトリビュートが無い場合は None。
        """
        fn = om2.MFnDependencyNode(mobject)
        try:
            return fn.findPlug(name, False)
        except RuntimeError:
            pass
        for alias, attribute_path in fn.getAliasList():
            if alias == name:
                return Plug._attribute_path_plug(mobject, attribute_path)
        return None

    @staticmethod
    def _has_out_of_range_index(attribute_path):
        """アトリビュートパスが :data:`MAX_LOGICAL_INDEX` を超える配列インデックスを含むか判定する。

        Args:
            attribute_path (str): ノード名を含まないアトリビュートパス(``input1D[4294967296]`` など)。

        Returns:
            bool: 範囲外のインデックスを含む場合は True。
        """
        return any(int(index) > MAX_LOGICAL_INDEX for index in _PLUG_PATH_INDEX.findall(attribute_path))

    @staticmethod
    def _has_unresolved_index(mplug):
        """論理インデックスが未確定(-1)の配列要素を経由するプラグか判定する。

        ``findPlug("input3Dx")`` のように配列複合アトリビュートの子を要素を指定せずに取得すると
        ``input3D[-1].input3Dx`` のようなプラグになり、maya.cmds では解決できない。

        Args:
            mplug (om2.MPlug): 判定するプラグ。

        Returns:
            bool: 未確定のインデックスを含む場合は True。
        """
        current = mplug
        while True:
            if current.isElement:
                if current.logicalIndex() < 0:
                    return True
                current = current.array()
            elif current.isChild:
                current = current.parent()
            else:
                return False

    @staticmethod
    def _attribute_path_plug(mobject, attribute_path, first=None):
        """ノードとアトリビュートパス(``input1D[3]``、``pnts[2].pntx`` など)から MPlug を求める。

        ``.`` で区切った各区切りのアトリビュート名(ロング名・ショート名。先頭はエイリアスも可)と
        ``[i]`` の論理インデックスを順に辿る。存在しない配列要素もプラグとして返し、
        要素は作らない(シーンを変更しない)。

        Args:
            mobject (om2.MObject): 所有ノード。
            attribute_path (str): ノード名を含まないアトリビュートパス。
            first (om2.MPlug | None): 先頭の区切りのアトリビュート名に対応するプラグが既に分かっている
                場合に指定する(transform からシェイプへ伸ばして探した場合など)。

        Returns:
            om2.MPlug | None: プラグ。アトリビュートとして解決できない場合(存在しないアトリビュート、範囲指定、
                配列でないアトリビュートへのインデックス、:data:`MAX_LOGICAL_INDEX` を超えるインデックス、
                配列要素の番号を指定しない子アトリビュートなど)は None。
        """
        mplug = None
        for token in attribute_path.split("."):
            match = _PLUG_PATH_TOKEN.match(token)
            if match is None:
                return None
            name, indices = match.groups()
            if mplug is None:
                mplug = first if first is not None else Plug._find_plug(mobject, name)
                if mplug is None:
                    return None
            else:
                if mplug.isArray or not mplug.isCompound:
                    return None
                for child_index in range(mplug.numChildren()):
                    child = mplug.child(child_index)
                    attribute = om2.MFnAttribute(child.attribute())
                    if name in (attribute.name, attribute.shortName):
                        mplug = child
                        break
                else:
                    return None
            for index in _PLUG_PATH_INDEX.findall(indices):
                index = int(index)
                if not mplug.isArray or index > MAX_LOGICAL_INDEX:
                    # 範囲外の番号は elementByLogicalIndex() が別の番号へ変換してしまう
                    # (input1D[4294967296] が input1D[0] を指す)ため、解決できない名前として扱う。
                    return None
                mplug = mplug.elementByLogicalIndex(index)
        if mplug is None or Plug._has_unresolved_index(mplug):
            # 子アトリビュート名だけを指定した場合などの未確定(-1)のインデックスは maya.cmds で解決できない。
            return None
        return mplug

    @staticmethod
    def _plug_from_path(text):
        """``"node.attr[i].child"`` 形式の文字列を、ノード部分とアトリビュートパスを辿って MPlug へ解決する。

        mesh の ``pnts[i]``、nurbsCurve・nurbsSurface・lattice の ``controlPoints[i]`` のように
        コンポーネント名としても解釈されるアトリビュートは、MSelectionList が頂点・CV として登録し
        プラグとして取り出せないため、Plug の入力解決ではこの関数で解決し直す(maya.cmds の
        ``connectAttr``/``setAttr`` などと同じくアトリビュートとして扱う)。transform の名前で
        シェイプのアトリビュートを指す場合(``pCube1.pnts[3]``)は、唯一のシェイプ(中間オブジェクトを
        除く)へ伸ばして解決する。

        Args:
            text (str): アトリビュートを指す名前。

        Returns:
            tuple[om2.MObject | om2.MDagPath, om2.MPlug] | None: 所有ノード(DAG ノードは
                名前が指すインスタンスの MDagPath)とプラグ。アトリビュートとして解決できない場合
                (存在しないアトリビュート、範囲指定、配列でないアトリビュートへのインデックスなど)は None。
        """
        node_part, separator, attribute_path = text.partition(".")
        if not separator or not attribute_path:
            return None
        owner = om2.MSelectionList()
        try:
            owner.add(node_part)
        except RuntimeError:
            return None
        if owner.length() != 1:
            return None
        mobject = owner.getDependNode(0)
        dagPath = owner.getDagPath(0) if mobject.hasFn(om2.MFn.kDagNode) else None
        match = _PLUG_PATH_TOKEN.match(attribute_path.split(".", 1)[0])
        if match is None:
            return None
        first = Plug._find_plug(mobject, match.group(1))
        if first is None:
            # transform の名前でシェイプのアトリビュートを指す場合は、唯一のシェイプで探す。
            if dagPath is None or not mobject.hasFn(om2.MFn.kTransform):
                return None
            shape_path = om2.MDagPath(dagPath)
            try:
                shape_path.extendToShape()
            except RuntimeError:
                return None
            mobject, dagPath = shape_path.node(), shape_path
            first = Plug._find_plug(mobject, match.group(1))
            if first is None:
                return None
        mplug = Plug._attribute_path_plug(mobject, attribute_path, first)
        if mplug is None:
            return None
        return (dagPath if dagPath is not None else mobject), mplug

    @staticmethod
    def _resolve_input(value):
        """対象を hlib の Plug インスタンスへ変換する。

        文字列は ``str(plug)``・``plug.getFullName()`` が返す形式(``grp1|dup.translateX``、
        ``bs.weight[0]``、エイリアス名、``cubeShape.pnts[2].pntx`` など)を含め、
        maya.cmds と同じ規則で解決する。インスタンス化された DAG ノードのアトリビュートは、
        名前が指すインスタンスのノードを所有ノードにする。コンポーネント名としても
        解釈されるアトリビュート(mesh の ``pnts[i]``、nurbsCurve・lattice の ``controlPoints[i]`` など)は、
        ``connectAttr`` などと同じくアトリビュートとして解決する。

        Args:
            value (Plug | om2.MPlug | str): Plug、MPlug、または ``"node.attribute"`` 形式のアトリビュート名。

        Returns:
            Plug: value が Plug ならそのまま(削除済みでも例外にしない。``Plug.isValid()`` で
                確かめる)、それ以外はアトリビュート型に応じた Plug ラッパー。

        Raises:
            TypeError: 対応しない型、または文字列がアトリビュートを指していない場合。
            ValueError: 空文字列、または空の MPlug の場合。
            RuntimeError: 文字列を解決できない(存在しない、または複数の対象に一致する)場合。
                MPlug の所有ノードが削除済み、またはアトリビュートが ``deleteAttr`` で削除済みの場合
                (``Node(...)``・``Plug(...)`` の生成と同じ。Undo の対象から外れて削除された
                ノードの MPlug は検出できず、Maya が異常終了する)。
        """
        from ..nodes.node import Node as _InputNode
        from .._core.object import Object as _InputObject
        node_class, plug_class, _, _ = _InputObject._classes()
        if isinstance(value, plug_class):
            return value
        if isinstance(value, om2.MPlug):
            if value.isNull:
                raise ValueError("空の MPlug は指定できません")
            return plug_class(node_class(value.node()), value)
        if isinstance(value, str):
            if not value:
                raise ValueError("空でないアトリビュート名を指定してください")
            selection = om2.MSelectionList()
            try:
                selection.add(value)
            except RuntimeError as error:
                raise RuntimeError(f"アトリビュートが見つかりません: {value}") from error
            if selection.length() != 1:
                raise RuntimeError(f"複数の対象に一致します。一意なアトリビュート名を指定してください: {value}")
            try:
                mplug = selection.getPlug(0)
            except TypeError as error:
                # pnts[i]・controlPoints[i] などは頂点・CV として登録されるため、アトリビュートパスを辿る。
                resolved = Plug._plug_from_path(value)
                if resolved is None:
                    raise TypeError(f"アトリビュートを指す名前ではありません: {value}") from error
                owner, mplug = resolved
                return plug_class(node_class(owner), mplug)
            mobject, dagPath = _InputNode._selection_owner(selection, 0, value)
            return plug_class(node_class(dagPath if dagPath is not None else mobject), mplug)
        raise TypeError(f"Plug、om2.MPlug、またはアトリビュート名を指定してください: {type(value).__name__}")

    def _attribute_exists(self):
        """アトリビュートが所有ノードに存在し続けているか判定する(所有ノードは有効であること)。

        頻繁に呼ばれる :meth:`_require_valid`・:meth:`fullName` は、呼び出しの負荷を
        避けるため同じ判定を直接書いている(変更する場合はそろえること)。

        Returns:
            bool: 静的アトリビュート、または削除されていない動的アトリビュートの場合は True。
        """
        if self._static_attribute:
            return True
        return (self._attribute_handle.isValid()
                and self._node._dependency_fn().attributeClass(self._attribute) != _INVALID_ATTRIBUTE)

    def _require_valid(self):
        """所有ノードとアトリビュートが有効か確かめる。

        削除済みの動的アトリビュートの MPlug で値を読み書きすると Maya が異常終了し、削除済みノードの
        MPlug は古い値を返す(Undo の対象から外れた削除では問い合わせで異常終了する場合も
        ある)ため、MPlug・アトリビュートを扱う前に必ず確かめる。静的アトリビュートはノードが有効な間は常に
        存在するため、ノードの確認だけで済む。動的アトリビュートは所有ノードの
        ``MFnDependencyNode.attributeClass()`` で存在を確かめる(:meth:`_attribute_exists`)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        node = self._node
        handle = node._handle
        if handle is None or not handle.isValid():
            raise RuntimeError("所有ノードが無効な(削除済みの)アトリビュートは扱えません")
        if not self._static_attribute:
            # _attribute_exists() と同じ判定。get()/set() のたびに呼ばれるため直接書く。
            fn = node._fn_cache
            if fn is None:
                fn = node._dependency_fn()
            if not self._attribute_handle.isValid() or fn.attributeClass(self._attribute) == _INVALID_ATTRIBUTE:
                raise RuntimeError("削除済みのアトリビュートは扱えません")

    @staticmethod
    def _validated_flags(locked=None, keyable=None, channelBox=None):
        """状態値を全件検証し、Mayaのフラグ名へ変換する。

        Args:
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー可能状態。
            channelBox (bool | None): Channel Box表示状態。

        Returns:
            dict: 指定されたMayaフラグだけを含む辞書。

        Raises:
            TypeError: boolまたはNone以外の状態がある場合。
        """
        flags = {}
        for name, value in (("lock", locked), ("keyable", keyable), ("channelBox", channelBox)):
            if value is not None:
                if not isinstance(value, bool):
                    raise TypeError(f"{name} must be bool or None")
                flags[name] = value
        return flags

    def _require_writable(self):
        """保持参照と複合型の全子の書込み可否を検証する。シーンは変更しない。

        Raises:
            RuntimeError: 無効な参照、ロック、入力接続、書込み禁止の場合。
        """
        from .._core.fastWrite import writable
        self._require_valid()

        def check(plug):
            """複合型の子も確認する。配列要素は展開・作成しない。"""
            writable(plug)
            if plug.isCompound:
                for index in range(plug.numChildren()):
                    check(plug.child(index))

        check(self._mplug)

    @staticmethod
    def _node_from_mplug(mplug):
        """MPlug の所有 MObject から登録された型の Node ラッパーを生成する。

        Args:
            mplug (om2.MPlug): 所有ノードを取得するプラグ。

        Returns:
            Node: 所有ノードの型登録に従って解決したラッパー。
        """
        # nodes.node が ..plugs.plug を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..nodes.node import Node

        return Node(mplug.node())
