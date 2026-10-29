# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya API 2.0 の MPlug をアトリビュートラッパーとして扱う。"""

import math
import re
from contextlib import contextmanager, nullcontext
from functools import partial
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from ..core.attributeType import attributeType, is_internal_data_type, value_reader
from ..core.attributeType import _convert_angles, _convert_units, _plain_angle_unit
from ..core.fastWrite import _ancestor_plugs, require_supported_type, set_attr
from ..core.fastWrite import set_plug
from ..core.object import Object
from ..decorator import _require_bool, _undo_recording, _validated_flags, undoChunk
from ..util import _ArgumentError
from typing import Any, Callable, ContextManager, Iterable, Iterator, Literal
from mlib.nodes.node import Node
from mlib.plugs.multiPlug import MultiPlug
from typing import overload
from typing_extensions import Self

_MULTI_SET_MESSAGE: str
_MULTI_RESET_MESSAGE: str
_PLUG_PATH_TOKEN: Any
_PLUG_PATH_INDEX: Any
MAX_LOGICAL_INDEX: int
_SCALAR_ARRAY_TYPES: frozenset
_LENGTH_PREFIXED_ARRAY_TYPES: frozenset
_INVALID_ATTRIBUTE: Any
_NORMAL_ATTRIBUTE: Any

def _instance_count(multi: om2.MPlug) -> int:
    """ワールド空間アトリビュートがマルチアトリビュートなら、所有 DAG ノードのインスタンス数を返す。

    ``worldMatrix`` などのワールド空間アトリビュートは、インスタンス番号(0～インスタンス数-1)の
    要素を評価前でも存在するものとして扱う(:class:`MultiPlug` と同じ規則)。

    Args:
        multi (om2.MPlug): マルチアトリビュートのプラグ。

    Returns:
        int: 間接インスタンスを含むインスタンス数。ワールド空間アトリビュートでなければ 0。
    """
    ...

def _attribute_class(fn: om2.MFnDependencyNode, attribute_handle: om2.MObjectHandle, attribute: om2.MObject) -> int:
    """アトリビュートが所有ノードに存在するかと、静的なアトリビュートかを判定する。

    ``addAttr`` による動的アトリビュート(``addExtension`` による拡張アトリビュートを含む)は削除でき、削除済みの
    アトリビュートの MPlug で値を読み書きすると Maya が異常終了する。削除は Undo のためにアトリビュートの
    MObject が保持されたままの場合があり、``MObjectHandle.isValid()`` だけでは判定できない
    ため、所有ノードの ``MFnDependencyNode.attributeClass()`` で確かめる(ノードに無いアトリビュートは
    ``kInvalidAttr``)。同じ名前で追加し直したアトリビュートは別のアトリビュートとして扱い、Undo で削除を
    取り消したアトリビュートと名前を変更したアトリビュートは同じアトリビュートのまま。

    Args:
        fn (om2.MFnDependencyNode): 所有ノードの関数セット。ノードが有効(削除済みでない)であること。
        attribute_handle (om2.MObjectHandle): アトリビュートの MObject のハンドル。
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        int: ``MFnDependencyNode`` の ``kNormalAttr`` (静的アトリビュート)・``kLocalDynamicAttr``・
            ``kExtensionAttr``、またはノードに無いアトリビュートの ``kInvalidAttr``。
    """
    ...

def _multi_element_exists(mplug: om2.MPlug) -> bool:
    """プラグ(と経由するマルチアトリビュートの要素)がシーンに存在するか判定する。

    マルチアトリビュートの要素は、マルチアトリビュートの既存の論理番号(``getExistingArrayAttributeIndices()``。
    値を持つ要素と接続された要素)に含まれる場合に存在する。値を読まないため、
    存在しない要素を作らない。

    Args:
        mplug (om2.MPlug): 判定するプラグ。

    Returns:
        bool: プラグと、経由するすべてのマルチアトリビュートの要素が存在する場合は True。
    """
    ...


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

    マルチアトリビュート、登録型、コンパウンドアトリビュートの順でラッパーを選ぶ。参照取得では値を評価せず、
    generic/kAnyは基底Plugのままget時に値を解釈する。
    通常編集はUndo有効時に記録し、対応するfastはUndoなしで直接更新する。

    MayaコマンドへはgetFullName()で文字列化する。名前は改名・親変更に追従する。
    特にMultiPlug・コンパウンドアトリビュートのPlugは、cmdsによるシーケンス展開を避けるため文字列化が必要。
    所有ノードや動的アトリビュートの削除後はisValidがFalse、名前は空文字列になり、
    値の読書き・接続照会・子参照はRuntimeErrorになる。削除をUndoすれば再び有効になる。
    """
    _registry: None
    _reader: None
    def __new__(cls, node: Node, mplug: om2.MPlug) -> Self:
        """マルチアトリビュート・登録アトリビュート型・コンパウンドアトリビュートの順にラッパー型を選ぶ。

        登録アトリビュート型の判定には ``cmds.getAttr(type=True)`` と同じ型名を使う。型名は
        アトリビュート定義から求め(:func:`mlib.core.attributeType.attributeType`)、maya.cmds へ
        問い合わせないため、存在しないマルチアトリビュートの要素の Plug を作っても要素は作られない。
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
                プラグが未確定(-1)の論理番号を経由する場合(``cmp[-1].child`` や
                ``inputTarget[-1].inputTargetGroup`` のような maya.cmds で解決できないプラグ)。
                MPlug の所有ノードが node と異なる場合(静的アトリビュート・動的アトリビュートとも。所有ノードでは
                ない node を渡した誤用)。
        """
        ...
    def __init__(self, node: Node, mplug: om2.MPlug) -> None:
        """所有Nodeを共有し、MPlug参照のコピーとアトリビュートの有効性確認用ハンドルを保持する。

        MPlugをコピーしても参照先は同じシーンのアトリビュートで、値の独立コピーではない。

        Args:
            node (Node): プラグを所有するノードラッパー。
            mplug (om2.MPlug): ラップする Maya API 2.0 のプラグ。

        Returns:
            None: 値を返さない。
        """
        ...
    def __eq__(self, other):
        """生存中の同じアトリビュート参照を比較する。削除済みのAPIへ照会しない。

        Args:
            other: 比較・演算の相手。
        """
        ...
    def __hash__(self):
        """生成時の所有ノードとアトリビュートパスに基づく固定ハッシュを返す。"""
        ...
    def __repr__(self) -> str:
        """デバッグ用に、ラッパーのクラス名と完全修飾プラグ名を含む表現を返す。

        クラス名は ``Plug``, ``MultiPlug``, ``CompoundPlug`` などの実際の型で、マルチアトリビュート全体か
        コンパウンドアトリビュートかを表示から判別できる。

        Returns:
            str: ``MultiPlug('pma.input1D')`` のような文字列表現。所有ノードが無効、またはアトリビュートが
                削除済みなら ``<Plug invalid>`` のようにクラス名を含む無効表示。
        """
        ...
    def __rshift__(self, dst: Plug | om2.MPlug | str) -> Plug:
        """``self >> dst`` で自身から dst へ接続し、接続先を返す(:meth:`connectTo` の通常経路)。

        ``a >> b.x`` は ``a >> (b.x)`` と評価される(属性参照が演算子より優先する)。
        Undo を記録する通常経路のみで、fast 経路は無い。cymel の同名演算子は None を返すが、
        mlib では戻り値を持つ。

        Args:
            dst (Plug | om2.MPlug | str): 接続先。マルチアトリビュート全体は受け付けない(空き要素を選ぶには
                ``self.connectTo(multi, nextAvailable=True)`` を使う)。

        Returns:
            Plug: 実際の接続先(dst を解決した Plug)。

        Raises:
            TypeError: dst が未対応の型の場合。
            RuntimeError: 同一接続・入力済み・ロック・無効な Plug、マルチアトリビュート全体への接続の場合
                (:meth:`connect` と同じ)。
        """
        ...
    def __lshift__(self, src: Plug | om2.MPlug | str) -> Plug:
        """``self << src`` で src から自身へ接続し、自身を返す(:meth:`connect` の通常経路)。

        Args:
            src (Plug | om2.MPlug | str): 接続元。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: src が未対応の型の場合。
            RuntimeError: 同一接続・入力済み・ロック・無効な Plug の場合(:meth:`connect` と同じ)。
        """
        ...
    def __floordiv__(self, dst: Plug | om2.MPlug | str) -> Plug:
        """``self // dst`` で自身から dst への直接接続を解除し、dst を返す(:meth:`disconnect` の通常経路)。

        Args:
            dst (Plug | om2.MPlug | str): 接続先。

        Returns:
            Plug: 解決した接続先 Plug。

        Raises:
            TypeError: dst が未対応の型の場合。
            RuntimeError: 自身から dst への接続が無い、または無効な Plug の場合。
        """
        ...
    def getNode(self) -> Node:
        """この Plug を所有する mlib ノードを取得する。

        Returns:
            Node: 保持する所有Nodeと同じインスタンス。新しいノード参照は作らない。
        """
        ...
    def isValid(self) -> bool:
        """所有ノードとアトリビュートの参照が有効か判定する。

        ロック・接続・アトリビュート定義による読み書きの可否は判定しない。

        Returns:
            bool: 所有ノードが有効で、アトリビュート(動的アトリビュートは ``deleteAttr`` で削除されうる)が
                存在する場合は ``True``。Undo でノード・アトリビュートが戻れば再び ``True`` になる。
        """
        ...
    def mplug(self) -> om2.MPlug:
        """内部で保持するMPlugを、コピーや有効性の再検査をせず返す。

        Returns:
            om2.MPlug: 保持中のAPI参照。アトリビュート値の独立コピーではない。
        """
        ...
    def getName(self) -> str:
        """最短一意ノード名と短いアトリビュート名を含むPlug名を取得する。

        Returns:
            str: 必要な論理番号を含むプラグ名。所有ノードが無効(削除済み)、
                またはアトリビュートが削除済みの場合は空文字列(:meth:`getFullName` と同じ)。
        """
        ...
    def getAttrName(self) -> str:
        """先頭ドットと必要な要素番号を含む短いアトリビュートパスを取得する。

        Returns:
            str: ノード名を除いたPlug名。無効な場合は空文字列。
        """
        ...
    def getShortName(self) -> str:
        """要素番号や階層を含まないアトリビュートの短名。

        Returns:
            str: 要素番号や階層を含まないアトリビュートの短名。
        """
        ...
    def getFullName(self) -> str:
        """maya.cmdsで一意に解決できるプラグ名を取得する。

        ``<Node.getName()の名前>.<アトリビュートパス>`` の形式で、名前変更・親子付け替えに
        追従する。アトリビュートはロング名と必要な論理番号を含み、エイリアスがあれば使う。

        Returns:
            str: 一意なプラグ名。所有ノードやアトリビュートが削除済みなら空文字列。
        """
        ...
    __str__: Any
    def getLongName(self) -> str:
        """基になる Maya アトリビュートのロング名を取得する。

        Returns:
            str: MFnAttribute が返すアトリビュート名。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getNiceName(self) -> str:
        """UI 表示用のニース名を取得する。

        Returns:
            str: Attribute Editor 等で使われる表示名(例: ``translateX`` は
                ``"Translate X"``)。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getType(self) -> str | None:
        """アトリビュート定義からMayaの型名を取得する。値の評価は行わない。

        ``cmds.getAttr(<プラグ名>, type=True)`` と同じ型名(``doubleLinear``・``double3``・
        ``matrix``・``string`` 等)を返す。:meth:`Node.getType` が Maya の nodeType 名を
        返すのと同じ流儀で、Python のラッパークラスは ``type(plug)`` で調べる。

        Returns:
            str | None: 定義上のMaya型名。マルチアトリビュート全体では要素の型名。
                generic/kAny等の値で型が決まるアトリビュートは実値を評価せずNoneを返し、
                値を取得した後もこの規則は変わらない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def isMulti(self) -> bool:
        """マルチアトリビュートか判定する。

        ``isMulti``/``isCompound``/``isMultiElement``/``isChild`` はプラグの構造だけを返すため、
        無効な Plug(:meth:`isValid` が ``False``)でも例外にしない。

        Returns:
            bool: マルチアトリビュートのプラグの場合は ``True``。
        """
        ...
    def isCompound(self) -> bool:
        """コンパウンドアトリビュートか判定する。

        Returns:
            bool: 子プラグを持つ場合は ``True``。
        """
        ...
    def isMultiElement(self) -> bool:
        """マルチアトリビュートの要素プラグか判定する。

        Returns:
            bool: マルチアトリビュートの要素の場合は ``True``。
        """
        ...
    def isChild(self) -> bool:
        """コンパウンドアトリビュートの子プラグか判定する。

        Returns:
            bool: 子プラグの場合は ``True``。
        """
        ...
    def getParent(self) -> Plug | None:
        """コンパウンドアトリビュートの子プラグであれば、その親プラグを取得する。

        Returns:
            Plug | None: 親プラグ。子プラグでない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合
                (子プラグかどうかにかかわらず。削除済みの MPlug は子かどうかを正しく返さないため)。
        """
        ...
    def getMulti(self) -> MultiPlug | None:
        """マルチアトリビュートの要素プラグであれば、そのマルチアトリビュート全体のプラグを取得する。

        Returns:
            MultiPlug | None: マルチアトリビュート全体のプラグ。要素プラグでない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getIndex(self) -> int:
        """マルチアトリビュートの要素プラグの論理番号を取得する。

        Returns:
            int: 要素の論理番号(``multi[index]`` の index。物理的な並び順ではない)。

        Raises:
            TypeError: 要素プラグでない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isKeyable(self) -> bool:
        """チャンネルボックスでキー可能なアトリビュートか判定する。

        setAttr(keyable=...) によるプラグ単位の動的な上書きを反映する
        (アトリビュート定義の既定値だけを見る MFnAttribute.keyable とは異なる)。

        Returns:
            bool: キー可能な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def setKeyable(self, val: bool = ..., leaf: bool = ..., *, fast: bool = ...) -> Plug:
        """キー設定可否を設定する。

        Args:
            val (bool): キー設定可否。
            leaf (bool): コンパウンドアトリビュートの末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        ...
    def setFlags(self, *, locked: bool | None = ..., keyable: bool | None = ..., channelBox: bool | None = ..., fast: bool = ...) -> Plug:
        """アトリビュートの状態をまとめて変更する。省略した状態は変更しない。

        Args:
            locked (bool | None): ロック状態。
            keyable (bool | None): キー設定可否。
            channelBox (bool | None): Channel Box表示。キー可能なアトリビュートはFalseでも表示される。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: 状態がbool/None以外の場合。
            RuntimeError: アトリビュートが無効、またはMayaが更新を拒否した場合。
        """
        ...
    def isChannelBox(self) -> bool:
        """Channel Boxフラグ(keyableによる表示を含まない)。

        Returns:
            bool: Channel Boxフラグ(keyableによる表示を含まない)。
        """
        ...
    def setChannelBox(self, val: bool = ..., leaf: bool = ..., *, fast: bool = ...) -> Plug:
        """Channel Box表示を設定する。

        Args:
            val (bool): 表示状態。有効時はkeyableを無効にする。
            leaf (bool): コンパウンドアトリビュートの末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        ...
    def unlock(self, below: bool = ..., *, fast: bool = ...) -> list[Plug]:
        """上位と必要な下位階層をアンロックする。

        通常は1回のUndoで戻る。fastはOpenMayaで直接更新し、Undoに記録しない。

        Args:
            below (bool): 子階層(コンパウンドアトリビュートの子・マルチアトリビュートの既存要素)も解除する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            list[Plug]: 実際に解除したPlugを上位から返す。解除するものが無ければ空のlist。

        Raises:
            TypeError: belowまたはfastがbool以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def mute(self) -> Plug:
        """現在値でミュートし、自身を返す。

        アニメーション(入力のアニメーションカーブ)の無いチャンネルでは、Mayaが警告を出すだけで
        何もしない(muteノードを作らず、 :meth:`isMuted` はFalseのまま)。例外にはしない。
        fast引数は持たない。

        Returns:
            Plug: 自身。
        """
        ...
    def unmute(self) -> Plug:
        """ミュートを解除し、自身を返す。fast引数は持たない。

        Returns:
            Plug: 自身。
        """
        ...
    def isConnected(self, *, source: bool = ..., destination: bool = ...) -> bool:
        """指定方向の直接の接続を持つか判定する。

        Args:
            source (bool): 入力元からの接続を調べる。
            destination (bool): 出力先への接続を調べる。

        Returns:
            bool: 指定方向に接続を持つ場合は ``True``。両Falseなら ``False``。

        Raises:
            TypeError: 方向指定がboolでない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isSource(self) -> bool:
        """出力接続元か判定する。

        Returns:
            bool: 他のプラグへの出力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isDestination(self) -> bool:
        """入力接続先か判定する。

        Returns:
            bool: 他のプラグからの入力接続を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isHidden(self) -> bool:
        """UI から隠されたアトリビュートか判定する。

        Returns:
            bool: 隠しアトリビュートの場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isDynamic(self) -> bool:
        """動的に追加されたアトリビュート(addAttr によるカスタムアトリビュート等)か判定する。

        Returns:
            bool: 動的アトリビュートの場合は ``True``。静的(ノード型に組み込み)のアトリビュートは ``False``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isReadable(self) -> bool:
        """アトリビュート定義の readable フラグを取得する。

        値の取得が成功することを保証する検査ではない。

        Returns:
            bool: 定義の readable が有効な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isWritable(self) -> bool:
        """アトリビュート定義の writable フラグを取得する。

        ロックや入力接続を含めた現在の編集可否は判定しない。

        Returns:
            bool: 定義の writable が有効な場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isSettable(self) -> bool:
        """Maya標準のsettable照会と同じ基準で、現在値を設定可能か取得する。

        ``maya.cmds.getAttr(settable=True)`` と同じ値を、``MPlug.isFreeToChange()`` で求める
        (自身・親・子のロックと入力接続を反映する)。定義上の writable は判定に含まない
        (cmds と同じく、``worldMatrix`` などの出力アトリビュートも True になる)。
        値の型・範囲や実行時エラーまで含めたset()の成功保証ではない。

        Returns:
            bool: 自身・親・子にロックも入力接続も無い場合は ``True``。

        Raises:
            RuntimeError: 所有ノード・アトリビュートが無効な場合。
        """
        ...
    def isStorable(self) -> bool:
        """シーンファイルへ値が保存されるアトリビュートか判定する。

        Returns:
            bool: 保存対象の場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def hasMin(self) -> bool:
        """最小値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最小値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def hasMax(self) -> bool:
        """最大値制限を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: 最大値制限を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getMin(self, *, unit: str | None = ..., uiUnits: bool = ...) -> float | om2.MAngle | om2.MDistance | om2.MTime | None:
        """設定されている最小値を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクト(``MAngle``/``MDistance``/``MTime``)をそのまま返す。
        既定(``uiUnits=False``)では単位の換算を行わない。

        Args:
            unit (str | None): 指定すると角度の値(MAngle)を ``"deg"`` / ``"rad"`` の数値で返す
                (``"degree"`` 等の別名も可)。既定Noneは単位付きオブジェクトのまま。
                角度以外では使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは :meth:`get` と同じく現在のUI単位(度・cm等)の数値で返す。
                既定Falseは内部の単位付きオブジェクトのまま返す。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最小値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getMax(self, *, unit: str | None = ..., uiUnits: bool = ...) -> float | om2.MAngle | om2.MDistance | om2.MTime | None:
        """設定されている最大値を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクト(``MAngle``/``MDistance``/``MTime``)をそのまま返す。

        Args:
            unit (str | None): 指定すると角度の値(MAngle)を ``"deg"`` / ``"rad"`` の数値で返す
                (``"degree"`` 等の別名も可)。既定Noneは単位付きオブジェクトのまま。
                角度以外では使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは :meth:`get` と同じく現在のUI単位の数値で返す。既定Falseは内部単位のまま。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: 最大値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def hasSoftMin(self) -> bool:
        """ソフト最小値(UIスライダーの下限)を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最小値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def hasSoftMax(self) -> bool:
        """ソフト最大値(UIスライダーの上限)を持つアトリビュートか判定する。

        数値アトリビュート、角度・距離・時間アトリビュートのみ対応する。それ以外は常に ``False``。

        Returns:
            bool: ソフト最大値を持つ場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getSoftMin(self, *, unit: str | None = ..., uiUnits: bool = ...) -> float | om2.MAngle | om2.MDistance | om2.MTime | None:
        """設定されているソフト最小値(UIスライダーの下限)を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Args:
            unit (str | None): 指定すると角度の値(MAngle)を ``"deg"`` / ``"rad"`` の数値で返す
                (``"degree"`` 等の別名も可)。既定Noneは単位付きオブジェクトのまま。
                角度以外では使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは :meth:`get` と同じく現在のUI単位の数値で返す。既定Falseは内部単位のまま。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最小値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getSoftMax(self, *, unit: str | None = ..., uiUnits: bool = ...) -> float | om2.MAngle | om2.MDistance | om2.MTime | None:
        """設定されているソフト最大値(UIスライダーの上限)を取得する。

        数値アトリビュートは ``float``、角度・距離・時間アトリビュートは対応する Maya API 2.0 の
        単位付きオブジェクトをそのまま返す。min/max とは異なり値の入力自体は制限しない。

        Args:
            unit (str | None): 指定すると角度の値(MAngle)を ``"deg"`` / ``"rad"`` の数値で返す
                (``"degree"`` 等の別名も可)。既定Noneは単位付きオブジェクトのまま。
                角度以外では使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは :meth:`get` と同じく現在のUI単位の数値で返す。既定Falseは内部単位のまま。

        Returns:
            float | om2.MAngle | om2.MDistance | om2.MTime | None: ソフト最大値。
                制限が無い、または対応しないアトリビュート型では ``None``。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getDefault(self, *, unit: str | None = ..., uiUnits: bool = ...) -> Any:
        """アトリビュートの既定値を取得する。

        数値アトリビュートは ``float``/``bool``/``int``、角度・距離・時間アトリビュートは対応する Maya API 2.0
        の単位付きオブジェクト、enum アトリビュートは ``int`` をそのまま返す。
        scale・double3・float3のような数値のコンパウンドアトリビュートは、子の既定値の ``tuple``
        (例 ``(1.0, 1.0, 1.0)``)を返す。

        Args:
            unit (str | None): 指定すると角度の値(MAngle)を ``"deg"`` / ``"rad"`` の数値で返す
                (``"degree"`` 等の別名も可)。既定Noneは単位付きオブジェクトのまま。
                角度以外では使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは :meth:`get` と同じく現在のUI単位(度・cm等)の数値で返す
                (コンパウンドアトリビュートは子ごとに換算したtuple)。既定Falseは内部単位のまま。

        Returns:
            object | None: 既定値。対応しないアトリビュート型(文字列・message・マトリクス・
                数値以外の汎用のコンパウンドアトリビュートなど)では ``None``。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getAlias(self) -> str | None:
        """このプラグに設定されているエイリアス名を取得する。

        Returns:
            str | None: エイリアス名。設定されていない場合は ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def setAlias(self, name: str | None = ..., *, fast: bool = ...) -> Plug:
        """別名を設定または解除する。

        Args:
            name (str | None): 別名。Noneまたは空文字で解除。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        ...
    def setKey(self, *, fast: bool = ..., **kwargs) -> Plug:
        """対象アトリビュートへキーを設定する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。
            **kwargs: Maya setKeyframeのフラグ。値・時間はMayaのUI単位。
                fastは単一のtime/t・value/v・inTangentType/itt・outTangentType/ottのみ。
                レイヤー、範囲、コンパウンドアトリビュートの入力等は更新前に拒否する。
                接線省略時はMayaのグローバル設定を使う。fastの入力stepはautoへ補正し、
                入力stepnextはNotImplementedError、fixed/global/未知型はValueErrorで
                カーブを生成・変更する前に拒否する。

        Returns:
            Plug: 自身。
        """
        ...
    def getAnimLayers(self, selected: bool = ..., exact: bool = ...) -> list[str]:
        """入力チェーンのアニメーションレイヤー名を上位から取得する。

        Args:
            selected (bool): 選択レイヤーに限定する。
            exact (bool): selected時にベースレイヤーも選択状態で絞る。

        Returns:
            list[str]: レイヤー名。最後に条件に合うベースレイヤーを含む。
        """
        ...
    def getEnumName(self, value: int | None = ...) -> str:
        """enum アトリビュートの値に対応するフィールド名を取得する(:meth:`getEnumValue` の逆引き)。

        Args:
            value (int | None): 名前を調べる enum 値。既定の None は現在値(``get()``)を使う。
                bool は受け付けない。

        Returns:
            str: 値に対応するフィールド名。

        Raises:
            TypeError: enum アトリビュートでない、または value が None・整数以外の場合。
            ValueError: 値に対応するフィールドが無い場合(``a=1:b=5`` で3を指定した場合など、欠番の値)。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def getEnumNames(self) -> list[tuple[str, int]]:
        """enum アトリビュートの全フィールドを ``(名前, 値)`` の組で値の昇順に取得する。

        ``a=1:b=5`` のような欠番のある定義では、フィールドのある値だけを含む。

        Returns:
            list[tuple[str, int]]: ``(フィールド名, enum 値)`` の新しい list。値の昇順。

        Raises:
            TypeError: enum アトリビュートでない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def setEnumNames(self, names: Iterable[str], *, fast: bool = ...) -> Plug:
        """enumアトリビュートの表示名を指定順に更新する。

        Args:
            names (Iterable[str]): 値0から順に対応する空でない名前列。
                API 2.0は既存enumフィールドの削除を公開しないためfast=Trueは未対応。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            Plug: 更新した自身。

        Raises:
            TypeError: enumアトリビュートでない、名前が文字列でない、またはfastがbool以外の場合。
            ValueError: 空の列、空の名前、区切り文字を含む名前の場合。
            RuntimeError: アトリビュートが無効、またはMayaが変更を拒否した場合。
            NotImplementedError: fast=Trueの場合。変更前に拒否する。
        """
        ...
    def getEnumValue(self, name: str) -> int:
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
        ...
    def isLocked(self) -> bool:
        """プラグがロックされているか判定する。

        Returns:
            bool: ロックされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def setLocked(self, val: bool = ..., leaf: bool = ..., *, fast: bool = ...) -> Plug:
        """ロックを設定する。

        Args:
            val (bool): ロック状態。
            leaf (bool): コンパウンドアトリビュートでは末端だけを設定する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            Plug: 自身。
        """
        ...
    def isMuted(self) -> bool:
        """アトリビュートがミュートされているか判定する。

        Returns:
            bool: ミュートされている場合は ``True``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def setMuted(self, state: bool) -> Plug:
        """ミュート状態を設定する。Trueは現在値で固定し、Falseは解除する。

        アニメーションの無いチャンネルへのTrueは、Mayaが警告を出すだけで何もしない
        (muteノードを作らず、 :meth:`isMuted` はFalseのまま)。例外にはせず自身を返す。
        コンパウンドアトリビュートは入力接続のある子だけを対象にする(``cmds.mute`` と同じ)。
        ``cmds.mute`` でUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            state (bool): ミュートする場合はTrue。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: stateがbool以外の場合。
            RuntimeError: 所有ノード・アトリビュートが無効、またはMayaが更新を拒否した場合。
        """
        ...
    def delete(self, force: bool = ..., *, fast: bool = ...) -> None:
        """このアトリビュートをノードから削除する。

        動的に追加されたアトリビュート(addAttr によるカスタムアトリビュート)にのみ使用できる。
        静的(ノード型に組み込み)のアトリビュートを削除しようとすると Maya が拒否する。
        接続がある場合は force に関わらず Maya が自動的に切断してから削除する。

        Args:
            force (bool): True の場合、ロックされていれば一時的に解除してから
                削除する。False でロックされているアトリビュートを削除しようとすると
                RuntimeError になる。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: force=False でロックされている場合や、静的アトリビュートの
                削除を試みた場合など、Maya が削除を拒否した場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def get(self, *, unit: str | None = ..., uiUnits: bool = ...) -> Any:
        """現在の評価値を取得する。値はキャッシュしない。

        角度アトリビュート(doubleAngle等。rotateX・jointOrientの子など)の数値は既定で度、
        距離はcm、時間は秒で返す。角度のコンパウンドアトリビュートは子ごとに換算する。
        rotateのEulerRotateのように自身の単位を持つ値は換算しない(内部はrad)。

        Args:
            unit (str | None): 数値の角度の単位。None(既定)と ``"deg"`` / ``"degree"`` /
                ``"degrees"`` は度、``"rad"`` / ``"radian"`` / ``"radians"`` はラジアン。
                角度以外のアトリビュートでは使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは単位付き数値を現在のUI単位へ換算する。既定Falseは角度が度
                (unitの指定に従う)、距離cm、時間秒。

        Returns:
            object: 型に応じた値。CompoundPlug.getは子の定義順tuple、MultiPlug.getは
                論理番号をキーとするdict。API読取の型付き配列はlistで、各要素は
                vectorArray=XYZ、pointArray=XYZW、matrixArray=16成分のtuple。
                未初期化データはNone、空配列は空list。generic/kAnyは現在値に応じて
                Matrix・数値・tuple等を返す。マトリクス・型付き配列の成分と無単位値は換算しない。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 参照が無効、または値を読み取れない場合。

        Note:
            まだ作られていないマルチアトリビュートの要素(``multi[9]`` のように参照しただけの要素)を読むと、
            ``cmds.getAttr`` と同じくMayaがその要素を作る(以後 ``getIndices()`` に現れる)。
            参照の取得だけでは要素を作らない。
        """
        ...
    def set(self, value: object, safe: bool = ..., *, unit: str | None = ..., uiUnits: bool = ..., fast: bool = ...) -> Plug | int:
        """値を設定する。ロック解除や接続解除、自動ロールバックは行わない。

        通常はcmds.setAttrで更新し、Undo有効時に記録する。
        safeは本体のRuntimeError/TypeError/ValueErrorを失敗数へ変換し、
        コンパウンドアトリビュートの値の失敗は子ごとに再試行する。成功した子の更新は残る。

        Args:
            value (object): 設定する値。角度の数値は既定で度(unitで変更)、距離cm、時間秒。
                EulerRotate・Quaternion・MAngleのように自身の単位を持つ値は換算しない。
            safe (bool): Trueは対応する失敗を数える。既定Falseは例外を送出する。
            unit (str | None): 数値の角度の単位。None(既定)と ``"deg"`` / ``"degree"`` /
                ``"degrees"`` は度、``"rad"`` / ``"radian"`` / ``"radians"`` はラジアン。
                角度以外のアトリビュートでは使わない。uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): Trueは現在のUI単位の数値入力。既定Falseは角度が度(unitの指定に従う)、
                距離cm、時間秒。
            fast (bool): Trueは対応型をOpenMayaで直接更新する。Undoへ記録せず、Undo設定も変更しない。
                入力の意味と検証は通常経路と同じ(整数型・enum・boolへの小数は四捨五入、
                数値型への文字列や文字列型への数値はRuntimeError)。

        Returns:
            Plug | int: 通常は自身。safe=Trueは成功なら0、子の再試行では失敗数の合計。
                無効参照・分解不能な入力・再試行を完了できない失敗は1。
                厳密な未更新成分の総数は保証しない。

        Raises:
            TypeError: fastがbool以外、またはマルチアトリビュート全体への設定。safe=Trueでも拒否する。
                safe=Falseでunitが文字列・None以外、または不正な入力の場合も送出する。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueの同時指定(safe=Trueでは1を返す)。
                safe=Falseで値の変換等に失敗した場合。
            RuntimeError: safe=Falseで無効参照・ロック・入力接続等により書けない場合。
            NotImplementedError: fast未対応型(messageなど)。ロック等の書込み可否より先に検査し、
                safe=Trueでも部分更新前に拒否する。

        Note:
            fastは値や書込み可否より先に、全子の型対応を確認する。
            呼出し形式の誤りや、上記以外の例外を一律には抑制しない。
        """
        ...
    def setIfChanged(self, value: bool | int | float | str, *, unlock: bool = ..., fast: bool = ...) -> bool:
        """現在のスカラー値と異なる場合だけ書き込み、更新の有無を返す。

        getで現在値を取得してPythonの等価比較を行う。同値なら書込み可否の検証や
        ロック変更をせずFalseを返す。異なる場合はsetへ委譲し、失敗は例外にする。

        Args:
            value (bool | int | float | str): 比較・設定する値。数値は許容誤差なしで比較し、
                単位は :meth:`get` / :meth:`set` の既定(角度は度、距離cm、時間秒)。
            unlock (bool): Trueで対象自身のロックを一時解除し、値更新の成否にかかわらず
                再ロックを試みる。親のロックや入力接続は解除しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。内側のset/状態更新にも同じ値を渡す。

        Returns:
            bool: 更新に成功した場合はTrue。同値のため書き込まなかった場合はFalse。

        Raises:
            TypeError: スカラー以外を指定した場合。
            RuntimeError: Mayaがアトリビュート更新を拒否した場合。

        Note:
            通常は値とロックの更新をUndoが有効なら同じチャンクへ記録する。
            fastはUndo設定を変更せず、更新済みの値の自動ロールバックは行わない。
        """
        ...
    def reset(self, *, fast: bool = ...) -> Plug:
        """数値・単位・enumアトリビュートを定義上の既定値へ戻す。

        単位アトリビュートの既定値を内部単位(cm/rad/秒)へ換算し、``unit="rad"`` でsetへ渡す。
        コンパウンドアトリビュートは定義順に子を更新し、途中で失敗したら例外を送出する。
        全子の事前検証や、成功した子の自動ロールバックは行わない。
        接続の切断やロック解除はしない。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 自身。通常はUndoが有効なら子の変更を同じチャンクへ記録する。
                fastは子へも引数で渡し、Undoへ記録しない。

        Raises:
            TypeError: マルチアトリビュート全体・文字列・messageなど既定値を扱えないアトリビュートの場合。
            RuntimeError: ロック・入力接続などで変更できない場合。enumの既定値がフィールドの
                最小〜最大の外にある場合(``a=1:b=5`` の既定値0など)も、Mayaの設定どおり
                書込みを拒否してRuntimeErrorになる(値は変えない)。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ...
    @overload
    def getSource(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[True], **kwargs: Any) -> tuple[Plug, Node] | None: ...
    @overload
    def getSource(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[False] = ..., **kwargs: Any) -> tuple[Plug, Plug] | None: ...
    @overload
    def getSource(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[True], **kwargs: Any) -> Node | None: ...
    @overload
    def getSource(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[False] = ..., **kwargs: Any) -> Plug | None: ...
    @overload
    def getSource(self, *, skipConversionNodes: bool = ..., **kwargs) -> Plug | Node | tuple | None:
        """直接の入力元を取得する。子・マルチアトリビュートの要素の独立接続は展開しない。

        Args:
            skipConversionNodes (bool): 既定TrueはunitConversion系を省略する。
                Falseは直結したPlug。getConnectionsの既定とは異なる。
            **kwargs: getConnectionsの型・ペア・Node化等の指定。子/要素展開は無効、indexは0に固定。

        Returns:
            Plug | Node | tuple | None: 既定は入力元Plug。未接続や型条件不一致はNone。
                asPairは(自身側Plug, 入力元)、asNodeは相手Node。値や接続は変更しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[True], index: int, **kwargs: Any) -> tuple[Plug, Node] | None: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[True], index: None = ..., **kwargs: Any) -> list[tuple[Plug, Node]]: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[False] = ..., index: int, **kwargs: Any) -> tuple[Plug, Plug] | None: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[True], asNode: Literal[False] = ..., index: None = ..., **kwargs: Any) -> list[tuple[Plug, Plug]]: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[True], index: int, **kwargs: Any) -> Node | None: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[True], index: None = ..., **kwargs: Any) -> list[Node]: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[False] = ..., index: int, **kwargs: Any) -> Plug | None: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., asPair: Literal[False] = ..., asNode: Literal[False] = ..., index: None = ..., **kwargs: Any) -> list[Plug]: ...
    @overload
    def getDestinations(self, *, skipConversionNodes: bool = ..., **kwargs) -> list | Plug | Node | tuple | None:
        """直接の出力先を取得する。子・マルチアトリビュートの要素の独立接続は展開しない。

        Args:
            skipConversionNodes (bool): 既定TrueはunitConversion系を省略する。Falseは直結したPlug。
            **kwargs: getConnectionsの型・ペア・Node化・index等の指定。子/要素展開は無効。

        Returns:
            list | Plug | Node | tuple | None: 既定は出力先Plugのlist、未接続は空list。
                asPairは(自身側Plug, 出力先)、asNodeは相手Node。
                indexは絞込み・重複統合後の一件を選び、範囲外はNone。値や接続は変更しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[True], checkChildren: bool = ..., checkElements: bool = ..., index: int) -> tuple[Plug, Node] | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[True], checkChildren: bool = ..., checkElements: bool = ..., index: None = ...) -> list[tuple[Plug, Node]]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[False] = ..., checkChildren: bool = ..., checkElements: bool = ..., index: int) -> tuple[Plug, Plug] | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[False] = ..., checkChildren: bool = ..., checkElements: bool = ..., index: None = ...) -> list[tuple[Plug, Plug]]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[True], checkChildren: bool = ..., checkElements: bool = ..., index: int) -> Node | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[True], checkChildren: bool = ..., checkElements: bool = ..., index: None = ...) -> list[Node]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[False] = ..., checkChildren: bool = ..., checkElements: bool = ..., index: int) -> Plug | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[False] = ..., checkChildren: bool = ..., checkElements: bool = ..., index: None = ...) -> list[Plug]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., asPair: bool = ..., asNode: bool = ..., checkChildren: bool = ..., checkElements: bool = ..., index: int | None = ...) -> list | Plug | Node | tuple | None:
        """接続参照を取得する。既定は変換ノードを省略しない。

        自身の入力・出力、次にマルチアトリビュートの既存要素または子へ再帰する。
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
            checkChildren (bool): コンパウンドアトリビュートの子も探索する。
            checkElements (bool): マルチアトリビュートの既存要素も探索する。
            index (int | None): 絞込み後のPythonの位置番号。負数可、範囲外はNone。

        Returns:
            list | Plug | Node | tuple | None: 既定は相手Plugのlist。index指定時は一件またはNone。
                重複は通常は相手Plug単位、asNodeは相手Node単位、asPairは自身側も含めて統合する。
                値やノードの複製は行わない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        ...
    def getAnimCurve(self) -> Node | None:
        """このプラグに直接接続された animCurve ノードを取得する。

        pairBlend やアニメーションレイヤーを介した間接的な animCurve は解決しない
        (直接の入力接続だけを対象とする)。

        Returns:
            Node | None: 接続されている animCurve ノード。無ければ ``None``。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def isConnectedTo(self, other: Plug | om2.MPlug | str, *, source: bool = ..., destination: bool = ...) -> bool:
        """指定したプラグと接続されているか判定する。

        既定では入力・出力いずれの向きでも一致すれば True を返す。
        子・マルチアトリビュートの要素の独立した接続や変換ノードの先の接続は展開しない。

        Args:
            other (Plug | om2.MPlug | str): 判定対象のプラグ。文字列は
                ``"node.attribute"`` 形式のアトリビュート名。
            source (bool): otherから自身への入力接続を調べる。
            destination (bool): 自身からotherへの出力接続を調べる。

        Returns:
            bool: 指定方向で接続されている場合は True。両Falseなら False。

        Raises:
            TypeError: other が Plug・MPlug・アトリビュート名のいずれでもない場合、または文字列が
                アトリビュートを指していない場合。方向指定がboolでない場合。
            ValueError: other が空文字列、または空の MPlug の場合。
            RuntimeError: 自身の所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
                other の文字列を解決できない(存在しない、または複数のアトリビュートに一致する)場合、
                other のPlugまたはMPlugの所有ノード・アトリビュートが削除済みの場合。
        """
        ...
    def connect(self, source: Plug | om2.MPlug | str, force: bool = ..., f: bool = ..., lock: bool = ..., l: bool = ..., nextAvailable: bool = ..., na: bool = ..., *, unlock: bool = ..., fast: bool = ...) -> Plug:
        """srcから自身へ接続し、接続先を返す。同一の既存接続も例外にする。

        通常はcmds.connectAttrでUndo有効時に記録する。fastはMDGModifierを使う。
        解除したロックは逆順に復元するが、復元失敗では例外になり残りを復元しない。
        接続済みの変更は、後続の失敗だけでは自動で戻さない。

        Args:
            source (Plug | om2.MPlug | str): 接続元。
            force (bool): 既存入力を置換する。unlock=Trueなら接続先と上位のコンパウンドアトリビュート・マルチアトリビュートを一時解除する。
                接続元のロックは変更しない。
            f (bool): forceとORする。
            lock (bool): 接続後にロックする。Falseでも元のロックは復元する。
            l (bool): lockとORする。
            nextAvailable (bool): マルチアトリビュート全体では0から入力/ロックのない要素を探す。
                コンパウンドアトリビュートの子も判定する。定数値や出力接続がある要素も候補になる。
            na (bool): nextAvailableとORする。
            unlock (bool): Falseならforceでもロックを解除しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 実際の接続先。nextAvailable時は選んだ要素。参照を取り直す場合があり、self同一性は保証しない。

        Raises:
            TypeError: 接続元が未指定・未対応型、またはfastがbool以外の場合。
            RuntimeError: 同一接続・forceなしの入力置換・ロック・接続やロック復元の失敗。
                接続元・接続先の所有ノードやアトリビュートが削除済みの場合も、何も変更せずに
                送出する(接続元は削除前のアトリビュートパスを文言に含める)。
        """
        ...
    def disconnectInput(self, *, fast: bool = ...) -> Plug:
        """直接の入力だけを解除する。未接続なら何もせず自身を返す。

        変換ノードを飛ばさずに現在の入力を調べ、disconnectへ委譲する。
        子/マルチアトリビュートの要素の独立接続は展開せず、ロックも一時解除しない。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 自身。disconnectの単件返却である入力元ではない。

        Raises:
            RuntimeError: 無効な参照、またはロック等により切断できない場合。
        """
        ...
    def disconnect(self, source: Plug | om2.MPlug | str | None = ..., force: bool = ..., f: bool = ..., nextAvailable: bool = ..., na: bool = ..., *, fast: bool = ...) -> Plug | list[Plug]:
        """指定入力元との直接接続を解除する。子接続へ再帰せず、変換ノードも飛ばさない。

        通常はcmds.disconnectAttrでUndo有効時に記録し、fastはMDGModifierを使う。
        変換ノードは削除しない。ロック復元の失敗は例外で打ち切り、完了済みの切断は戻さない。

        Args:
            source (Plug | om2.MPlug | str | None): 入力元。省略またはNoneは現在の直接入力。
            force (bool): 接続先と上位を一時解除し、逆順に再ロックする。入力元のロックは変えない。
            f (bool): forceとORする。
            nextAvailable (bool): マルチアトリビュート内でsrcへ直結した既存要素を全て解除する。src明示時だけ有効。
            na (bool): nextAvailableとORする。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug | list[Plug]: 単一切断は切断した入力元Plug(自身ではない)。srcを渡した場合は
                そのPlug(Plugならそのオブジェクト、MPlug・名前なら解決したPlug)、省略した場合は
                切断前に現在の直接入力として取得したPlugを返し、名前から取り直さない。
                接続由来(networked)のMPlugを持つ場合は、切断前に同じアトリビュートを指す
                非networkedのMPlugへ持ち替える(自身も同様。切断後も安全に比較・使用できる)。
                マルチアトリビュートの検索は接続先要素のlist。

        Raises:
            TypeError: sourceがbool等の未対応型、またはfastがbool以外の場合。
            RuntimeError: 入力・指定接続がない、または切断やロック復元に失敗した場合。

        Note:
            マルチアトリビュートの検索は既存順に切断し、後半の失敗でも先行する切断は戻さない。
            未接続時に何もしない入力解除は :meth:`disconnectInput` を使う。
        """
        ...
    def disconnectAll(self, *, source: bool = ..., destination: bool = ..., fast: bool = ...) -> Plug:
        """入力、次に出力の直接接続を解除する。ロックは解除しない。

        子・マルチアトリビュートの要素の独立接続は展開せず、変換ノードも削除しない。
        通常はUndo有効時に同じチャンクへ記録する。途中失敗で完了済みの切断は戻さない。

        Args:
            source (bool): 入力を解除する。既定True。
            destination (bool): 全出力を解除する。既定True。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 自身。未接続または両Falseなら変更しない。

        Raises:
            TypeError: 方向・fastがbool以外の場合。
            RuntimeError: 無効参照、またはロック等により切断できない場合。
        """
        ...
    def connectTo(self, destination: Plug | om2.MPlug | str, *, fast: bool = ..., **kwargs) -> Plug:
        """自身からdstへ接続し、接続先Plugを返す。

        dstをPlugへ解決し、 ``destination.connect(self, **kwargs)`` へ委譲する。
        通常Undo・force時のロック復元・マルチアトリビュートの空き番号選択はconnectと共通。
        fast指定は内側のconnectへ引数で渡す。

        Args:
            destination (Plug | om2.MPlug | str): 接続先。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。未対応操作は更新前に拒否。
            **kwargs: connectのforce/f・lock/l・nextAvailable/na・unlock。

        Returns:
            Plug: 実際の接続先。
        """
        ...
    def _set_template(self, value: object, safe: bool, *, fast: bool, unit: str | None = ..., uiUnits: bool = ..., _writer: Callable[..., Any] | None = ..., **options) -> Plug | int:
        """set()の共通骨格。Undo文脈・マルチアトリビュート全体の拒否・fast未対応型の事前検査・safeの例外吸収を担う。

        派生クラスは値の書込み本体 :meth:`_set_value` と、safeの再試行 :meth:`_set_children_safely`
        だけをoverrideする。Undoチャンク名は ``mlib<クラス名>Set``。

        Args:
            value (object): 書き込む値。
            safe (bool): Trueは対応する失敗を数える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            unit (str | None): 数値の角度の単位。Noneは度。ここで一度だけラジアンへ換算し、
                書込み本体とsafeの再試行には内部単位の値を渡す。
            uiUnits (bool): TrueはUI単位の数値。unitとは同時に指定できない。
            _writer (callable | None): 内部専用。値の書込みに使う関数(既定は自身の ``_set_value``)。
                Transform が Double3 の回転変換を通さずに基底の書込みを使うときに ``Plug._set_value`` を渡す。
            **options: ``_set_value`` と ``_set_children_safely`` へ渡す追加指定。

        Returns:
            Plug | int: safe=Falseは自身。safe=Trueは成功0、または失敗数。

        Raises:
            TypeError: fastがbool以外、またはマルチアトリビュート全体への設定。safe=Trueでも拒否する。
                safe=Falseでunitが文字列・None以外の場合も送出する。
            ValueError: safe=Falseでunitが未対応、またはunitとuiUnits=Trueを同時に指定した場合。
                safe=Trueではいずれも書込み前の失敗として1を返す。
            NotImplementedError: fast未対応型。safe=Trueでも拒否する。
        """
        ...
    def _set_value(self, value: object, *, uiUnits: bool = ..., fast: bool = ...) -> None:
        """値の型と単位を揃え、指定した更新経路へ書き込む。

        safeの再試行とUndoチャンクは呼出し元で扱う。

        Args:
            value (object): 書き込む値。
            uiUnits (bool): TrueならUI単位から内部単位へ変換する。
            fast (bool): TrueならOpenMayaで直接更新する。

        Returns:
            None: 値を返さない。
        """
        ...
    def _set_children_safely(self, value: object, *, uiUnits: bool = ..., fast: bool = ...) -> int:
        """失敗したコンパウンドアトリビュートの値を子の定義順で再試行し、失敗数を返す。

        分解できない入力や再試行を完了できない失敗は1とし、更新済みの子は戻さない。

        Args:
            value (object): 最初の設定へ渡した値。
            uiUnits (bool): 子のsetへ渡す単位指定。
            fast (bool): 子のsetへ渡す更新経路。

        Returns:
            int: 子の失敗数、または分解できない失敗を表す1。
        """
        ...
    def _get_value(self) -> Any:
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
                そのタプルを返す(cmds.getAttr フォールバック時のみ該当)。
                文字列、数値、配列、None など実際のアトリビュート型に依存する。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合
                (:meth:`isValid` が ``False``。削除前の古い値を返さない)。
                Maya 内部のデータ型(nurbsSurface の ``patchUVIds`` など)の、存在しない
                マルチアトリビュートの要素の場合(値を読むと Maya が異常終了する場合があるため。
                :func:`mlib.core.attributeType.is_internal_data_type`)。
        """
        ...
    def _set_key_direct(self, kwargs: dict) -> None:
        """単一時刻のキー設定だけをAPI 2.0で実行する。

        Args:
            kwargs (dict): value/timeと入出力接線型。長名とMaya短名を受け付ける。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 明示的なfixed・global・未知の接線型を指定した場合。
            NotImplementedError: 範囲・レイヤー・非時間カーブ等の場合。生成前に拒否。
                入力stepnextもMayaの版で補正が異なるため生成前に拒否する。
        """
        ...
    def _record_connection_value(self):
        """既存入力定数をUndoへ記録し、接続後のUndoでも元値を復元する。

        未作成のマルチアトリビュートの要素は実体化しない。数値・単位・enumなど、
        共通の数値操作で表せるものだけを対象にする。
        Undoが無効なら記録されないため、同値の書込み自体を省く。
        """
        ...
    def _set_flags(self, leaf, *, fast: bool = ..., **flags):
        """指定階層の末端または自身へフラグを適用する。

        Args:
            leaf: コンパウンドアトリビュートの末端へ適用するか。
            fast (bool): 自身と子の状態更新へ渡す更新経路。
            **flags: 呼出し先へ渡すキーワード引数。
        """
        ...
    @staticmethod
    def _connection_results(pairs: Iterable[tuple[Plug, Plug]], node_type: str | None, exact: bool, as_pair: bool, as_node: bool, index: int | None) -> list | Plug | Node | tuple | None:
        """接続ペアを相手ノードの型で絞り、初出順のPlug/Node一覧へ整える。

        重複統合の後でindexを適用する。ペアでは入力方向でも自身側を先に返す。

        Args:
            pairs (Iterable[tuple[Plug, Plug]]): (自身側, 相手側)の列。
            node_type (str | None): 相手のMayaノード型。Noneは型を絞らない。
            exact (bool): Trueはノード型名の完全一致、Falseは派生型も含める。
            as_pair (bool): Trueは自身側と相手側の組を返す。
            as_node (bool): Trueは相手側だけNodeへ変換する。
            index (int | None): 結果のPythonの位置番号。負数も使用できる。

        Returns:
            list | Plug | Node | tuple | None: 一覧、またはindexで選んだ一件。範囲外はNone。
        """
        ...
    def _temporarily_unlocked_connection_path(self, enabled: bool, *, fast: bool = ...) -> ContextManager[None]:
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
        ...
    def _unlock_connection_path(self, *, fast: bool = ...) -> list[Plug]:
        """自身と上位のロックを一時解除し、復元対象を返す。

        Args:
            fast (bool): ロックの解除と、解除途中で失敗した場合の復元へ渡す更新経路。

        Returns:
            list[Plug]: 実際にロックを解除した参照。上位から自身への順序。
        """
        ...
    @staticmethod
    def _plug_path(mplug: om2.MPlug) -> str:
        """ノード名を除いた、maya.cmds で解決できるアトリビュートパスを返す。

        ロング名と、必要な論理番号(``worldMatrix[0]``、``pnts[2].pntx`` 等)・
        インスタンス番号を含み、エイリアスがあればエイリアス名を使う
        (``MPlug.name()`` のアトリビュート部分と同じ表記)。

        Args:
            mplug (om2.MPlug): 対象のプラグ。

        Returns:
            str: ``translateX`` や ``worldMatrix[0]`` のようなアトリビュートパス。
        """
        ...
    @staticmethod
    def _mplug_attribute_exists(mplug: om2.MPlug, node: om2.MObject | None = ...) -> bool:
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
        ...
    @staticmethod
    def _mplug_name(mplug: om2.MPlug) -> str:
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
        ...
    @staticmethod
    def _deleted_attribute_error(plug: Plug) -> DeletedAttributeError | None:
        """所有ノードが有効なままアトリビュートが削除された Plug の例外を返す(該当しなければ None)。

        Args:
            plug (Plug): 判定する mlib の Plug。

        Returns:
            DeletedAttributeError | None: アトリビュートが ``deleteAttr`` で削除済みなら送出する例外。
                所有ノードが削除済みの場合(無効な所有ノードとして扱う)と、有効な Plug は None。
        """
        ...
    @staticmethod
    def _find_plug(mobject: om2.MObject, name: str) -> om2.MPlug | None:
        """ノードのアトリビュート名(ロング名・ショート名・エイリアス)から MPlug を求める。

        ``MFnDependencyNode.findPlug()`` はエイリアスを解決しないため、見つからない場合は
        エイリアスの一覧(``bs.smile`` → ``weight[0]`` など)からアトリビュートパスを求めて解決する。

        Args:
            mobject (om2.MObject): 所有ノード。
            name (str): アトリビュート名。

        Returns:
            om2.MPlug | None: プラグ。アトリビュートが無い場合は None。
        """
        ...
    @staticmethod
    def _has_out_of_range_index(attribute_path: str) -> bool:
        """アトリビュートパスが :data:`MAX_LOGICAL_INDEX` を超える論理番号を含むか判定する。

        Args:
            attribute_path (str): ノード名を含まないアトリビュートパス(``input1D[4294967296]`` など)。

        Returns:
            bool: 範囲外の番号を含む場合は True。
        """
        ...
    @staticmethod
    def _has_unresolved_index(mplug: om2.MPlug) -> bool:
        """論理番号が未確定(-1)のマルチアトリビュートの要素を経由するプラグか判定する。

        ``findPlug("input3Dx")`` のようにマルチアトリビュートであるコンパウンドアトリビュートの子を要素を指定せずに取得すると
        ``input3D[-1].input3Dx`` のようなプラグになり、maya.cmds では解決できない。

        Args:
            mplug (om2.MPlug): 判定するプラグ。

        Returns:
            bool: 未確定の番号を含む場合は True。
        """
        ...
    @staticmethod
    def _attribute_path_plug(mobject: om2.MObject, attribute_path: str, first: om2.MPlug | None = ...) -> om2.MPlug | None:
        """ノードとアトリビュートパス(``input1D[3]``、``pnts[2].pntx`` など)から MPlug を求める。

        ``.`` で区切った各区切りのアトリビュート名(ロング名・ショート名。先頭はエイリアスも可)と
        ``[i]`` の論理番号を順に辿る。存在しないマルチアトリビュートの要素もプラグとして返し、
        要素は作らない(シーンを変更しない)。

        Args:
            mobject (om2.MObject): 所有ノード。
            attribute_path (str): ノード名を含まないアトリビュートパス。
            first (om2.MPlug | None): 先頭の区切りのアトリビュート名に対応するプラグが既に分かっている
                場合に指定する(transform からシェイプへ伸ばして探した場合など)。

        Returns:
            om2.MPlug | None: プラグ。アトリビュートとして解決できない場合(存在しないアトリビュート、範囲指定、
                マルチアトリビュートでないアトリビュートへの番号、:data:`MAX_LOGICAL_INDEX` を超える番号、
                マルチアトリビュートの要素の番号を指定しない子アトリビュートなど)は None。
        """
        ...
    @staticmethod
    def _plug_from_path(text: str) -> tuple[om2.MObject | om2.MDagPath, om2.MPlug] | None:
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
                (存在しないアトリビュート、範囲指定、マルチアトリビュートでないアトリビュートへの番号など)は None。
        """
        ...
    @staticmethod
    def _unnetworked(mplug: om2.MPlug) -> om2.MPlug:
        """接続由来(networked)のMPlugを、同じアトリビュートを指す非networkedのMPlugにする。

        networkedのMPlugは接続が解除されると破棄されるため、切断後も使う参照はこれに持ち替える。

        Args:
            mplug (om2.MPlug): 対象のMPlug。

        Returns:
            om2.MPlug: 非networkedならそのまま、networkedならマルチアトリビュートの要素・子を辿って作り直したMPlug。
        """
        ...
    @staticmethod
    def _resolve_input(value: Plug | om2.MPlug | str) -> Plug:
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
        ...
    def _enum_attribute(self, caller: str) -> om2.MObject:
        """有効性を確かめ済みの前提で、enumアトリビュートの定義を返す。

        Args:
            caller (str): エラー表示に使うメソッド名。

        Returns:
            om2.MObject: enumアトリビュートの定義。

        Raises:
            TypeError: enumアトリビュートでない場合。
        """
        ...
    def _enum_field_name(self, attr: om2.MObject, value: int) -> str:
        """enumの値に対応するフィールド名を返す。

        Args:
            attr (om2.MObject): enumアトリビュートの定義。
            value (int): enum値。

        Returns:
            str: フィールド名。

        Raises:
            ValueError: 対応するフィールドが無い場合(MayaのRuntimeErrorを読み替える)。
        """
        ...
    def _label(self) -> str:
        """エラー表示用の名前を返す。削除済みでも作成時のアトリビュートパスで示す。

        Returns:
            str: 有効なら :meth:`getFullName`。無効なら所有ノード名(削除済みなら
                ``<deleted node>``)と作成時のアトリビュートパス。
        """
        ...
    def _attribute_exists(self) -> bool:
        """アトリビュートが所有ノードに存在し続けているか判定する(所有ノードは有効であること)。

        頻繁に呼ばれる :meth:`_require_valid`・:meth:`getFullName` は、呼び出しの負荷を
        避けるため同じ判定を直接書いている(変更する場合はそろえること)。

        Returns:
            bool: 静的アトリビュート、または削除されていない動的アトリビュートの場合は True。
        """
        ...
    def _require_valid(self, action: str = ...) -> None:
        """所有ノードとアトリビュートが有効か確かめる。

        削除済みの動的アトリビュートの MPlug で値を読み書きすると Maya が異常終了し、削除済みノードの
        MPlug は古い値を返す(Undo の対象から外れた削除では問い合わせで異常終了する場合も
        ある)ため、MPlug・アトリビュートを扱う前に必ず確かめる。静的アトリビュートはノードが有効な間は常に
        存在するため、ノードの確認だけで済む。動的アトリビュートは所有ノードの
        ``MFnDependencyNode.attributeClass()`` で存在を確かめる(:meth:`_attribute_exists`)。

        Args:
            action (str): 例外メッセージの動詞(``Cannot {action} an invalid Plug``)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        ...
    def _range_value(self, value: object, angle_unit: str | None, ui_units: bool) -> Any:
        """getMin等の戻り値を、uiUnits・unitの指定に従って換算する。

        Args:
            value (object): 定義から読んだ値(単位付きオブジェクト・数値・tuple)。
            angle_unit (str | None): ``"deg"`` / ``"rad"``。Noneは換算しない。
            ui_units (bool): Trueは現在のUI単位の数値へ換算する。

        Returns:
            object: 換算した値。
        """
        ...
    def _range_attribute_fn(self) -> om2.MFnNumericAttribute | om2.MFnUnitAttribute | None:
        """寿命を検証し、範囲照会に対応する型のFunction Setを返す。

        Returns:
            om2.MFnNumericAttribute | om2.MFnUnitAttribute | None: 数値・単位型の照会先。
                対応しないアトリビュート型はNone。
        """
        ...
    def _require_writable(self):
        """保持参照とコンパウンドアトリビュートの全子の書込み可否を検証する。シーンは変更しない。

        Raises:
            RuntimeError: 無効な参照、ロック、入力接続、書込み禁止の場合。
        """
        ...
    @staticmethod
    def _node_from_mplug(mplug: om2.MPlug) -> Node:
        """MPlug の所有 MObject から登録された型の Node ラッパーを生成する。

        Args:
            mplug (om2.MPlug): 所有ノードを取得するプラグ。

        Returns:
            Node: 所有ノードの型登録に従って解決したラッパー。
        """
        ...
    def __getattr__(self, name: str) -> Any: ...
    def __getitem__(self, key: int | str) -> Plug: ...
    def __iter__(self) -> Iterator[Plug]: ...
