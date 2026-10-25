"""Maya API 2.0 の MPlug をアトリビュートラッパーとして扱う。"""

import re
from contextlib import contextmanager, nullcontext

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.attributeType import attributeType, is_internal_data_type, value_reader
from ..core.attributeType import _convert_units
from ..core.fastWrite import _require_supported_type, set_attr
from ..core.fastWrite import set_plug
from ..core.object import Object
from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET

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
    削除済みの対象を黙って受け付けてしまうため、``Node._resolve_input``・``Node(...)``/``mlib.getNode``・
    ``Transform.addConstraint()`` のターゲット・コンストレイント先などでも例外にする。mlib のコマンド(``Object._input_name``)と
    同じく ``ValueError`` として扱う。``Node(...)`` は解決できない対象をすべて
    ``RuntimeError`` にする規則のため、``RuntimeError`` としても捕捉できるようにしている
    (標準ライブラリの ``io.UnsupportedOperation`` が ``OSError`` と ``ValueError`` の両方を
    継承するのと同じ考え方)。
    """


class Plug(Object):
    """所有NodeとMPlugを保持し、アトリビュートの値・接続・状態を扱う。

    配列、登録型、複合型の順でラッパーを選ぶ。参照取得では値を評価せず、
    generic/kAnyは基底Plugのままget時に値を解釈する。
    通常編集はUndo有効時に記録し、対応するfastはUndoなしで直接更新する。

    MayaコマンドへはgetFullName()で文字列化する。名前は改名・親変更に追従する。
    特にArrayPlug・複合Plugは、cmdsによるシーケンス展開を避けるため文字列化が必要。
    所有ノードや動的アトリビュートの削除後はisValidがFalse、名前は空文字列になり、
    値の読書き・接続照会・子参照はRuntimeErrorになる。削除をUndoすれば再び有効になる。
    """

    _registry = None  #: ルートの初期化が構築して注入する型登録表。
    _reader = None  #: get() が値を読む関数。初回の get() でアトリビュート定義から選ぶ(value_reader)。

    def __new__(cls, node, mplug):
        """配列・登録アトリビュート型・複合アトリビュートの順にラッパー型を選ぶ。

        登録アトリビュート型の判定には ``cmds.getAttr(type=True)`` と同じ型名を使う。型名は
        アトリビュート定義から求め(:func:`mlib.core.attributeType.attributeType`)、maya.cmds へ
        問い合わせないため、存在しない配列要素の Plug を作っても要素は作られない。
        generic/kAnyは現在値を読まず、基底Plugとして参照する。
        マトリクスなどの値型はget()を呼んだ時に解釈するため、参照の作成や接続列挙で
        型選択のためのDG評価を行わない。値の型が変わっても同じPlugを保持できる。

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
        """所有Nodeを共有し、MPlug参照のコピーとアトリビュートの有効性確認用ハンドルを保持する。

        MPlugをコピーしても参照先は同じシーンのアトリビュートで、値の独立コピーではない。

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
        """この Plug を所有する mlib ノードを取得する。

        Returns:
            Node: 保持する所有Nodeと同じインスタンス。新しいノード参照は作らない。
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

    def mplug(self):
        """内部で保持するMPlugを、コピーや有効性の再検査をせず返す。

        Returns:
            om2.MPlug: 保持中のAPI参照。アトリビュート値の独立コピーではない。
        """
        return self._mplug

    def getName(self):
        """最短一意ノード名と短いアトリビュート名を含むPlug名を取得する。

        Returns:
            str: 必要な multi インデックスを含むプラグ名。所有ノードが無効(削除済み)、
                またはアトリビュートが削除済みの場合は空文字列(:meth:`getFullName` と同じ)。
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
        """maya.cmdsで一意に解決できるプラグ名を取得する。

        ``<Node.getName()の名前>.<アトリビュートパス>`` の形式で、名前変更・親子付け替えに
        追従する。アトリビュートはロング名と必要な配列番号を含み、エイリアスがあれば使う。

        Returns:
            str: 一意なプラグ名。所有ノードやアトリビュートが削除済みなら空文字列。
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
        return node.getName() + "." + self._mplug.partialName(False, True, True, True, False, True)

    #: ``str(plug)`` は :meth:`getFullName` と同じ(maya.cmds は文字列以外の引数に ``str()`` を
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
        """この参照のPythonラッパークラスを取得する。

        type(self)を返すだけで、Mayaへの照会や有効性の検査は行わない。
        genericの実値が変化してもラッパークラスは変更しない。

        Returns:
            type: Plugまたはその派生クラス（例: ``DoubleLinearPlug``）。
        """
        return type(self)

    def getDataType(self):
        """アトリビュート定義からMayaのデータ型名を取得する。値の評価は行わない。

        Returns:
            str | None: doubleLinear等の定義上のMaya型名。multi全体では要素の型名。
                generic/kAny等は実値を評価せずNoneを返し、値を取得した後もこの規則は変わらない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。

        Note:
            getType()はPythonラッパークラスを返す。未作成の配列要素を生成しない。
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

    def isCompound(self):
        """compound アトリビュートか判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        return self._mplug.isCompound

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

    def setKeyable(self, val=True, leaf=False, *, fast=False):
        """キー設定可否を設定する。

        Args:
            val (bool): キー設定可否。
            leaf (bool): コンパウンドの末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetKeyable"):
            return self._set_flags(leaf, keyable=val, fast=fast)

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
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetFlags"):
            flags = self._validated_flags(locked, keyable, channelBox)
            self._require_valid()
            if flags:
                if fast:
                    for flag, value in flags.items():
                        setattr(self._mplug, {"lock": "isLocked", "keyable": "isKeyable",
                                             "channelBox": "isChannelBox"}[flag], value)
                else:
                    set_attr(self.getFullName(), **flags, fast=False)
            return self

    def isChannelBox(self):
        """Channel Boxフラグ（keyableによる表示を含まない）。

        Returns:
            bool: Channel Boxフラグ（keyableによる表示を含まない）。
        """
        self._require_valid()
        return self.mplug().isChannelBox

    def setChannelBox(self, val=True, leaf=False, *, fast=False):
        """Channel Box表示を設定する。

        Args:
            val (bool): 表示状態。有効時はkeyableを無効にする。
            leaf (bool): コンパウンドの末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetChannelBox"):
            return self._set_flags(leaf, channelBox=val, fast=fast)

    def unlock(self, below=False, undoable=True, *, fast=False):
        """上位と必要な下位階層をアンロックする。

        Args:
            below (bool): 子階層も解除する。
            undoable (bool): FalseはOpenMayaによるUndoなしの更新。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            list[Plug]: 実際に解除したPlugを上位から返す。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugUnlock"):
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
                    plug.setFlags(locked=False, fast=fast or not undoable)
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

    def mute(self, *, fast=False):
        """現在値でミュートし、自身を返す。

        Args:
            fast (bool): Trueは未対応で、変更前にNotImplementedError。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        return self.setMuted(True, fast=fast)

    def unmute(self, *, fast=False):
        """ミュートを解除し、自身を返す。

        Args:
            fast (bool): Trueは未対応で、変更前にNotImplementedError。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        return self.setMuted(False, fast=fast)

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

    def isConnected(self, *, src=_UNSET, dst=_UNSET, source=_UNSET, destination=_UNSET):
        """指定方向の直接の接続を持つか判定する。

        Args:
            src (bool): 入力元からの接続を調べる。別名 ``source`` も使用可能。
            dst (bool): 出力先への接続を調べる。別名 ``destination`` も使用可能。
            source (bool): srcの別名。同時指定は不可。
            destination (bool): dstの別名。同時指定は不可。

        Returns:
            bool: 指定方向に接続を持つ場合は ``True``。両Falseなら ``False``。

        Raises:
            TypeError: 方向指定がboolでない場合、または別名と重複指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        if source is not _UNSET:
            if src is not _UNSET:
                raise _ArgumentError("Specify only one of 'src' and 'source'")
            src = source
        if destination is not _UNSET:
            if dst is not _UNSET:
                raise _ArgumentError("Specify only one of 'dst' and 'destination'")
            dst = destination
        if src is _UNSET:
            src = True
        if dst is _UNSET:
            dst = True
        self._require_valid()
        self._validate_connection_directions(src, dst)
        if src and dst:
            return self._mplug.isConnected
        return (src and self._mplug.isDestination) or (dst and self._mplug.isSource)

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

    def isHidden(self):
        """UI から隠されたアトリビュートか判定する。

        Returns:
            bool: 隠しアトリビュートの場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).hidden

    def isDynamic(self):
        """動的に追加されたアトリビュート（addAttr によるカスタムアトリビュート等）か判定する。

        Returns:
            bool: 動的アトリビュートの場合は ``True``。静的（ノード型に組み込み）のアトリビュートは ``False``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).dynamic

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

    def isSettable(self):
        """Maya標準のsettable照会で、現在値を設定可能か取得する。

        定義上のwritableとは異なり、ロックや入力接続の現在状態を反映する。
        値の型・範囲や実行時エラーまで含めたset()の成功保証ではない。

        Returns:
            bool: maya.cmds.getAttr(settable=True)の結果。

        Raises:
            RuntimeError: 所有ノード・アトリビュートが無効、または照会に失敗した場合。
        """
        self._require_valid()
        return bool(cmds.getAttr(self.getFullName(), settable=True))

    def isStorable(self):
        """シーンファイルへ値が保存されるアトリビュートか判定する。

        Returns:
            bool: 保存対象の場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return om2.MFnAttribute(self._mplug.attribute()).storable

    def hasMin(self):
        """最小値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最小値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        fn = self._range_attribute_fn()
        return fn.hasMin() if fn is not None else False

    def hasMax(self):
        """最大値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最大値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        fn = self._range_attribute_fn()
        return fn.hasMax() if fn is not None else False

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
        fn = self._range_attribute_fn()
        return fn.getMin() if fn is not None and fn.hasMin() else None

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
        fn = self._range_attribute_fn()
        return fn.getMax() if fn is not None and fn.hasMax() else None

    def hasSoftMin(self):
        """ソフト最小値（UIスライダーの下限）を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最小値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        fn = self._range_attribute_fn()
        return fn.hasSoftMin() if fn is not None else False

    def hasSoftMax(self):
        """ソフト最大値（UIスライダーの上限）を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最大値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        fn = self._range_attribute_fn()
        return fn.hasSoftMax() if fn is not None else False

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
        fn = self._range_attribute_fn()
        return fn.getSoftMin() if fn is not None and fn.hasSoftMin() else None

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
        fn = self._range_attribute_fn()
        return fn.getSoftMax() if fn is not None and fn.hasSoftMax() else None

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

    def setAlias(self, name=None, *, fast=False):
        """別名を設定または解除する。

        Args:
            name (str | None): 別名。Noneまたは空文字で解除。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetAlias"):
            self._require_valid()
            if fast:
                fn = self.getNode()._dependency_fn()
                alias = name or fn.plugsAlias(self._mplug)
                if alias:
                    fn.setAlias(alias, self._mplug.partialName(useLongNames=True), self._mplug, bool(name))
            elif name:
                cmds.aliasAttr(name, self.getFullName())
            elif cmds.aliasAttr(self.getFullName(), query=True):
                cmds.aliasAttr(self.getFullName(), remove=True)
            return self

    def setKey(self, *, fast=False, **kwargs):
        """対象アトリビュートへキーを設定する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。
            **kwargs: Maya setKeyframeのフラグ。値・時間はMayaのUI単位。
                fastは単一のtime/t・value/v・inTangentType/itt・outTangentType/ottのみ。
                レイヤー、範囲、複合入力等は更新前に拒否する。
                接線省略時はMayaのグローバル設定を使う。fastの入力stepはautoへ補正し、
                入力stepnextはNotImplementedError、fixed/global/未知型はValueErrorで
                カーブを生成・変更する前に拒否する。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetKey"):
            self._require_valid()
            if fast:
                self._set_key_direct(kwargs)
            else:
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
            kind = node.getType()
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

    def setEnumNames(self, names, *, fast=False):
        """enumアトリビュートの表示名を指定順に更新する。

        Args:
            names (Iterable[str]): 値0から順に対応する空でない名前列。
                API 2.0は既存enumフィールドの削除を公開しないためfast=Trueは未対応。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            Plug: 更新した自身。

        Raises:
            TypeError: enumアトリビュートでない、または名前が文字列でない場合。
            ValueError: 空の列、空の名前、区切り文字を含む名前の場合。
            RuntimeError: アトリビュートが無効、またはMayaが変更を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetEnumNames"):
            if fast:
                raise NotImplementedError("setEnumNames does not support fast=True")
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
        """enum アトリビュートのフィールド名に対応する値を取得する(getEnumNameの逆引き)。

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

    def setLocked(self, val=True, leaf=False, *, fast=False):
        """ロックを設定する。

        Args:
            val (bool): ロック状態。
            leaf (bool): コンパウンドでは末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetLocked"):
            return self._set_flags(leaf, locked=val, fast=fast)

    lock = setLocked

    def isMuted(self):
        """アトリビュートがミュートされているか判定する。

        Returns:
            bool: ミュートされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        source = self._mplug.source()
        if source.isNull:
            return False
        node = om2.MFnDependencyNode(source.node())
        return node.typeName == "mute" and node.findPlug("mute", False).asBool()

    def setMuted(self, state, *, fast=False):
        """ミュート状態を設定する。Trueは現在値で固定し、Falseは解除する。

        Args:
            state (bool): ミュートする場合はTrue。
            fast (bool): Trueは未対応で、変更前にNotImplementedError。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: stateまたはfastがboolでない場合。
            NotImplementedError: fast=Trueの場合。
            RuntimeError: 所有ノード・アトリビュートが無効、またはMayaが更新を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetMuted"):
            if fast:
                raise NotImplementedError("setMuted does not support fast=True")
            self._require_valid()
            if not isinstance(state, bool):
                raise TypeError("state must be a bool")
            if state:
                cmds.mute(self.getFullName())
            else:
                cmds.mute(self.getFullName(), disable=True, force=True)
            return self

    def delete(self, force=_UNSET, *, fast=False, f=_UNSET):
        """このアトリビュートをノードから削除する。

        動的に追加されたアトリビュート（addAttr によるカスタムアトリビュート）にのみ使用できる。
        静的（ノード型に組み込み）のアトリビュートを削除しようとすると Maya が拒否する。
        接続がある場合は force に関わらず Maya が自動的に切断してから削除する。

        Args:
            force (bool): True の場合、ロックされていれば一時的に解除してから
                削除する。False でロックされているアトリビュートを削除しようとすると
                RuntimeError になる。 別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: force=False でロックされている場合や、静的アトリビュートの
                削除を試みた場合など、Maya が削除を拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if force is _UNSET:
            force = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugDeleteAttr"):
            self._require_valid()
            if fast:
                attribute = self._mplug.attribute()
                fn = om2.MFnAttribute(attribute)
                if not fn.dynamic or not fn.parent.isNull():
                    raise RuntimeError("Only top-level dynamic attributes can be deleted")
                if self.isLocked() and not force:
                    raise RuntimeError("Attribute is locked: " + self.getFullName())
                modifier = om2.MDGModifier()
                modifier.removeAttribute(self.getNode().mnode(), attribute)
                if force and self.isLocked():
                    self._mplug.isLocked = False
                modifier.doIt()
            else:
                if force and self.isLocked():
                    set_attr(self.getFullName(), lock=False, fast=False)
                cmds.deleteAttr(self.getFullName())

    def get(self, *, uiUnits=False):
        """現在の評価値を取得する。値はキャッシュしない。

        Args:
            uiUnits (bool): Trueは単位付き数値を現在のUI単位へ換算する。既定Falseはcm/rad/秒。

        Returns:
            object: 型に応じた値。CompoundPlug.getは子の定義順tuple、ArrayPlug.getは
                論理番号をキーとするdict。API読取の型付き配列はlistで、各要素は
                vectorArray=XYZ、pointArray=XYZW、matrixArray=16成分のtuple。
                未初期化データはNone、空配列は空list。generic/kAnyは現在値に応じて
                Matrix・数値・tuple等を返す。マトリクス・型付き配列の成分と無単位値は換算しない。

        Raises:
            TypeError: uiUnitsがbool以外の場合。
            RuntimeError: 参照が無効、または値を読み取れない場合。
        """
        self._validate_ui_units(uiUnits)
        value = self._get_internal()
        return _convert_units(self._mplug, value) if uiUnits else value

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """値を設定する。ロック解除や接続解除、自動ロールバックは行わない。

        通常はcmds.setAttrで更新し、Undo有効時に記録する。
        safeは本体のRuntimeError/TypeError/ValueErrorを失敗数へ変換し、
        複合値の失敗は子ごとに再試行する。成功した子の更新は残る。

        Args:
            value (object): 内部単位の値（距離cm・角度rad・時間秒）。
            safe (bool): Trueは対応する失敗を数える。既定Falseは例外を送出する。
            uiUnits (bool): Trueは現在のUI単位の数値入力。既定Falseは内部単位。
            fast (bool): Trueは対応型をOpenMayaで直接更新する。Undoへ記録せず、Undo設定も変更しない。

        Returns:
            Plug | int: 通常は自身。safe=Trueは成功なら0、子の再試行では失敗数の合計。
                無効参照・分解不能な入力・再試行を完了できない失敗は1。
                厳密な未更新成分の総数は保証しない。

        Raises:
            TypeError: fastがbool以外、またはmulti全体への設定。safe=Trueでも拒否する。
                safe=Falseで不正な入力の場合も送出する。
            ValueError: safe=Falseで値の変換等に失敗した場合。
            RuntimeError: safe=Falseで無効参照・ロック・入力接続等により書けない場合。
            NotImplementedError: fast未対応型。safe=Trueでも部分更新前に拒否する。

        Note:
            safe=Trueのfast複合値は、値や書込み可否より先に全子の型対応を確認する。
            呼出し形式の誤りや、上記以外の例外を一律には抑制しない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSet"):
            if self.isArray():
                raise TypeError("Set an array element instead of the array plug")
            if safe and fast and self.isValid() and self.mplug().isCompound:
                # 未対応の子を、ロックや入力値の失敗に読み替えて部分更新しない。
                _require_supported_type(self.mplug())
            try:
                self._set_value(value, uiUnits=uiUnits, fast=fast)
            except NotImplementedError:
                raise
            except (RuntimeError, TypeError, ValueError):
                if not safe:
                    raise
                return self._set_children_safely(value, uiUnits=uiUnits, fast=fast)
            return 0 if safe else self

    def setIfChanged(self, value, *, unlock=False, fast=False):
        """現在のスカラー値と異なる場合だけ書き込み、更新の有無を返す。

        getで現在値を取得してPythonの等価比較を行う。同値なら書込み可否の検証や
        ロック変更をせずFalseを返す。異なる場合はsetへ委譲し、失敗は例外にする。

        Args:
            value (bool | int | float | str): 比較・設定する値。数値は許容誤差なしで比較し、単位はcm/rad/秒。
            unlock (bool): Trueで対象自身のロックを一時解除し、値更新の成否にかかわらず
                再ロックを試みる。親のロックや入力接続は解除しない。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。内側のset/状態更新にも同じ値を渡す。

        Returns:
            bool: 更新に成功した場合はTrue。同値のため書き込まなかった場合はFalse。

        Raises:
            TypeError: スカラー以外を指定した場合。
            RuntimeError: Mayaがアトリビュート更新を拒否した場合。

        Note:
            通常は値とロックの更新をUndoが有効なら同じチャンクへ記録する。
            fastはUndo設定を変更せず、更新済みの値の自動ロールバックは行わない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugSetIfChanged"):
            if not isinstance(value, (bool, int, float, str)):
                raise TypeError("setIfChanged supports scalar values only")
            if self.get() == value:
                return False
            locked = self.isLocked()
            if unlock and locked:
                self.setFlags(locked=False, fast=fast)
            try:
                self.set(value, fast=fast)
            finally:
                if unlock and locked:
                    self.setFlags(locked=True, fast=fast)
            return True

    def reset(self, *, fast=False):
        """数値・単位・enumアトリビュートを定義上の既定値へ戻す。

        単位アトリビュートの既定値をcm/rad/秒へ換算してsetへ渡す。
        複合アトリビュートは定義順に子を更新し、途中で失敗したら例外を送出する。
        全子の事前検証や、成功した子の自動ロールバックは行わない。
        接続の切断やロック解除はしない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Plug: 自身。通常はUndoが有効なら子の変更を同じチャンクへ記録する。
                fastは子へも引数で渡し、Undoへ記録しない。

        Raises:
            TypeError: 配列全体・文字列・messageなど既定値を扱えないアトリビュートの場合。
            RuntimeError: ロック・入力接続などで変更できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugReset"):
            if self.isArray():
                raise TypeError("Reset an array element instead of the array plug")
            self._require_valid()
            if self._mplug.isCompound:
                for index in range(self._mplug.numChildren()):
                    Plug(self._node, self._mplug.child(index)).reset(fast=fast)
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
            self.set(value, fast=fast)
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

    def getSource(self, *, skipConversionNodes=_UNSET, scn=_UNSET, **kwargs):
        """直接の入力元を取得する。子・配列要素の独立接続は展開しない。

        Args:
            skipConversionNodes (bool): 既定TrueはunitConversion系を省略する。
                Falseは直結したPlug。getConnectionsの既定とは異なる。
            scn (bool): skipConversionNodesの別名。同時指定は不可。
            **kwargs: getConnectionsの型・ペア・Node化等の指定。子/要素展開は無効、indexは0に固定。
                idxは固定したindexと競合するため指定不可。

        Returns:
            Plug | Node | tuple | None: 既定は入力元Plug。未接続や型条件不一致はNone。
                asPairは(自身側Plug, 入力元)、asNodeは相手Node。値や接続は変更しない。

        Raises:
            TypeError: 長短名を同時指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        if scn is not _UNSET:
            if skipConversionNodes is not _UNSET:
                raise _ArgumentError("Specify only one of 'skipConversionNodes' and 'scn'")
            skipConversionNodes = scn
        if skipConversionNodes is _UNSET:
            skipConversionNodes = True
        self._require_valid()
        if not kwargs:
            sources = ([self._mplug.source()] if skipConversionNodes else
                       self._mplug.connectedTo(True, False))
            return (Plug(self._node_from_mplug(sources[0]), sources[0])
                    if sources and not sources[0].isNull else None)
        kwargs.update(skipConversionNodes=skipConversionNodes, checkChildren=False,
                      checkElements=False, index=0)
        return self.getConnections(True, False, **kwargs)

    def getDestinations(self, *, skipConversionNodes=_UNSET, scn=_UNSET, **kwargs):
        """直接の出力先を取得する。子・配列要素の独立接続は展開しない。

        Args:
            skipConversionNodes (bool): 既定TrueはunitConversion系を省略する。Falseは直結したPlug。
            scn (bool): skipConversionNodesの別名。同時指定は不可。
            **kwargs: getConnectionsの型・ペア・Node化・index等の指定。子/要素展開は無効。

        Returns:
            list | Plug | Node | tuple | None: 既定は出力先Plugのlist、未接続は空list。
                asPairは(自身側Plug, 出力先)、asNodeは相手Node。
                indexは絞込み・重複統合後の一件を選び、範囲外はNone。値や接続は変更しない。

        Raises:
            TypeError: 長短名を同時指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        if scn is not _UNSET:
            if skipConversionNodes is not _UNSET:
                raise _ArgumentError("Specify only one of 'skipConversionNodes' and 'scn'")
            skipConversionNodes = scn
        if skipConversionNodes is _UNSET:
            skipConversionNodes = True
        self._require_valid()
        if not kwargs:
            targets = (self._mplug.destinations() if skipConversionNodes else
                       self._mplug.connectedTo(False, True))
            return [Plug(self._node_from_mplug(plug), plug) for plug in targets]
        kwargs.update(skipConversionNodes=skipConversionNodes, checkChildren=False,
                      checkElements=False)
        return self.getConnections(False, True, **kwargs)

    def getConnections(self, s=True, d=True, c=False, t=None, et=False, scn=False, source=_UNSET,
        destination=_UNSET, connections=False, type=None, exactType=False, skipConversionNodes=False,
        asPair=False, asNode=False, checkChildren=True, checkElements=True, index=_UNSET, pcls=None, *,
        idx=_UNSET, src=_UNSET, dst=_UNSET):
        """接続参照を取得する。既定は変換ノードを省略しない。

        自身の入力・出力、次に既存配列要素または子へ再帰する。
        型で絞り、初出順で重複を統合した後にindexを適用する。

        Args:
            s (bool): 入力方向。sourceとANDする。
            d (bool): 出力方向。destinationとANDする。
            c (bool): connections/asPairとORし、ペアを返す。
            t (str | None): typeが未指定または偽のときの型条件。
            et (bool): exactTypeとORする。
            scn (bool): skipConversionNodesとORする。
            source (bool): 入力を含める。sとANDする。
            destination (bool): 出力を含める。dとANDする。
            connections (bool): c/asPairとORし、ペアを返す。
            type (str | None): 相手Nodeの型。tより優先する。
            exactType (bool): Trueは型名の完全一致。Falseは派生型を含む。
            skipConversionNodes (bool): unitConversion系を省略する。
            asPair (bool): (自身側Plug, 相手側)の組で返す。入力方向でも同じ順序。
            asNode (bool): 相手側をNodeにする。ペアの自身側はPlugのまま。
            checkChildren (bool): 複合の子も探索する。
            checkElements (bool): 既存配列要素も探索する。
            index (int | None): 絞込み後のPython添字。負数可、範囲外はNone。
            pcls (type | None): Plugとして返す側をこのクラスで構築する。
            idx (int | None): indexの別名。同時指定は不可。
            src (bool): sourceの別名。同時指定は不可。
            dst (bool): destinationの別名。同時指定は不可。

        Returns:
            list | Plug | Node | tuple | None: 既定は相手Plugのlist。index指定時は一件またはNone。
                重複は通常は相手Plug単位、asNodeは相手Node単位、asPairは自身側も含めて統合する。
                値やノードの複製は行わない。

        Raises:
            TypeError: index/idx・source/src・destination/dstを同時指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if dst is not _UNSET:
            if destination is not _UNSET:
                raise _ArgumentError("Specify only one of 'destination' and 'dst'")
            destination = dst
        if source is _UNSET:
            source = True
        if destination is _UNSET:
            destination = True
        if index is _UNSET:
            index = None
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

    def isConnectedTo(self, other, *, src=_UNSET, dst=_UNSET, source=_UNSET, destination=_UNSET):
        """指定したプラグと接続されているか判定する。

        既定では入力・出力いずれの向きでも一致すれば True を返す。
        子・配列要素の独立した接続や変換ノードの先の接続は展開しない。

        Args:
            other (Plug | om2.MPlug | str): 判定対象のプラグ。文字列は
                ``"node.attribute"`` 形式のアトリビュート名。
            src (bool): otherから自身への入力接続を調べる。別名 ``source`` も使用可能。
            dst (bool): 自身からotherへの出力接続を調べる。別名 ``destination`` も使用可能。
            source (bool): srcの別名。同時指定は不可。
            destination (bool): dstの別名。同時指定は不可。

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
        if source is not _UNSET:
            if src is not _UNSET:
                raise _ArgumentError("Specify only one of 'src' and 'source'")
            src = source
        if destination is not _UNSET:
            if dst is not _UNSET:
                raise _ArgumentError("Specify only one of 'dst' and 'destination'")
            dst = destination
        if src is _UNSET:
            src = True
        if dst is _UNSET:
            dst = True
        self._require_valid()
        self._validate_connection_directions(src, dst)
        other = Plug._resolve_input(other)
        other._require_valid()
        return any(
            connected == other.mplug()
            for connected in self._mplug.connectedTo(src, dst)
        )

    def connect(self, src=_UNSET, force=False, f=False, lock=False, l=False, nextAvailable=False, na=False, *,
        unlock=True, fast=False, source=_UNSET):
        """srcから自身へ接続し、接続先を返す。同一の既存接続も例外にする。

        通常はcmds.connectAttrでUndo有効時に記録する。fastはMDGModifierを使う。
        解除したロックは逆順に復元するが、復元失敗では例外になり残りを復元しない。
        接続済みの変更は、後続の失敗だけでは自動で戻さない。

        Args:
            src (Plug | om2.MPlug | str): 接続元。
            force (bool): 既存入力を置換する。unlock=Trueなら接続先と上位の複合/配列を一時解除する。
                接続元のロックは変更しない。
            f (bool): forceとORする。
            lock (bool): 接続後にロックする。Falseでも元のロックは復元する。
            l (bool): lockとORする。
            nextAvailable (bool): 配列全体では0から入力/ロックのない要素を探す。
                複合の子も判定する。定数値や出力接続がある要素も候補になる。
            na (bool): nextAvailableとORする。
            unlock (bool): Falseならforceでもロックを解除しない。
            fast (bool): TrueはUndoなしの直接接続。Undo設定は変更しない。
            source (Plug | om2.MPlug | str): srcの別名。同時指定は不可。

        Returns:
            Plug: 実際の接続先。nextAvailable時は選んだ要素。参照を取り直す場合があり、self同一性は保証しない。

        Raises:
            TypeError: 接続元が未指定・未対応型、長短名の競合、またはfastがbool以外の場合。
            RuntimeError: 同一接続・forceなしの入力置換・ロック・接続やロック復元の失敗。
        """
        if source is not _UNSET:
            if src is not _UNSET:
                raise _ArgumentError("Specify only one of 'src' and 'source'")
            src = source
        if src is _UNSET:
            raise _ArgumentError("Missing required argument: 'src'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugConnect"):
            self._require_valid()
            src = Plug._resolve_input(src)
            force, lock = force or f, lock or l
            if self.isLocked() and not (force and unlock):
                raise RuntimeError("Attribute is locked: " + self.getFullName())
            # 配列親を先に解除する。親がロックされたまま空き番号を探すと
            # 全要素がロック扱いになり、探索が終わらなくなる。
            with self._temporarily_unlocked_connection_path(force and unlock, fast=fast):
                target = self
                if self.isArray() and (nextAvailable or na):
                    def occupied(plug):
                        """自身または子に入力接続・ロックがある要素を避ける。"""
                        if plug.isLocked() or plug.getSource(skipConversionNodes=False) is not None:
                            return True
                        return plug.mplug().isCompound and any(occupied(p) for p in plug.getChildren())
                    index = 0
                    while True:
                        candidate = Plug(self.getNode(), self.mplug().elementByLogicalIndex(index))
                        if not occupied(candidate):
                            target = candidate
                            break
                        index += 1
                current = target.getSource(skipConversionNodes=False)
                if current is not None and current.getFullName() == src.getFullName():
                    raise RuntimeError("Already connected: " + src.getFullName() + " -> " + target.getFullName())
                target_name = target.getFullName()
                keep_self = target is self and not self.mplug().isNetworked
                if fast:
                    if current is not None and not force:
                        raise RuntimeError("Destination already has an input: " + target_name)
                    modifier = om2.MDGModifier()
                    if current is not None:
                        modifier.disconnect(current.mplug(), target.mplug())
                    modifier.connect(src.mplug(), target.mplug())
                    modifier.doIt()
                    if lock:
                        target.mplug().isLocked = True
                else:
                    if current is None:
                        target._record_connection_value()
                    cmds.connectAttr(src.getFullName(), target_name, force=force)
                    if lock:
                        cmds.setAttr(target_name, lock=True)
            return self if keep_self else Plug._resolve_input(target_name)

    def disconnectInput(self, *, fast=False):
        """直接の入力だけを解除する。未接続なら何もせず自身を返す。

        変換ノードを飛ばさずに現在の入力を調べ、disconnectへ委譲する。
        子/配列要素の独立接続は展開せず、ロックも一時解除しない。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya直接更新。

        Returns:
            Plug: 自身。disconnectの単件返却である入力元ではない。

        Raises:
            RuntimeError: 無効な参照、またはロック等により切断できない場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugDisconnectInput"):
            source = self.getSource(skipConversionNodes=False)
            if source is not None:
                self.disconnect(source, fast=fast)
            return self

    def disconnect(self, src=_UNSET, force=False, f=False, nextAvailable=False, na=False, *, fast=False,
        source=_UNSET):
        """指定入力元との直接接続を解除する。子接続へ再帰せず、変換ノードも飛ばさない。

        通常はcmds.disconnectAttrでUndo有効時に記録し、fastはMDGModifierを使う。
        変換ノードは削除しない。ロック復元の失敗は例外で打ち切り、完了済みの切断は戻さない。

        Args:
            src (Plug | om2.MPlug | str | None): 入力元。省略またはNoneは現在の直接入力。
            force (bool): 接続先と上位を一時解除し、逆順に再ロックする。入力元のロックは変えない。
            f (bool): forceとORする。
            nextAvailable (bool): 配列内でsrcへ直結した既存要素を全て解除する。src明示時だけ有効。
            na (bool): nextAvailableとORする。
            fast (bool): TrueはUndoなしの直接更新。Undo設定は変更しない。
            source (Plug | om2.MPlug | str | None): srcの別名。同時指定は不可。

        Returns:
            Plug | list[Plug]: 単一切断は取り直した入力元Plug（自身ではない）。配列検索は接続先要素のlist。

        Raises:
            TypeError: srcがbool等の未対応型、長短名の競合、またはfastがbool以外の場合。
            RuntimeError: 入力・指定接続がない、または切断やロック復元に失敗した場合。

        Note:
            配列検索は既存順に切断し、後半の失敗でも先行する切断は戻さない。
            未接続時に何もしない入力解除は :meth:`disconnectInput` を使う。
        """
        if source is not _UNSET:
            if src is not _UNSET:
                raise _ArgumentError("Specify only one of 'src' and 'source'")
            src = source
        if src is _UNSET:
            src = None
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugDisconnect"):
            self._require_valid()
            if isinstance(src, bool):
                raise TypeError("src must be an input plug reference, not bool; use disconnectAll for directions")
            if src is not None:
                src = Plug._resolve_input(src)
            if self.isArray() and (nextAvailable or na) and src is not None:
                targets = [p for p in self.getElements() if p.getSource(skipConversionNodes=False) == src]
                if not targets:
                    raise RuntimeError("Input connection not found: " + self.getFullName())
                names = [target.getFullName() for target in targets]
                for target in targets:
                    target.disconnect(src, force=force or f, fast=fast)
                return [Plug._resolve_input(name) for name in names]
            if src is None:
                src = self.getSource(skipConversionNodes=False)
            if src is None:
                raise RuntimeError("Input connection not found: " + self.getFullName())
            if not self.isConnectedTo(src, src=True, dst=False):
                raise RuntimeError("Input connection not found: " + self.getFullName())
            source_name = src.getFullName()
            with self._temporarily_unlocked_connection_path(force or f, fast=fast):
                if fast:
                    modifier = om2.MDGModifier()
                    modifier.disconnect(src.mplug(), self.mplug())
                    modifier.doIt()
                else:
                    cmds.disconnectAttr(src.getFullName(), self.getFullName())
            return Plug._resolve_input(source_name)

    def disconnectAll(self, *, src=_UNSET, dst=_UNSET, fast=False, source=_UNSET, destination=_UNSET):
        """入力、次に出力の直接接続を解除する。ロックは解除しない。

        子・配列要素の独立接続は展開せず、変換ノードも削除しない。
        通常はUndo有効時に同じチャンクへ記録する。途中失敗で完了済みの切断は戻さない。

        Args:
            src (bool): 入力を解除する。既定True。
            dst (bool): 全出力を解除する。既定True。
            fast (bool): TrueはUndoなしの直接更新。Undo設定は変更しない。
            source (bool): srcの別名。同時指定は不可。
            destination (bool): dstの別名。同時指定は不可。

        Returns:
            Plug: 自身。未接続または両Falseなら変更しない。

        Raises:
            TypeError: 方向・fastがbool以外、または長短名を同時指定した場合。
            RuntimeError: 無効参照、またはロック等により切断できない場合。
        """
        if source is not _UNSET:
            if src is not _UNSET:
                raise _ArgumentError("Specify only one of 'src' and 'source'")
            src = source
        if destination is not _UNSET:
            if dst is not _UNSET:
                raise _ArgumentError("Specify only one of 'dst' and 'destination'")
            dst = destination
        if src is _UNSET:
            src = True
        if dst is _UNSET:
            dst = True
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibPlugDisconnectAll"):
            self._require_valid()
            self._validate_connection_directions(src, dst)
            if src:
                self.disconnectInput(fast=fast)
            if dst:
                for destination in self.getDestinations(skipConversionNodes=False):
                    destination.disconnect(self, fast=fast)
            return self

    def connectTo(self, dst=_UNSET, *, fast=False, destination=_UNSET, **kwargs):
        """自身からdstへ接続し、接続先Plugを返す。

        dstをPlugへ解決し、 ``dst.connect(self, **kwargs)`` へ委譲する。
        通常Undo・force時のロック復元・配列の空き番号選択はconnectと共通。
        fast指定は内側のconnectへ引数で渡す。

        Args:
            dst (Plug | om2.MPlug | str): 接続先。 別名 ``destination`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。未対応操作は更新前に拒否。
            **kwargs: connectのforce/f・lock/l・nextAvailable/na・unlock。
            destination (Plug | om2.MPlug | str): dstの別名。同時指定は不可。

        Returns:
            Plug: 実際の接続先。
        """
        if destination is not _UNSET:
            if dst is not _UNSET:
                raise _ArgumentError("Specify only one of 'dst' and 'destination'")
            dst = destination
        if dst is _UNSET:
            raise _ArgumentError("Missing required argument: 'dst'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        return Plug._resolve_input(dst).connect(self, **kwargs, fast=fast)

    def _set_value(self, value, *, uiUnits=False, fast=False):
        """値の型と単位を揃え、指定した更新経路へ書き込む。

        safeの再試行とUndoチャンクは呼出し元で扱う。

        Args:
            value (object): 書き込む値。
            uiUnits (bool): TrueならUI単位から内部単位へ変換する。
            fast (bool): TrueならOpenMayaで直接更新する。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        if uiUnits:
            value = _convert_units(self._mplug, value, to_ui=False)
        if attributeType(self._mplug) is None:
            from ..maths import Matrix, Transformation
            if (isinstance(value, (om2.MMatrix, om2.MTransformationMatrix, Transformation))
                    or isinstance(value, (tuple, list)) and len(value) == 16):
                value = Matrix(value)
                if fast:
                    set_plug(self._mplug, value)
                else:
                    set_attr(self.getFullName(), *tuple(value), type="matrix", fast=False)
                return
        if fast:
            set_plug(self._mplug, value)
            return
        value = _convert_units(self._mplug, value)
        if isinstance(value, str):
            set_attr(self.getFullName(), value, type="string", fast=False)
            return
        if isinstance(value, (tuple, list)):
            attr_type = attributeType(self._mplug)
            if attr_type in _SCALAR_ARRAY_TYPES:
                set_attr(self.getFullName(), value, type=attr_type, fast=False)
            elif attr_type in _LENGTH_PREFIXED_ARRAY_TYPES:
                set_attr(self.getFullName(), len(value), *value, type=attr_type, fast=False)
            else:
                set_attr(self.getFullName(), *value, fast=False)
            return
        set_attr(self.getFullName(), value, fast=False)

    def _set_children_safely(self, value, *, uiUnits=False, fast=False):
        """失敗した複合値を子の定義順で再試行し、失敗数を返す。

        分解できない入力や再試行を完了できない失敗は1とし、更新済みの子は戻さない。

        Args:
            value (object): 最初の設定へ渡した値。
            uiUnits (bool): 子のsetへ渡す単位指定。
            fast (bool): 子のsetへ渡す更新経路。

        Returns:
            int: 子の失敗数、または分解できない失敗を表す1。
        """
        if not self.isValid() or not self.mplug().isCompound:
            return 1
        try:
            self._validate_ui_units(uiUnits)
            values = tuple(value)
            if len(values) != self.mplug().numChildren():
                return 1
            failures = 0
            for index, child_value in enumerate(values):
                failures += self[index].set(child_value, safe=True, uiUnits=uiUnits, fast=fast)
            return failures
        except NotImplementedError:
            raise
        except (RuntimeError, TypeError, ValueError):
            return 1

    def _get_internal(self):
        """評価済みの Maya アトリビュート値を取得する。

        最初の呼出しで読取関数を選んで保持し、値そのものは毎回読み直す。
        generic/kAnyのマトリクス判定も値取得時に行い、Pythonラッパークラスは変えない。

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
                :func:`mlib.core.attributeType.is_internal_data_type`)。
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
        if attributeType(self._mplug) is None and om2.MFnAttribute(self._attribute).readable:
            # generic/kAnyの参照型は固定し、実際の値を読む時だけマトリクスを判定する。
            # 数値などMObjectを持たない値は、従来のcmds読取へ委譲する。
            try:
                data = self._mplug.asMObject()
            except RuntimeError:
                data = None
            if data is not None and not data.isNull() and data.hasFn(om2.MFn.kMatrixData):
                from ..maths import Matrix
                return Matrix.fromMMatrix(om2.MFnMatrixData(data).matrix())
        value = cmds.getAttr(self.getFullName())
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return tuple(value[0])
        return value

    def _set_key_direct(self, kwargs):
        """単一時刻のキー設定だけをAPI 2.0で実行する。

        Args:
            kwargs (dict): value/timeと入出力接線型。長名とMaya短名を受け付ける。

        Raises:
            NotImplementedError: 範囲・レイヤー・非時間カーブ等の場合。生成前に拒否。
                入力stepnextもMayaの版で補正が異なるため生成前に拒否する。
            ValueError: 明示的なfixed・global・未知の接線型を指定した場合。
        """
        import math
        import maya.api.OpenMayaAnim as oma2
        from ..nodes.animCurve import AnimCurve
        aliases = {"v": "value", "t": "time", "itt": "inTangentType",
                   "ott": "outTangentType"}
        options = dict(kwargs)
        for short, long in aliases.items():
            if short in options:
                if long in options:
                    raise _ArgumentError("Specify only one of {!r} and {!r}".format(short, long))
                options[long] = options.pop(short)
        if set(options) - {"value", "time", "inTangentType", "outTangentType"}:
            raise NotImplementedError("Unsupported fast setKey flags")
        if self.isArray() or self.isCompound():
            raise NotImplementedError("fast setKey requires a scalar plug")
        if self.isLocked():
            raise RuntimeError("Attribute is locked: " + self.getFullName())
        if not om2.MFnAttribute(self._mplug.attribute()).writable:
            raise RuntimeError("Attribute is not writable: " + self.getFullName())
        key_time = options.get("time")
        if isinstance(key_time, (tuple, list)):
            if len(key_time) != 1:
                raise NotImplementedError("fast setKey requires one time")
            key_time = key_time[0]
        if key_time is None:
            seconds = oma2.MAnimControl.currentTime().asUnits(om2.MTime.kSeconds)
        else:
            value = float(key_time)
            if not math.isfinite(value):
                raise ValueError("Expected a finite time")
            seconds = om2.MTime(value, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)
        value = (_convert_units(self._mplug, options["value"], to_ui=False)
                 if "value" in options else self.get())
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        # MAnimControlのグローバル接線値はMFnAnimCurveの列挙値と一致しない。
        # 省略した側だけMayaの設定名を照会し、キーの直接更新にはcmdsを使わない。
        tangent_in = (options["inTangentType"] if "inTangentType" in options else
                      cmds.keyTangent(query=True, g=True, inTangentType=True)[0])
        tangent_out = (options["outTangentType"] if "outTangentType" in options else
                       cmds.keyTangent(query=True, g=True, outTangentType=True)[0])
        AnimCurve._tangent_type(tangent_in, incoming=True, key=True)
        AnimCurve._tangent_type(tangent_out, key=True)
        source = self.getSource(skipConversionNodes=False)
        if source is not None:
            if not source.getNode().mnode().hasFn(om2.MFn.kAnimCurve):
                raise NotImplementedError("fast setKey requires a direct animCurve input")
            curve = AnimCurve(source.getNode().mnode())
            if not curve.isTimeInput():
                raise NotImplementedError("fast setKey requires a time-input animCurve")
        else:
            fn = oma2.MFnAnimCurve()
            kind = fn.timedAnimCurveTypeForPlug(self._mplug)
            if kind == oma2.MFnAnimCurve.kAnimCurveUnknown:
                raise NotImplementedError("No supported animation curve for this plug")
            # 値・単位・接線を検証してから初めてシーンへカーブを作成する。
            curve = AnimCurve(fn.create(self._mplug, kind))
        curve.setKey(seconds, value, tangent_in, tangent_out, fast=True)

    def _record_connection_value(self):
        """既存入力定数をUndoへ記録し、接続後のUndoでも元値を復元する。

        未作成の配列要素は実体化しない。数値・単位・enumなど、
        共通の数値操作で表せるものだけを対象にする。
        """
        mp = self._mplug
        current = mp
        while current.isChild or current.isElement:
            if current.isElement:
                if current.logicalIndex() not in current.array().getExistingArrayAttributeIndices():
                    return
                current = current.array()
            else:
                current = current.parent()
        attribute = mp.attribute()
        fn = om2.MFnAttribute(attribute)
        if not fn.writable or fn.isProxyAttribute or mp.isArray:
            return
        # 未初期化matrix/typed、proxyは同値の取得自体が成立しない場合がある。
        # 接続のUndoで定数が失われる数値・単位・enumだけをここで記録する。
        if (attribute.hasFn(om2.MFn.kNumericAttribute) or
                attribute.hasFn(om2.MFn.kUnitAttribute) or
                attribute.hasFn(om2.MFn.kEnumAttribute)):
            self.set(self.get())

    def _set_flags(self, leaf, *, fast=False, **flags):
        """指定階層の末端または自身へフラグを適用する。

        Args:
            leaf: 複合アトリビュートの末端へ適用するか。
            fast (bool): 自身と子の状態更新へ渡す更新経路。
            **flags: 呼出し先へ渡すキーワード引数。
        """
        if leaf and self.isCompound():
            for child in self.getChildren():
                child._set_flags(True, **flags, fast=fast)
        else:
            # Mayaのkeyable/channelBoxのUndo順序を保つ。
            if flags.get("keyable") and self.isChannelBox():
                self.setFlags(channelBox=False, fast=fast)
            if flags.get("channelBox"):
                flags["keyable"] = False
            self.setFlags(**flags, fast=fast)
        return self

    @staticmethod
    def _validate_ui_units(value):
        """UI単位の選択を値の取得・更新前に検証する。

        Args:
            value (bool): 内部単位とUI単位の選択。

        Raises:
            TypeError: bool以外の場合。
        """
        if type(value) is not bool:
            raise TypeError("uiUnits must be bool")

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
        """接続ペアを相手ノードの型で絞り、初出順のPlug/Node一覧へ整える。

        重複統合の後でindexを適用する。ペアでは入力方向でも自身側を先に返す。

        Args:
            pairs (Iterable[tuple[Plug, Plug]]): (自身側, 相手側)の列。
            node_type (str | None): 相手のMayaノード型。Noneは型を絞らない。
            exact (bool): Trueはノード型名の完全一致、Falseは派生型も含める。
            as_pair (bool): Trueは自身側と相手側の組を返す。
            as_node (bool): Trueは相手側だけNodeへ変換する。
            index (int | None): 結果のPython添字。負数も使用できる。
            pcls (type | None): Plugを作り直すクラス。Node化する相手には適用しない。

        Returns:
            list | Plug | Node | tuple | None: 一覧、またはindexで選んだ一件。範囲外はNone。
        """
        result, seen = [], set()
        for local, remote in pairs:
            node = remote.getNode()
            if node_type and not (node.getType() == node_type if exact else node.isType(node_type)):
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

    @contextmanager
    def _temporarily_unlocked_connection_path(self, enabled, *, fast=False):
        """接続先と上位のロックを一時解除し、解除の逆順に再ロックを試みる。

        元からロックされていたPlugだけを復元対象にする。接続編集でnetworked MPlugが
        失効する場合に備え、復元時は保持したアトリビュートパスから参照を取り直す。

        Args:
            enabled (bool): Trueなら自身と上位のロックを一時解除する。
            fast (bool): ロックの解除と復元へ同じ更新経路を渡す。

        Yields:
            None: 接続の編集を行う区間。

        Note:
            解除途中の失敗は解除処理が復元を試みる。編集後の復元失敗はその例外を送出し、
            残りの復元を行わない。編集も失敗していれば、その例外を ``__context__`` に残す。
            接続の変更や値をロールバックするコンテキストではない。
        """
        unlocked = self._unlock_connection_path(fast=fast) if enabled else []
        # networked MPlugは接続変更で失効するため、復元先は変更前のパスを保持し、
        # 復元時に所有ノードから現在の参照を取り直す。
        paths = [self._plug_path(plug.mplug()) for plug in unlocked]
        try:
            yield
        finally:
            for path in reversed(paths):
                self.getNode().getPlug(path).setFlags(locked=True, fast=fast)

    def _unlock_connection_path(self, *, fast=False):
        """自身と上位のロックを一時解除し、復元対象を返す。

        Args:
            fast (bool): ロックの解除と、解除途中で失敗した場合の復元へ渡す更新経路。

        Returns:
            list[Plug]: 実際にロックを解除した参照。上位から自身への順序。
        """
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
                    item.setFlags(locked=False, fast=fast)
                    unlocked.append(item)
        except Exception:
            for item in reversed(unlocked):
                item.setFlags(locked=True, fast=fast)
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
        削除操作をまたいで保持する参照には、mlibのPlugを使う。

        Args:
            mplug (om2.MPlug): 変換対象。

        Returns:
            str: ``<ノードの最短一意名>.<アトリビュートパス>``。

        Raises:
            ValueError: 空の MPlug、所有ノードが削除済み、またはアトリビュートが削除済み(``deleteAttr``)の場合。
        """
        from ..nodes.node import Node
        if mplug.isNull:
            raise ValueError("空の MPlug は指定できません")
        node = mplug.node()
        if not om2.MObjectHandle(node).isValid():
            raise ValueError("削除済みノードの MPlug は指定できません")
        if not Plug._mplug_attribute_exists(mplug, node):
            raise ValueError("削除済みのアトリビュートの MPlug は指定できません")
        return Node._unique_node_name(node) + "." + Plug._plug_path(mplug)

    @staticmethod
    def _deleted_attribute_error(plug):
        """所有ノードが有効なままアトリビュートが削除された Plug の例外を返す(該当しなければ None)。

        Args:
            plug (Plug): 判定する mlib の Plug。

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
        dag_path = owner.getDagPath(0) if mobject.hasFn(om2.MFn.kDagNode) else None
        match = _PLUG_PATH_TOKEN.match(attribute_path.split(".", 1)[0])
        if match is None:
            return None
        first = Plug._find_plug(mobject, match.group(1))
        if first is None:
            # transform の名前でシェイプのアトリビュートを指す場合は、唯一のシェイプで探す。
            if dag_path is None or not mobject.hasFn(om2.MFn.kTransform):
                return None
            shape_path = om2.MDagPath(dag_path)
            try:
                shape_path.extendToShape()
            except RuntimeError:
                return None
            mobject, dag_path = shape_path.node(), shape_path
            first = Plug._find_plug(mobject, match.group(1))
            if first is None:
                return None
        mplug = Plug._attribute_path_plug(mobject, attribute_path, first)
        if mplug is None:
            return None
        return (dag_path if dag_path is not None else mobject), mplug

    @staticmethod
    def _resolve_input(value):
        """対象を mlib の Plug インスタンスへ変換する。

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
        # Nodeとの循環importを避け、所有ノードの解決に使うクラスをここで取得する。
        from ..nodes.node import Node

        if isinstance(value, Plug):
            return value
        if isinstance(value, om2.MPlug):
            if value.isNull:
                raise ValueError("空の MPlug は指定できません")
            return Plug(Node(value.node()), value)
        if not isinstance(value, str):
            raise TypeError(f"Plug、om2.MPlug、またはアトリビュート名を指定してください: {type(value).__name__}")
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
            return Plug(Node(owner), mplug)
        mobject, dag_path = Node._selection_owner(selection, 0, value)
        return Plug(Node(dag_path if dag_path is not None else mobject), mplug)

    def _attribute_exists(self):
        """アトリビュートが所有ノードに存在し続けているか判定する(所有ノードは有効であること)。

        頻繁に呼ばれる :meth:`_require_valid`・:meth:`getFullName` は、呼び出しの負荷を
        避けるため同じ判定を直接書いている(変更する場合はそろえること)。

        Returns:
            bool: 静的アトリビュート、または削除されていない動的アトリビュートの場合は True。
        """
        if self._static_attribute:
            return True
        if not self._attribute_handle.isValid():
            return False
        return self._node._dependency_fn().attributeClass(self._attribute) != _INVALID_ATTRIBUTE

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
        if self._static_attribute:
            return
        # _attribute_exists() と同じ判定。get()/set() のたびに呼ばれるため直接書く。
        fn = node._fn_cache
        if fn is None:
            fn = node._dependency_fn()
        if not self._attribute_handle.isValid() or fn.attributeClass(self._attribute) == _INVALID_ATTRIBUTE:
            raise RuntimeError("削除済みのアトリビュートは扱えません")

    def _range_attribute_fn(self):
        """寿命を検証し、範囲照会に対応する型のFunction Setを返す。

        Returns:
            om2.MFnNumericAttribute | om2.MFnUnitAttribute | None: 数値・単位型の照会先。
                対応しないアトリビュート型はNone。
        """
        self._require_valid()
        attr = self._mplug.attribute()
        if attr.hasFn(om2.MFn.kNumericAttribute):
            return om2.MFnNumericAttribute(attr)
        if attr.hasFn(om2.MFn.kUnitAttribute):
            return om2.MFnUnitAttribute(attr)
        return None

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
        from ..core.fastWrite import writable
        self._require_valid()

        def check(plug):
            """複合の子と既存配列要素だけを確認し、未作成要素を作らない。"""
            writable(plug)
            if plug.isArray:
                for index in plug.getExistingArrayAttributeIndices():
                    check(plug.elementByLogicalIndex(index))
            elif plug.isCompound:
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
        # 循環回避のためここで遅延 import する（mlib で意図的な相互依存の一つ）。
        from ..nodes.node import Node

        return Node(mplug.node())
