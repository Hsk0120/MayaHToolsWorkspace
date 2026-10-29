# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

import inspect
import re
from typing import Any
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import Object, _missing_member_message
from ..core.registry import _inherited_node_types, _node_type_exists, _real_node_type
from ..core.registry import _unknown_node_type_message
from ..decorator import _edit_context, _merge_flags, _pick_alias, _require_bool, _validated_flags, undoTransaction
from ..util import _ArgumentError, _UNSET, _angle_unit
from typing import Any, Iterable, Iterator, Literal, Sequence
from mlib.common.namespace import Namespace
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.nodes.dagNode import DagNode
from mlib.nodes.shadingEngine import ShadingEngine
from mlib.plugs.plug import Plug
from typing import overload
from typing_extensions import Self

_MOVABLE_NUMERIC_TYPES: dict
_MULTI_COMPONENT_NUMERIC_TYPES: frozenset
_OM2_LIST_ATTR_FLAGS: frozenset
_TYPE_NAME_FN: Any

def _subclass_overrides(base: type, name: str) -> bool:
    """baseの派生クラス(孫以降を含む)のいずれかがメソッドを上書きしているか調べる。

    呼出しのたびに現在の派生クラスを調べるため、後から定義・登録されたクラスも反映する。

    Args:
        base (type): 基底クラス。
        name (str): メソッド名。

    Returns:
        bool: 1つでも上書きしていればTrue。
    """
    ...

def _node_type_name(mobject: om2.MObject) -> str:
    """検証済みの依存ノードの MObject から nodeType 名を取得する。

    ``om2.MFnDependencyNode(mobject).typeName`` と同じ値を、使い回しの関数セットで読む。

    Args:
        mobject (om2.MObject): 有効な依存ノードの MObject。

    Returns:
        str: Maya の nodeType 名。
    """
    ...

def _resolve_node(node: str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> tuple[om2.MObject, om2.MDagPath | None]:
    """ノードを表す入力を MObject と MDagPath へ解決する。

    Node.__new__ (ラッパー型の選択)を通じてNodeの入力解決が利用する下位の解決処理。
    Node(...) の生成では __new__ で1回だけ呼び、結果を __init__ へ引き継ぐ。Plug・MPlug は
    所有ノード、コンポーネント(単体・複数形)は所有シェイプへ解決する。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
            ``"node.attribute"`` や ``"pCube1.vtx[0]"`` のような文字列も所有ノードへ解決する
            (インスタンス化されたノードは、名前が指すインスタンスのパスを保持する)。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (:class:`mlib.plugs.plug.DeletedAttributeError`。``RuntimeError`` の派生でもある)。
        RuntimeError: 名前を解決できない(存在しない、または複数の対象に一致する)場合、
            または空・無効な(削除済みの)ラッパーや om2 オブジェクトを指定した場合。
    """
    ...

def _not_unique_message(name: str, matches: Sequence[str]) -> str:
    """複数の対象に一致する名前の例外メッセージを作る。

    一致した対象を最大3件まで完全パスで示し、完全パスか ``mlib.ls`` での指定を案内する。

    Args:
        name (str): 解決しようとした名前。
        matches (Sequence[str]): 一致した対象の名前。

    Returns:
        str: 例外メッセージ。
    """
    ...

def _require_node_name(name: object) -> None:
    """作成・改名に使うノード名の、Mayaが黙って置き換える文字を拒否する。

    Args:
        name (object): ノード名。文字列以外の検査はMayaに任せる。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: DAGパスの区切り ``|`` を含む場合。
    """
    ...

def _is_deleted_api_object(value: object) -> bool:
    """om2 オブジェクトが削除済みのノードを指すか判定する(空のオブジェクトは False)。

    Args:
        value (object): 判定する値。om2 の MObject・MDagPath・MPlug 以外は False。

    Returns:
        bool: 削除済みのノードを指す MObject・MDagPath・MPlug の場合は True。
            無効な MDagPath は、空のパスも含めて True(``Node(...)`` も区別しない)。
    """
    ...

def _resolve_input_or_none(other: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> Node | None:
    """判定メソッド(``isParentOf`` など)の対象をノードへ解決する。

    ``mlib.nodes.Node._resolve_input`` と同じ規則で解決し、削除済みの対象(削除済みの Node、
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
    ...

def _dump_movable_attr(plug: Plug) -> dict:
    """並び替え対応の単純な動的アトリビュートから再作成に必要な情報を集める。

    数値(bool/byte/short/long/float/double)、enum、文字列型のコンパウンドアトリビュートでもマルチアトリビュートでもない
    トップレベル動的アトリビュートのみ対応する。

    Args:
        plug (Plug): ダンプ対象の動的アトリビュートプラグ。

    Returns:
        dict: addAttr() での再作成と値・状態の復元に必要な情報。

    Raises:
        TypeError: コンパウンドアトリビュート・マルチアトリビュート、または対応しないアトリビュート型の場合。
    """
    ...

def _enum_definition(plug: Plug) -> str:
    """enum の全フィールドを ``cmds.attributeQuery(listEnum=True)`` と同じ書式の文字列にする。

    値の昇順に並べ、直前の値 + 1(先頭は0)と異なる値だけ ``名前=値`` と書く(例: ``a=1:b=5``)。

    Args:
        plug (Plug): enum アトリビュートのプラグ。

    Returns:
        str: ``addAttr(enumName=...)`` へそのまま渡せるフィールド定義。
    """
    ...

def _scalar_attribute(attribute: om2.MObject) -> bool:
    """``cmds.listAttr(scalar=True)`` が列挙する、単一成分の数値・単位・enum 型か判定する。

    マルチアトリビュートであっても、要素が単一成分なら対象に含める(listAttr と同じ)。

    Args:
        attribute (om2.MObject): アトリビュート定義。

    Returns:
        bool: scalar として列挙する場合は True。
    """
    ...

def _writable_plug(plug: Plug) -> bool:
    """Plug._require_writable() が通るか(ロック・入力接続・書込み禁止が無いか)を返す。

    Args:
        plug (Plug): 検査するプラグ。

    Returns:
        bool: 書き込める場合は True。シーンは変更しない。
    """
    ...

def _movable_connection_ref(plug: Plug) -> tuple[Node, str]:
    """削除する定義を保持せず、所有ノードと再解決用のパスを保存する。

    Args:
        plug (Plug): 変更前に存在する接続端点。

    Returns:
        tuple[Node, str]: 所有ノードとaliasを使わないアトリビュートパス。
    """
    ...

def _create_movable_attr(node: Node, info: dict) -> Plug:
    """退避した定義と値を再作成する。接続とロックは全定義の作成後に戻す。

    Args:
        node (Node): アトリビュートを追加する対象ノード。
        info (dict): _dump_movable_attr() が返した情報。

    Returns:
        Plug: 再作成したアトリビュートプラグ。
    """
    ...


class Node(Object):
    """Mayaノードと、DAGノードでは特定インスタンスのパスを参照する。

    nodeTypeの登録型、近い登録祖先型、Nodeの順にラッパー型を選ぶ。
    Nodeを渡しても新しいラッパーを返し、Mayaノードは複製しない。
    名前・MDagPath・既存ラッパーのDAGパスを保持し、MObject・MPlugでは最初のパスを使う。
    保持インスタンスが消失した場合は別パスへ切り替えず、パスを使う操作でRuntimeErrorになる。
    str(node)は改名・親変更に追従する最短一意名、削除済みなら空文字列を返す。

    取得専用のクラスで、ノードの作成は :func:`mlib.createNode` で行う(``Node.create`` や
    ``Node(name, create=True)`` の作成経路は無い)。``isinstance`` の階層は手書きクラスの継承に
    従い、Mayaの抽象祖先型(``geometryFilter``・``containerBase``・``entity`` 等)のクラスは含まない。
    Mayaの継承チェーンによる判定は :meth:`isType` または :meth:`getType` の ``inherited=True`` を使う。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            名前または参照。Plug・MPlugは所有ノード、Component・Componentsは所有シェイプへ解決する。

    Raises:
        TypeError: 入力型が不正、または指定クラスと対象型が非互換の場合。
        ValueError: 所有ノードが有効でアトリビュートだけが削除済みのPlugの場合。
            MPlugも含み、DeletedAttributeError(RuntimeErrorの派生でもある)。
        RuntimeError: 取得対象が空・削除済み・存在しない・一意でない場合。
    """
    _registry: None
    _fn_cache: None
    def __new__(cls, node: str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug, *args: object, **kwargs: object) -> Self:
        """ノード型の登録情報に従ってラッパーを割り当てる。

        入力を一度だけ解決し、nodeTypeに対応する登録クラス(登録が無い型は登録表の規則で
        選ぶクラス。無ければNode)を選ぶ。具体的なクラスを指定した場合は、そのクラスの
        派生型以外を拒否し、黙って別の型へ差し替えない。ノードの作成は行わない。

        Args:
            node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlugは所有ノード、Component・Componentsは所有シェイプを指す。
            *args (object): 選んだクラスの ``__init__`` へ渡す位置引数。
            **kwargs (object): 選んだクラスの ``__init__`` へ渡すキーワード引数。
                ``create`` は受け付けない(``__init__`` が TypeError にする)。

        Returns:
            Node: 解決したMayaノードを参照する、適合クラスの新しいインスタンス。

        Raises:
            TypeError: ノード入力が対応しない型、指定クラスと対象型が非互換、または選んだクラスの
                ``__init__`` が受けない引数(廃止した ``create`` 等)を渡した場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノードを解決できない場合。
        """
        ...
    def __init__(self, node: str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> None:
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        既存の Node を渡した場合は、同じ MObject と DAG パス(インスタンス)を
        指す新しいラッパーになる。

        Args:
            node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlugは所有ノード、Component・Componentsは所有シェイプを指す。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノード名を解決できない場合。
        """
        ...
    def __eq__(self, other):
        """生存中の同じ対象を比較する。DAGはインスタンスのパスも区別する。

        Args:
            other: 比較・演算の相手。
        """
        ...
    def __hash__(self):
        """生成時のMayaハンドルのハッシュを返す。改名・削除後も変化しない。"""
        ...
    def __repr__(self) -> str:
        """デバッグ用にクラス名とノード名を含む表現を返す。

        Returns:
            str: 有効なら型名とノード名、無効なら型名と invalid を含む文字列。
        """
        ...
    def __str__(self) -> str:
        """Maya の最短一意ノード名を文字列として返す。

        maya.cmds は文字列以外の引数に ``str()`` を適用するため、Node をそのまま
        ``cmds.select(node)`` のように渡せる。呼び出すたびに再計算するため、
        名前変更・親子付け替えに追従する。

        :meth:`getName` と異なり、削除済み・Undoで無効になったノードでも例外にせず空文字列を返す
        (maya.cmds へ渡したときにMaya側のエラーとして扱われるようにする)。

        Returns:
            str: 最短一意名。無効なノードでは空文字列。
        """
        ...
    def __getattr__(self, name: str) -> Any:
        """通常アトリビュートにない名前を Maya Plug として動的に解決する。

        静的解析では、具象クラス(SkinCluster 等)のメソッドを基底の Node 型で呼んだ場合に
        Plug 型と誤判定しないよう、戻り値の注釈は Any としている。

        Args:
            name (str): 取得しようとした Python アトリビュート名。

        Returns:
            Plug: 解決した Maya アトリビュートプラグ。

        Raises:
            AttributeError: 非公開名または存在しない Maya アトリビュートを指定した場合。
                文言は ``'Joint' has no method or Maya attribute 'orientJoint'`` の形で、近い名前の
                メソッドとPyMEL・maya.cmdsの名前に対応するmlibの書き方を案内する。
                :meth:`getPlug` が RuntimeError にする名前(``input3Dx`` のような、マルチアトリビュートの要素の
                番号を含まないマルチアトリビュートであるコンパウンドアトリビュートの子)も、``hasattr``/``getattr(node, name, default)``
                が使えるよう AttributeError にする(原因の RuntimeError を ``__cause__`` に持つ)。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def __setattr__(self, name: str, value: object) -> None:
        """Mayaアトリビュートの名前への代入を、そのPlugの :meth:`~mlib.plugs.plug.Plug.set` にする。

        ``node.tx = 5`` は ``node.getPlug("tx").set(5)`` と同じで、Undoに記録し、角度は度で
        受け取る(``node.t = (1, 2, 3)`` も同じ)。``_`` で始まる名前と、クラスに定義された名前
        (メソッド・プロパティ・クラス属性)は通常のPythonの代入として扱う。それ以外の名前の
        Pythonの属性をインスタンスへ追加することはできない。

        Args:
            name (str): 代入する名前。
            value (object): 値。

        Returns:
            None: 値を返さない。

        Raises:
            AttributeError: Mayaアトリビュートが無い名前の場合。
            RuntimeError: ノードが無効、またはMayaが書込みを拒否した場合。
            TypeError: 値の型がアトリビュートに合わない場合(Plug.setと同じ)。
            ValueError: 値の成分数・範囲が合わない場合(Plug.setと同じ)。
        """
        ...
    def getShadingEngines(self) -> list[ShadingEngine]:
        """自身から直接接続されているShadingEngineを重複なしで返す。

        Returns:
            list[ShadingEngine]: 直接接続先。テクスチャから履歴を辿る操作ではない。
        """
        ...
    def sameNode(self, other: object) -> bool:
        """別インスタンスも含め、同じ生存中のMayaノードを指すか返す。

        Args:
            other (object): 比較対象。Node 以外は False。

        Returns:
            bool: 両者が生存し、同じ Maya ノードを指す場合は True。
        """
        ...
    def isValid(self) -> bool:
        """Maya シーン上でノードが有効か判定する。

        ノード全体の有効性を返し、保持したDAGインスタンスのパスは検証しない。
        保持インスタンスだけが削除されてもノードが残っていればTrueになり、
        そのパスを使う操作はRuntimeErrorになる。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        ...
    def isAlive(self) -> bool:
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        ...
    def mnode(self) -> om2.MObject | None:
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        ...
    def mfn(self) -> om2.MFnDependencyNode:
        """このノードで最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        Node は ``om2.MFnDependencyNode``。DagNode は ``MFnDagNode``、Transform は ``MFnTransform`` のように
        派生クラスが最も具体的な function set へ上書きする。内部のキャッシュとは共有しないため、
        戻り値を保持しても他の照会に影響しない。

        Returns:
            om2.MFnDependencyNode: このノードの function set。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def getType(self, inherited: bool = ...) -> str | list[str]:
        """Maya の nodeType 名、または nodeType の継承チェーンを取得する。

        動的に生成したクラスを含め、ラッパーのクラス名ではなく Maya の nodeType 名をそのまま返す。

        Args:
            inherited (bool): True なら ``cmds.nodeType(inherited=True)`` と同じ順
                (基底型から自身へ。``node`` は含まない)の継承チェーンを返す。既定 False は型名だけ。

        Returns:
            str | list[str]: 既定は対応する Maya nodeType 名。inherited=True は継承チェーンの新しいリスト。

        Raises:
            TypeError: inherited が bool 以外の場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def hasFn(self, fn: int) -> bool:
        """保持する MObject が指定の OpenMaya 関数型に対応するか判定する。

        ``mnode().hasFn(fn)`` の公開入口。Maya の nodeType の継承(:meth:`isType`)ではなく、
        ``om2.MFn.kDagNode`` のような API の関数型で判定する。

        Args:
            fn (int): ``om2.MFn`` の定数。

        Returns:
            bool: 対応する場合は True。

        Raises:
            TypeError: fn が int 以外の場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def getTypeId(self) -> int:
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def getPluginName(self) -> str:
        """ノード型がプラグイン由来の場合、そのプラグイン名を取得する。

        Returns:
            str: プラグイン名。Maya組み込みのノード型では空文字列。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def getClassification(self) -> list[str]:
        """ノード型の分類文字列を1要素のリストで取得する。

        Returns:
            list[str]: ``MNodeClass.classification`` を保持する。分類がなければ ``[""]``。
        """
        ...
    def isType(self, nodeType: str) -> bool:
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``isType("shape")`` で True になる。2026で改名された型は
        どちらの名前でも判定できる(``isType("multDoubleLinear")`` と ``isType("multDL")``)。

        Args:
            nodeType (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに nodeType が含まれる場合は True。

        Raises:
            ValueError: nodeType が空文字列または文字列以外の場合。
        """
        ...
    def isLocked(self) -> bool:
        """ノード自体がロックされているか判定する。

        アトリビュート単位のロックは Plug.isLocked() を参照する。

        Returns:
            bool: ロックされている場合は True。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def setLocked(self, state: bool = ..., *, fast: bool = ...) -> Node:
        """ノード自体のロック状態を設定する。アトリビュート単位のロックは Plug.setLocked() を使う。

        通常は ``cmds.lockNode`` で更新し Undo に記録する。``fast=True`` は
        ``MFnDependencyNode.isLocked`` を直接更新し Undo に記録しない。

        Args:
            state (bool): True でロック、False で解除。既定 True。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Node: 自身。

        Raises:
            TypeError: state または fastがbool以外の場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)、または Maya が更新を拒否した場合。
        """
        ...
    def isFromReferencedFile(self) -> bool:
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def isAncestorOf(self, other: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> bool:
        """保持するDAGパスで、otherが自身の子孫か判定する。

        Args:
            other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象の参照や名前。Plugは所有ノード、Componentは所有シェイプへ解決する。

        Returns:
            bool: 自身を除く子孫ならTrue。非DAG・無効なノード・削除済みアトリビュートはFalse。

        Raises:
            TypeError: otherが未対応型の場合。
            RuntimeError: 名前を解決できない、MObject・MPlugが空、または保持インスタンスが消失した場合。
        """
        ...
    def isParentOf(self, other: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> bool:
        """保持するDAGパスで、otherが自身の直接の子か判定する。

        Args:
            other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象の参照や名前。Plugは所有ノード、Componentは所有シェイプへ解決する。

        Returns:
            bool: 直接の子ならTrue。非DAG・無効なノード・削除済みアトリビュートはFalse。

        Raises:
            TypeError: otherが未対応型の場合。
            RuntimeError: 名前を解決できない、MObject・MPlugが空、または保持インスタンスが消失した場合。
        """
        ...
    def isRoot(self) -> bool:
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        ...
    def getNodeName(self, removeNamespace: bool = ...) -> str:
        """DAG パスを除いたノード名を取得する。

        DGノードにも使用できる。DAGの別階層に同名ノードがある場合も
        親パスは付けないため、Mayaコマンドへ渡す一意な名前にはgetNameを使う。

        Args:
            removeNamespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``removeNamespace`` が ``True`` の場合は
                namespaceを含まないノード名。

        Raises:
            RuntimeError: ノードが削除済み、またはUndoで作成が取り消された(無効な)場合。
        """
        ...
    def getNamespace(self) -> Namespace:
        """ノードが属するネームスペースを取得する。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        ...
    def setNamespace(self, namespace: str | Namespace, *, fast: bool = ...) -> Node:
        """ノードを指定したネームスペースへ移動する。

        Args:
            namespace (str | Namespace): 移動先のnamespace名。末尾の ``":"`` は任意。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Node: 自身。namespace付きの名前は :meth:`getNodeName` で取得する。

        Raises:
            ValueError: namespaceが空文字列または文字列でない場合。
            RuntimeError: namespace移動に失敗した場合。
        """
        ...
    def delete(self, *, safe: bool = ..., fast: bool = ...) -> None:
        """自身をMaya標準の規則で削除する。

        DAGの子も削除し、一回のUndoで戻せる。
        派生クラスはこのメソッドを上書きして専用の削除処理を実装できる。

        削除の前に自身とDAG子孫を検査し、ロック・参照のノード、または既定・共有ノード等の
        Mayaが削除を拒否するノード(``cmds.ls(undeletable=True)`` が返すもの。time1・persp・
        defaultLayer など)が含まれる場合は何も削除せずRuntimeErrorにする。通常経路の文言は
        cmds.deleteの要素ごとの表示に合わせ(``Cannot delete locked node 'x'.``・
        ``Cannot delete 'x' as it has locked or read-only children.``・
        ``Non-deletable node 'x' cannot be deleted.``)、fastのロック・参照は従来の
        ``Node is locked or referenced: x``。

        Args:
            safe (bool): Trueなら自身またはDAG子孫にDG接続がある場合は削除しない。
                入力・出力・message・Set/マテリアル接続を全て含む。
                Falseは従来の削除。ロック解除や例外抑制は行わない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: safeがboolでない場合。
            RuntimeError: 対象が無効、ロック・参照・削除できないノードを含む、またはMayaが
                削除を拒否した場合。
        """
        ...
    def rename(self, name: str, ignoreShape: bool = ..., *, fast: bool = ...) -> Node:
        """ノード名を変更し、自身を返す。

        Mayaが補正した最終的な名前(重複時の連番等)は戻り値の :meth:`getNodeName` で取得する。

        Args:
            name (str): 新しいノード名。DAGパスの区切り ``|`` は含められない
                (Mayaは黙って別の文字へ置き換えるため拒否する)。
            ignoreShape (bool): ``True`` の場合はShapeの名前変更を抑制する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Node: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: nameに ``|`` を含む場合。
            RuntimeError: ノードが無効(削除済み)の場合(``Cannot rename an invalid node``。
                fastも同じ)、保持するDAGインスタンスが削除された場合、またはMayaが
                改名を拒否した場合。
        """
        ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[True], index: int) -> tuple[Plug, Node] | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[True], index: None = ...) -> list[tuple[Plug, Node]]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[False] = ..., index: int) -> tuple[Plug, Plug] | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[True], asNode: Literal[False] = ..., index: None = ...) -> list[tuple[Plug, Plug]]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[True], index: int) -> Node | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[True], index: None = ...) -> list[Node]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[False] = ..., index: int) -> Plug | None: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: Literal[False] = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: Literal[False] = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., *, asPair: Literal[False] = ..., asNode: Literal[False] = ..., index: None = ...) -> list[Plug]: ...
    @overload
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., asPair: bool = ..., asNode: bool = ..., index: int | None = ...) -> list | Plug | Node | tuple | None:
        """接続をPlug・Node・ペアとして照会する。

        Args:
            s (bool): 入力を含める。sourceとANDする。
            d (bool): 出力を含める。destinationとANDする。
            c (bool): ペア指定の短縮名。
            t (str | None): typeの短縮名。
            et (bool): exactTypeの短縮名。
            scn (bool): skipConversionNodesの短縮名。
            source (bool): 入力を含める。
            destination (bool): 出力を含める。
            connections (bool): 自身側と相手側のペアを返す。
            type (str | None): 接続先ノード型。
            exactType (bool): 型名の完全一致で絞る。
            skipConversionNodes (bool): unitConversion系を飛ばす。
            asPair (bool): 自身側Plugと相手側のペアを返す。
            asNode (bool): 相手側をNodeで返す。
            index (int | None): 結果の一件。範囲外はNone。

        Returns:
            list | Plug | Node | tuple | None: 条件に合う結果。
        """
        ...
    def getHistory(self, type: str | None = ..., future: bool = ...) -> list[Node]:
        """構築履歴を ``MItDependencyGraph`` で検索し、対応するノードラッパーを取得する。

        Args:
            type (str | None): 継承型を含むノード型フィルター。Noneは全型。
            future (bool): Trueは下流、Falseは上流を検索する。

        Returns:
            list[Node]: ``cmds.listHistory`` と同じ順(深さ優先)。自身と重複を除く。該当なしなら空リスト。
                Shapeを持つTransformは、``listHistory`` と同じく中間オブジェクトでない直下のShapeの
                履歴を返す。DAGノードは最初のDAGパスで返す。

        Raises:
            RuntimeError: 無効な(削除済みの)ノードの場合。
        """
        ...
    def resetAttrs(self, attributes: str | Plug | Iterable[str | Plug] | None = ..., *, fast: bool = ...) -> list[Plug]:
        """指定アトリビュート、または書き込み可能なキー設定対象アトリビュートを既定値へ戻す。

        Transformも同じ規則で、省略時はtranslate・rotate・scale・shearに限らずキー設定可能な全て
        (visibility等を含む)を戻す。

        Args:
            attributes (str | Plug | Iterable[str | Plug] | None): アトリビュート名、または自身の
                Plug(名前と混在できる)。Noneはキー設定可能な
                数値・単位・enumアトリビュートを対象とし、マルチアトリビュート・ロック・入力接続・書込み禁止・
                非対応型は除外する(通常/fastで同じ選択)。
                明示指定したアトリビュートのエラーは除外せず送出する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            list[Plug]: リセットしたアトリビュート。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 名前・Plug以外を指定した場合、または明示指定したアトリビュートがリセット非対応の場合。
            ValueError: 別のノードのPlugを指定した場合。
            RuntimeError: 明示指定したアトリビュートがロック・接続済みなどで書き込みできない場合。
        """
        ...
    def setAttrFlags(self, attributes: str | Plug | Iterable[str | Plug], locked: bool | None = ..., keyable: bool | None = ..., channelBox: bool | None = ..., *, fast: bool = ...) -> Node:
        """指定アトリビュートのロック・キー設定可否・Channel Box表示を変更する。

        状態の型を検査し、全アトリビュートを解決してから順に更新する。
        途中の失敗で、先行の変更は自動では戻さない。

        Args:
            attributes (str | Plug | Iterable[str | Plug]): アトリビュート名、または自身のPlug
                (名前と混在できる)。子も変更するなら子名を明示する。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channelBox (bool | None): Channel Box表示。Noneは変更しない。keyable=TrueならMayaにより表示される。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Node: 自身。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 必須引数の不足、fastや状態の型が不正、または名前・Plug以外を指定した場合。
            ValueError: 別のノードのPlugを指定した場合。
            RuntimeError: Mayaが更新を拒否した場合。
        """
        ...
    def getPlugs(self, userDefined: bool = ..., includeChildren: bool = ..., **listAttrFlags) -> list[Plug]:
        """アトリビュートをPlug参照として列挙する。

        ``userDefined=True`` はユーザー追加(動的)アトリビュートだけを、Mayaの定義から追加順に
        型付きPlugで作る(cmdsは使わない。マルチアトリビュートはMultiPlug、非表示・非keyableも含む)。
        それ以外は ``cmds.listAttr`` の条件で列挙する(``keyable=True`` 等)。フラグ無し・``keyable=True``・
        ``scalar=True`` (併用可)は ``cmds.listAttr`` を呼ばず、同じ順序・同じ結果をOpenMayaの定義の
        走査で求める(トップレベルの定義順に、コンパウンドアトリビュートの子を親の直後へ並べ、マルチアトリビュートであるコンパウンドアトリビュートの子は含めない)。

        Args:
            userDefined (bool): Trueはユーザー定義アトリビュートだけを返す。listAttrのフラグとは併用できない。
            includeChildren (bool): Trueはコンパウンドアトリビュートの子も含める。Falseはトップレベルだけ。
            **listAttrFlags: ``userDefined=False`` のときに ``cmds.listAttr`` へ渡すフラグ。

        Returns:
            list[Plug]: 追加順(userDefined)またはlistAttr順の新しい参照リスト。解決できないパスは省き、
                該当なしなら空。名前が必要なら ``[plug.getLongName() for plug in ...]`` を使う。

        Raises:
            TypeError: userDefined・includeChildrenがboolでない、またはuserDefined=TrueにlistAttrのフラグを併用した場合。
            RuntimeError: ノードが無効、listAttrが失敗、またはuserDefined=TrueかつincludeChildren=Trueで
                番号を指定しないマルチアトリビュートであるコンパウンドアトリビュートの子が含まれる場合。
        """
        ...
    def getAliases(self) -> list[tuple[str, Plug]]:
        """このノードのアトリビュートエイリアスを取得する。

        Returns:
            list[tuple[str, Plug]]: ``(エイリアス名, 対応するPlug)`` のリスト。
                エイリアスが無ければ空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def addAttr(self, longName: str = ..., type: str | None = ..., subType: str | None = ..., channelBox: bool = ..., childNames: Sequence[str] | None = ..., childShortNames: Sequence[str] | None = ..., childSuffixes: Sequence[str] | None = ..., proxy: Plug | str | None = ..., getPlug: bool = ..., *, fast: bool = ..., unit: str = ..., attributeType: str = ..., at: str = ..., binaryTag: str = ..., bt: str = ..., cachedInternally: bool = ..., ci: bool = ..., category: str | Sequence[str] = ..., ct: str | Sequence[str] = ..., dataType: str | Sequence[str] = ..., dt: str | Sequence[str] = ..., defaultValue: object = ..., dv: object = ..., disconnectBehaviour: int = ..., dcb: int = ..., edit: bool = ..., e: bool = ..., enforcingUniqueName: bool = ..., eun: bool = ..., enumName: str = ..., en: str = ..., exists: bool = ..., ex: bool = ..., fromPlugin: bool = ..., fp: bool = ..., hasMaxValue: bool = ..., hxv: bool = ..., hasMinValue: bool = ..., hnv: bool = ..., hasSoftMaxValue: bool = ..., hsx: bool = ..., hasSoftMinValue: bool = ..., hsn: bool = ..., hidden: bool = ..., h: bool = ..., indexMatters: bool = ..., im: bool = ..., internalSet: bool = ..., keyable: bool = ..., k: bool = ..., ln: str = ..., maxValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., max: float | om2.MAngle | om2.MDistance | om2.MTime = ..., minValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., min: float | om2.MAngle | om2.MDistance | om2.MTime = ..., multi: bool = ..., m: bool = ..., niceName: str = ..., nn: str = ..., numberOfChildren: int = ..., nc: int = ..., parent: str = ..., p: str = ..., pxy: Plug | str | None = ..., query: bool = ..., q: bool = ..., readable: bool = ..., r: bool = ..., shortName: str = ..., sn: str = ..., softMaxValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., smx: float | om2.MAngle | om2.MDistance | om2.MTime = ..., softMinValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., smn: float | om2.MAngle | om2.MDistance | om2.MTime = ..., storable: bool = ..., s: bool = ..., usedAsColor: bool = ..., uac: bool = ..., usedAsFilename: bool = ..., uaf: bool = ..., usedAsProxy: bool = ..., uap: bool = ..., worldSpace: bool = ..., ws: bool = ..., writable: bool = ..., w: bool = ..., cb: bool = ..., **kwargs) -> Plug | None:
        """型・既定値・フラグを指定してアトリビュートを追加する。

        作成専用。query/edit=Trueは拒否する。長名と対応する短名は同時指定できない。
        型はproxyの元、明示type、attributeType/dataTypeの順に使い、全て省略時はdouble。
        単位型を追加する場合、数値の既定値・制限は距離cm・時刻秒、角度(doubleAngle、subType="doubleAngle"の子)は
        unitの単位(既定は度)で指定する。om2.MAngle等の単位付きの値はそのまま使う。
        通常はUndo有効時に記録する。fastはUndo設定を変えずOM2で追加し、未対応の型・定義フラグは追加前に拒否する。

        Args:
            longName (str): ロング名。lnまたはsnだけの指定も可能。
            type (str | None): 型名。at:/dt:接頭辞も可。明示時はattributeType/dataTypeより優先。
            subType (str | None): 自動生成する子の共通型。
            channelBox (bool): チャンネルボックス表示。cbでも指定可能。
            childNames (Sequence[str] | None): 子のロング名。
            childShortNames (Sequence[str] | None): 子のショート名。
            childSuffixes (Sequence[str] | None): 親名へ付加する子の接尾辞。
            proxy (Plug | str | None): プロキシの元アトリビュート。
            getPlug (bool): 既定Trueは追加したPlug、FalseはNoneを返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            unit (str): 角度アトリビュートの数値の既定値・min/max・softMin/softMaxの単位。既定 ``"deg"`` は度、
                ``"rad"`` はラジアン(``"degree"`` / ``"radians"`` 等の別名も可)。Mayaのフラグではない。
            attributeType (str): MayaのattributeTypeフラグ。
            at (str): attributeTypeの別名。
            binaryTag (str): MayaのbinaryTagフラグ。
            bt (str): binaryTagの別名。
            cachedInternally (bool): MayaのcachedInternallyフラグ。
            ci (bool): cachedInternallyの別名。
            category (str | Sequence[str]): Mayaのcategoryフラグ。
            ct (str | Sequence[str]): categoryの別名。
            dataType (str | Sequence[str]): MayaのdataTypeフラグ。
            dt (str | Sequence[str]): dataTypeの別名。
            defaultValue (object): 追加する型に対応した既定値。数値のコンパウンドアトリビュートは成分列、型付きデータはPlug.setと同じ形で指定する。
            dv (object): defaultValueの別名。
            disconnectBehaviour (int): MayaのdisconnectBehaviourフラグ。
            dcb (int): disconnectBehaviourの別名。
            edit (bool): Trueは作成専用のため拒否する。
            e (bool): editの別名。
            enforcingUniqueName (bool): MayaのenforcingUniqueNameフラグ。
            eun (bool): enforcingUniqueNameの別名。
            enumName (str): MayaのenumNameフラグ。
            en (str): enumNameの別名。
            exists (bool): Mayaのexistsフラグ。
            ex (bool): existsの別名。
            fromPlugin (bool): MayaのfromPluginフラグ。
            fp (bool): fromPluginの別名。
            hasMaxValue (bool): MayaのhasMaxValueフラグ。
            hxv (bool): hasMaxValueの別名。
            hasMinValue (bool): MayaのhasMinValueフラグ。
            hnv (bool): hasMinValueの別名。
            hasSoftMaxValue (bool): MayaのhasSoftMaxValueフラグ。
            hsx (bool): hasSoftMaxValueの別名。
            hasSoftMinValue (bool): MayaのhasSoftMinValueフラグ。
            hsn (bool): hasSoftMinValueの別名。
            hidden (bool): Mayaのhiddenフラグ。
            h (bool): hiddenの別名。
            indexMatters (bool): MayaのindexMattersフラグ。
            im (bool): indexMattersの別名。
            internalSet (bool): MayaのinternalSetフラグ。
            keyable (bool): Mayaのkeyableフラグ。
            k (bool): keyableの別名。
            ln (str): longNameの別名。
            maxValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのmaxValueフラグ。
            max (float | om2.MAngle | om2.MDistance | om2.MTime): maxValueの別名。
            minValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのminValueフラグ。
            min (float | om2.MAngle | om2.MDistance | om2.MTime): minValueの別名。
            multi (bool): Mayaのmultiフラグ。
            m (bool): multiの別名。
            niceName (str): MayaのniceNameフラグ。
            nn (str): niceNameの別名。
            numberOfChildren (int): MayaのnumberOfChildrenフラグ。
            nc (int): numberOfChildrenの別名。
            parent (str): 親にする既存のコンパウンドアトリビュート名。ノードの親指定ではない。
            p (str): parentの別名。
            pxy (Plug | str | None): proxyの別名。
            query (bool): Trueは作成専用のため拒否する。
            q (bool): queryの別名。
            readable (bool): Mayaのreadableフラグ。
            r (bool): readableの別名。
            shortName (str): MayaのshortNameフラグ。
            sn (str): shortNameの別名。
            softMaxValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのsoftMaxValueフラグ。
            smx (float | om2.MAngle | om2.MDistance | om2.MTime): softMaxValueの別名。
            softMinValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのsoftMinValueフラグ。
            smn (float | om2.MAngle | om2.MDistance | om2.MTime): softMinValueの別名。
            storable (bool): Mayaのstorableフラグ。
            s (bool): storableの別名。
            usedAsColor (bool): MayaのusedAsColorフラグ。
            uac (bool): usedAsColorの別名。
            usedAsFilename (bool): MayaのusedAsFilenameフラグ。
            uaf (bool): usedAsFilenameの別名。
            usedAsProxy (bool): MayaのusedAsProxyフラグ。
            uap (bool): usedAsProxyの別名。
            worldSpace (bool): MayaのworldSpaceフラグ。
            ws (bool): worldSpaceの別名。同時指定は不可。
            writable (bool): Mayaのwritableフラグ。
            w (bool): writableの別名。
            cb (bool): channelBoxの別名。
            **kwargs: Mayaへ渡す追加フラグ。
                予約語の短名isは辞書展開で指定する。internalSetとの同時指定は不可。

        Returns:
            Plug | None: getPlug=Trueでは追加したPlug。getPlug=FalseではNone。
                getPlug=Falseでもアトリビュートの追加・既定値等の設定は実行する。

        Raises:
            TypeError: 長短名の同時指定、fastがbool以外、またはunitが文字列以外の場合。
            ValueError: 名前の省略、不正な型接頭辞、解決後のattributeType/dataType併用、query/edit=True、
                またはunitが未対応の単位名の場合。
            NotImplementedError: fastで型や定義フラグが未対応の場合。

        Note:
            子名・成分数と検証可能な型付き既定値は追加前に検査する。
            通常の子追加だけは公開addAttrへ委譲し、overrideを呼ぶ。fastは親子定義を一括構築する。
            Mayaやoverride、作成後の既定値・表示・proxy接続が失敗しても、完了済みの追加は戻さない。
        """
        ...
    def moveAttrOrder(self, name: str, offset: int) -> Node:
        """ユーザー定義アトリビュートを Channel Box 上で前後に移動する。

        Maya にはアトリビュートの並び替え API が無いため、移動元と移動先のうち手前側の
        位置から末尾までのアトリビュートをまとめて削除し、新しい順序で再作成すること
        で実現する(移動先より後ろにある、移動と無関係なアトリビュートも再作成対象に
        含まれる。数値・enum・文字列型のコンパウンドアトリビュートでもマルチアトリビュートでもないトップレベル動的アトリビュート
        のみ対応。対応しないアトリビュートが再作成対象に含まれる場合は何も変更せず
        例外を送出する)。

        並び替えが必要な場合はUndo有効を要求し、再作成中の失敗ではUndoによる復元を試みる。
        成功後は削除前に取得したPlug参照が無効になるため、必要なPlugを取得し直す。

        Args:
            name (str): 移動するユーザー定義アトリビュートのロング名。
            offset (int): 正の値で末尾方向、負の値で先頭方向へ移動する位置数。
                範囲を超える指定は先頭・末尾で止まる。

        Returns:
            Node: 自身。全変更を一回の Undo にまとめる。

        Raises:
            TypeError: 移動範囲にコンパウンドアトリビュート・マルチアトリビュート、または対応しないアトリビュート型が
                含まれる場合。cmdsで再現できないnon-connectable定義も変更前に拒否する。
            ValueError: name がトップレベルのユーザー定義アトリビュート一覧に無い場合。
            RuntimeError: ノードが無効、または安全な復元に必要なUndoが無効な場合。
        """
        ...
    def getPlug(self, name: str) -> Plug:
        """このノードのアトリビュートを、値の評価や要素作成なしで参照する。

        Args:
            name (str): ロング名・ショート名・エイリアス、またはノード名を除いたパス。
                マルチアトリビュートの要素と子を ``input3D[2].input3Dx`` のように指定できる。
                論理番号は0〜2147483647。

        Returns:
            Plug: 自身を所有Nodeとする、型に対応した新しいラッパー。
                未作成のマルチアトリビュートの要素も参照できる。genericは基底Plugで、値の型はget時に解釈する。

        Raises:
            ValueError: nameが空または文字列以外の場合。
            RuntimeError: ノードが無効、または ``input3Dx`` 等の未確定な論理番号を含む参照の場合。
            AttributeError: パスを解決できない、または論理番号が上限を超える場合。
        """
        ...
    def hasAttr(self, name: str) -> bool:
        """アトリビュートパスを解決できるか判定する。

        Args:
            name (str): アトリビュート名またはアトリビュートパス。

        Returns:
            bool: アトリビュートを解決できる場合は ``True``。
        """
        ...
    def getUuid(self) -> str | None:
        """ノードの Maya UUID を取得する。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        ...
    def getName(self) -> str:
        """Mayaコマンドで保持インスタンスを指定できる最短一意名を取得する。

        DAGノードは保持パスのpartialPathName、DGノードはノード名を返す。
        名前はキャッシュせず、呼ぶたびにMayaへ問い合わせる。

        別の階層に同じ短い名前のノードがある場合は、一意にするための親を含む部分パス
        (``grp1|ctrl`` 等)になる。新しい名前を組み立てる元(接尾辞の付け替え等)には
        :meth:`getNodeName` を使う。

        Returns:
            str: 現在の名前。

        Raises:
            RuntimeError: ノードが削除済み・Undoで作成が取り消された(無効な)場合、または
                ノードは有効だが保持するDAGインスタンスが削除された場合。
        """
        ...
    def getFullName(self) -> str:
        """保持インスタンスの完全DAGパス、またはDGノード名を取得する。

        Returns:
            str: DAGではワールドから始まる完全パス。DGではノード名。
                ノード自体が無効なら空文字列。

        Raises:
            RuntimeError: ノードは有効だが保持するDAGインスタンスが削除された場合。
        """
        ...
    def _plugs_from(self, attributes: str | Plug | Iterable[str | Plug]) -> list[Plug]:
        """名前と自身のPlugが混在する指定を、自身のPlugの列へ解決する。

        Args:
            attributes (str | Plug | Iterable[str | Plug]): アトリビュート名・Plug、またはその列。

        Returns:
            list[Plug]: 指定順のPlug。

        Raises:
            AttributeError: 名前のアトリビュートが存在しない場合。
            TypeError: 名前・Plug以外の要素を含む場合。
            ValueError: 名前が空、または別のノードのPlugを含む場合。
        """
        ...
    @staticmethod
    def _create_node(node_type: str, flags: dict, *, fast: bool = ...) -> Node:
        """Mayaノードを作成し、実際のnodeTypeに対応するラッパーを返す(作成処理の唯一の実体)。

        :func:`mlib.createNode` と :meth:`Container.createNode` が呼ぶ内部ヘルパーで、Undoチャンクは
        呼出し側で管理する。Mayaが認識しない型名(標準プラグインのロード後も未知の型)を拒否する。
        cmds.createNodeは未知の型でも例外にせずunknownノードを作るため、ここで止める。型名の照会で
        認識できる名前は作成前に判定する。2026で改名された型(``multDoubleLinear``/``multDL``・
        ``addDoubleLinear``/``addDL``)はどちらの名前もその版の型名へ読み替える。照会では分からない
        名前は、通常経路では作成した結果がunknownノードなら削除して拒否し(Undoの記録は
        作成と削除が対になる)、fastでは作成前に拒否する。jointの下へ作ったjointは、``cmds.joint`` と
        同じく親の ``scale`` を ``inverseScale`` へ接続する(通常経路は作成と同じUndoの単位)。

        Args:
            node_type (str): Maya nodeType名。
            flags (dict): createNodeへ渡す正規化済みのフラグ。parent/pを所有ノード名へ変換する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Node: 作成(sharedでは共有)したノードの、実際のnodeTypeに対応するラッパー。
                登録表の規則で選んだクラス(登録型・動的クラス・Node)になる。

        Raises:
            TypeError: parentが未対応型・複数対象の場合。
            ValueError: nodeType名が空文字列または文字列以外、nameに ``|`` を含む、またはparentが
                空文字列・無効な参照の場合。
            RuntimeError: Mayaが認識しないnodeType名の場合(この版に無い型は、標準で追加された版が
                分かっていればその版を示す)、親名を解決できない場合、またはMayaが
                プラグインのロードやノード作成を拒否した場合。
            NotImplementedError: fastで未対応のフラグを指定した場合。
        """
        ...
    @staticmethod
    def _connect_joint_parent(node: Node, parent: str | None, *, fast: bool) -> Node:
        """jointの下へ作ったjointの inverseScale へ、親の scale を接続する(``cmds.joint`` と同じ)。

        Args:
            node (Node): 作成したノード。
            parent (str | None): 作成時に指定した親の完全パス。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            Node: node。jointでない、または親がjointでない場合は何もしない。
        """
        ...
    def _has_delete_connections(self) -> bool:
        """自身とDAG子孫のDG接続をOMで検査する。

        Returns:
            bool: 接続が一つでもあればTrue。DAG階層関係自体は接続に数えない。
        """
        ...
    @staticmethod
    def _selection_owner(selection: om2.MSelectionList, index: int, name: str | None = ..., plug: bool = ...) -> tuple[om2.MObject, om2.MDagPath | None]:
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
            plug (bool): 要素がアトリビュート(``getPlug`` で取得できる要素)と分かっている場合は True。
                インスタンス化されていない DAG ノードはパスが1つだけなので、失敗すると分かっている
                ``getDagPath()`` の例外処理を省いてそのパスを返す(結果は False の場合と同じ)。

        Returns:
            tuple[om2.MObject, om2.MDagPath | None]: 所有ノードの MObject と、DAG ノードで
                あれば DAG パス(DG ノードは None)。
        """
        ...
    @staticmethod
    def _unique_node_name(mobject: om2.MObject) -> str:
        """ノードの MObject から maya.cmds で一意に解決できる最短名を返す。

        DAG ノードは最初のインスタンスの最短一意パス(``MDagPath.partialPathName()``)、
        DG ノードはノード名を返す。``Node.getName()`` と同じ規則。

        Args:
            mobject (om2.MObject): 依存ノードの MObject。

        Returns:
            str: 最短一意名。
        """
        ...
    @staticmethod
    def _mobject_name(mobject: om2.MObject) -> str:
        """依存ノードの MObject を完全 DAG パスまたは DG ノード名へ変換する。

        Args:
            mobject (om2.MObject): 変換対象。

        Returns:
            str: 完全 DAG パス(最初のインスタンス)、または DG ノード名。

        Raises:
            TypeError: アトリビュート・コンポーネント・データなど依存ノード以外を指す場合。
            ValueError: 空、または削除済みノードの MObject の場合。
        """
        ...
    @staticmethod
    def _resolve_input(value: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> Node:
        """対象を Node インスタンスへ変換する。

        Plug・MPlug は所有ノード、Component・Components は所有シェイプへ解決する。

        Args:
            value (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                変換対象。

        Returns:
            Node: value が Node ならそのまま、Plug なら ``plug.getNode()``、コンポーネントなら
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
        ...
    @staticmethod
    def _input_name(value: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug) -> str:
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
        ...
    def _resolve(self, node: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug) -> None:
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
        ...
    def _alive_fn(self) -> om2.MFnDependencyNode:
        """破棄されていないことを確かめて、保持するノードの MFnDependencyNode を返す。

        Undo の記録から消えて破棄されたノード(削除後の flushUndo 等)へ関数セットを作ると
        Maya が異常終了するため、その前に RuntimeError にする。Undo で戻せる削除済みノード
        (生存中)は従来どおり問い合わせる。

        Returns:
            om2.MFnDependencyNode: このノードの関数セット。

        Raises:
            RuntimeError: ノードが破棄されている場合。
        """
        ...
    def _dependency_fn(self) -> om2.MFnDependencyNode:
        """保持するノードの MFnDependencyNode を返す(作成は初回の1回だけ)。

        名前・アトリビュートの問い合わせのたびに関数セットを作り直さないためのキャッシュ。
        ノードが有効(:meth:`isValid`)であることを呼び出し側で確かめてから使う。

        Returns:
            om2.MFnDependencyNode: このノードの関数セット。
        """
        ...
    @staticmethod
    def _wrap_dag_path(dag_path: om2.MDagPath) -> DagNode:
        """呼出し元が作った有効なMDagPathを、名前や入力の再解決なしでラッパーにする。

        ``Node(dag_path)`` と同じ型選択(nodeTypeの登録、無ければMaya継承に沿って生成したクラス)と
        初期化を行い、入力の種類判定・MDagPathの複製だけを省く。パスが無効なら ``Node(dag_path)`` と
        同じ例外を送出する。子・親の列挙のように、API で直前に取得・延長・短縮したパスにだけ使う。

        Args:
            dag_path (om2.MDagPath): 有効なDAGパス。ラッパーがそのまま保持するため、
                呼出し元は以後このオブジェクトを変更しない。

        Returns:
            DagNode: 実際のノード型に対応するラッパー。
        """
        ...
    @staticmethod
    def _wrap_resolved(mobject: om2.MObject, dag_path: om2.MDagPath | None, handle: om2.MObjectHandle | None = ...) -> Node:
        """API で直前に解決した有効な MObject と DAG パスを、入力の再解決なしでラッパーにする。

        ``Node(dag_path)``・``Node(mobject)`` と同じ型選択(nodeTypeの登録、無ければMaya継承に沿って生成したクラス)と
        初期化(選んだクラスの ``__init__``)を行い、入力の種類判定・有効性検査・複製だけを省く。
        ``_resolve_node`` の戻り値や、``MSelectionList``・``MItDag`` 等から取得したばかりの値にだけ使う。

        Args:
            mobject (om2.MObject): 有効な依存ノードの MObject。DAG ノードでは ``dag_path.node()`` と同じノード。
            dag_path (om2.MDagPath | None): DAG ノードの有効なパス。DG ノードは None。
                ラッパーがそのまま保持するため、呼出し元は以後これらのオブジェクトを変更しない。
            handle (om2.MObjectHandle | None): 呼出し元が mobject から作ったハンドル。指定すると
                ラッパーが保持するハンドルとして使い、作り直さない。

        Returns:
            Node: 実際のノード型に対応するラッパー。
        """
        ...
    @staticmethod
    def _from_name(value: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug) -> Node:
        """ノードを表す入力を解決し、``Node(value)`` と同じ型選択でラッパーにする。

        ``Node._wrap_resolved(*_resolve_node(value))`` の短縮。生成の入口(``Node.__new__``)の
        再判定を省くため、cmds・common のように解決済みの名前・MObject を多数ラップする側で使う。

        Args:
            value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                ``_resolve_node`` が受け付ける入力。

        Returns:
            Node: 実際のノード型に対応するラッパー。

        Raises:
            TypeError: 対応しない入力型の場合。
            RuntimeError: 名前を解決できない、または無効な参照の場合。
        """
        ...
    def _require_named(self) -> None:
        """名前の取得の前にノードが有効か確かめる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ノードが削除済み、またはUndoで作成が取り消された場合。
        """
        ...
    def _require_valid(self, action: str) -> None:
        """操作の前にノードが有効か確かめ、無効なら統一した文言で拒否する。

        Args:
            action (str): 例外メッセージに使う動作の動詞句(``"rename"``・``"delete"`` 等)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ノードが削除済み・無効な場合。文言は
                ``Cannot <action> an invalid <クラス名>``。
        """
        ...
    def _current_dag_path(self) -> om2.MDagPath | None:
        """保持パスを返す。消失したインスタンスを別パスへ切り替えない。

        ノードごと削除された場合は、Undoの記録に残る間(MDagPathが有効のまま古いパスを返す間)も
        無効として扱う。

        Returns:
            om2.MDagPath | None: 保持しているパス。非DAGはNone。

        Raises:
            RuntimeError: 保持しているDAGインスタンス、またはノード自体が削除された場合。
        """
        ...
    @staticmethod
    def _prepare_extra_attr_definition(flags: dict, attribute_type: str | None, child_names: Sequence[str] | None, child_short_names: Sequence[str] | None, child_suffixes: Sequence[str] | None, *, sub_type: str | None = ..., angle_unit: str = ...) -> tuple:
        """追加する型・子数・既定値と単位を、Mayaへの書込み前に解決する。

        Args:
            flags (dict): 正規化済みフラグ。型と単位をこの辞書へ反映する。
            attribute_type (str | None): 明示された型。
            child_names (Sequence[str] | None): 子のロング名。
            child_short_names (Sequence[str] | None): 子のショート名。
            child_suffixes (Sequence[str] | None): 子名の接尾辞。
            sub_type (str | None): 自動生成する子の共通型。doubleAngleなら子の値をradへ換算する。
            angle_unit (str): 角度の数値の単位(``"deg"`` / ``"rad"``)。

        Returns:
            tuple: 数値のコンパウンドアトリビュートの一致情報・子数・作成後に設定する既定値。
        """
        ...
    def _create_extra_attr_definition(self, name: str, flags: dict, numeric: object, count: int, deferred: object, child_names: Sequence[str] | None, child_short_names: Sequence[str] | None, child_suffixes: Sequence[str] | None, sub_type: str | None, *, fast: bool = ...):
        """親と子の定義を従来の順序で追加する。

        通常は子を公開addAttrへ順に委譲する。fastは未登録の親子定義を一括構築して追加する。

        Args:
            name (str): 親アトリビュート名。
            flags (dict): 親へ渡すフラグ。子用の範囲値を取り出す。
            numeric (object): 数値のコンパウンドアトリビュートの一致情報。
            count (int): 子数。
            deferred (object): 子に渡す既定値。
            child_names (Sequence[str] | None): 子のロング名。
            child_short_names (Sequence[str] | None): 子のショート名。
            child_suffixes (Sequence[str] | None): 子名の接尾辞。
            sub_type (str | None): 子の型。
            fast (bool): Trueなら定義をOpenMayaで追加する。
        """
        ...
    def _listed_attributes(self, include_children: bool = ..., keyable: bool = ..., scalar: bool = ...) -> list[om2.MObject]:
        """``cmds.listAttr`` と同じ順で、getPlugs() が返すアトリビュート定義を列挙する。

        トップレベルの定義を定義順に辿り、マルチアトリビュートでないコンパウンドアトリビュートは子を親の直後へ深さ優先で並べる
        (マルチアトリビュートであるコンパウンドアトリビュートの子は、番号の無い名前を Plug にできないため listAttr の結果からも除かれる)。

        Args:
            include_children (bool): Falseならトップレベルの定義だけを返す。
            keyable (bool): Trueならプラグがkeyableのものだけ(``listAttr(keyable=True)``)。
            scalar (bool): Trueなら単一成分の数値・単位・enumだけ(``listAttr(scalar=True)``)。

        Returns:
            list[om2.MObject]: アトリビュート定義。マルチアトリビュートの要素の取得・作成は行わない。
        """
        ...
    def _user_attributes(self, include_children: bool = ...) -> Iterator[om2.MObject]:
        """動的アトリビュートの定義を追加順に列挙する。

        Args:
            include_children (bool): Trueならコンパウンドアトリビュートの子の定義も含める。

        Yields:
            om2.MObject: アトリビュート定義。マルチアトリビュートの要素の取得・作成は行わない。
        """
        ...


class Nodes:
    """型を検証し、入力順のノード参照を保持するコレクション。

    同一ノード・同一DAGパスの重複だけを除外する。異なるインスタンスパスは保持する。
    コピーやスライスは参照を共有し、シーンのノードは複製しない。
    """
    def __iter__(self) -> Iterator[Node]: ...
    @overload
    def __getitem__(self, index: int) -> Node: ...
    @overload
    def __getitem__(self, index: slice) -> Nodes: ...
    item_class: Any
    def __init__(self, names: object | Iterable[object] = ...) -> None:
        """入力からノード参照を解決し、要素型を検証して保持する。

        Args:
            names (object | Iterable[object]): 名前・Node・API参照等、またはその列。単一名も受理する。

        Raises:
            TypeError: 解決結果がitem_classの派生でない場合。
            ValueError: 入力解決で不正な参照を検出した場合。
            RuntimeError: 名前を解決できない、または無効なノードの場合。
        """
        ...
    def __len__(self) -> int:
        """保持要素数。

        Returns:
            int: 保持要素数。
        """
        ...
    def __repr__(self) -> str:
        """具象コレクション名と保持参照を表示する。

        Returns:
            str: 具象コレクション名と保持参照を表示する。
        """
        ...
    def setAttrFlags(self, attributes: str | Plug | Iterable[str | Plug], locked: bool | None = ..., keyable: bool | None = ..., channelBox: bool | None = ..., *, fast: bool = ...) -> Nodes:
        """各ノードへ保持順に :meth:`Node.setAttrFlags` を適用する。

        一括で書き込めるメソッドは :meth:`setAttrFlags`・:meth:`resetAttrs`・:meth:`setLocked`・
        :meth:`setColor`・:meth:`setVisibility`・:meth:`show`・:meth:`hide`・:meth:`setParent`
        (:class:`~mlib.nodes.joint.Joints` は ``setRadius``・``setSegmentScaleCompensate`` も)。
        通常は全体を1回のUndoにまとめる。全要素がメソッドを持つことを書込みの前に確かめる。

        Args:
            attributes (str | Plug | Iterable[str | Plug]): :meth:`Node.setAttrFlags` と同じ。
                Plugを渡す場合は全要素に同じ名前のアトリビュートを使うため、名前で指定する。
            locked (bool | None): :meth:`Node.setAttrFlags` と同じ。
            keyable (bool | None): :meth:`Node.setAttrFlags` と同じ。
            channelBox (bool | None): :meth:`Node.setAttrFlags` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。

        Raises:
            AttributeError: :meth:`Node.setAttrFlags` と同じ。
            TypeError: :meth:`Node.setAttrFlags` と同じ。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。先行した要素の変更は
                自動では戻さない(通常はUndoで戻せる)。
        """
        ...
    def resetAttrs(self, attributes: str | Iterable[str] | None = ..., *, fast: bool = ...) -> list[Plug]:
        """各ノードへ保持順に :meth:`Node.resetAttrs` を適用する。

        Args:
            attributes (str | Iterable[str] | None): :meth:`Node.resetAttrs` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            list[Plug]: 全要素でリセットしたアトリビュート(要素順)。通常は1回のUndoにまとめる。

        Raises:
            AttributeError: :meth:`Node.resetAttrs` と同じ。
            TypeError: :meth:`Node.resetAttrs` と同じ。
            RuntimeError: 無効なノードを含む、またはアトリビュートを書き込めない場合。
        """
        ...
    def setLocked(self, state: bool = ..., *, fast: bool = ...) -> Nodes:
        """各ノードへ保持順に :meth:`Node.setLocked` を適用する。

        Args:
            state (bool): True でロック、False で解除。既定 True。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。

        Raises:
            TypeError: state または fastがbool以外の場合。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。
        """
        ...
    def setColor(self, color: object) -> Nodes:
        """各DAGノードへ保持順に :meth:`~mlib.nodes.dagNode.DagNode.setColor` を適用する。

        Args:
            color (object): :meth:`~mlib.nodes.dagNode.DagNode.setColor` と同じ。

        Returns:
            Nodes: 自身。全体を1回のUndoにまとめる。

        Raises:
            TypeError: DAGノード以外を含む、または色の指定が不正な場合。
            ValueError: 色の指定が不正な場合。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。
        """
        ...
    def setVisibility(self, state: bool, *, fast: bool = ...) -> Nodes:
        """各DAGノードへ保持順に :meth:`~mlib.nodes.dagNode.DagNode.setVisibility` を適用する。

        Args:
            state (bool): 表示状態。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。

        Raises:
            TypeError: DAGノード以外を含む、またはstate・fastがbool以外の場合。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。
        """
        ...
    def show(self, *, fast: bool = ...) -> Nodes:
        """各DAGノードへ保持順に :meth:`~mlib.nodes.dagNode.DagNode.show` を適用する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。

        Raises:
            TypeError: DAGノード以外を含む、またはfastがbool以外の場合。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。
        """
        ...
    def hide(self, *, fast: bool = ...) -> Nodes:
        """各DAGノードへ保持順に :meth:`~mlib.nodes.dagNode.DagNode.hide` を適用する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。

        Raises:
            TypeError: DAGノード以外を含む、またはfastがbool以外の場合。
            RuntimeError: 無効なノードを含む、またはMayaが更新を拒否した場合。
        """
        ...
    def setParent(self, parent: object | None = ..., relative: bool = ..., add: bool = ..., *, fast: bool = ...) -> Nodes:
        """各Transformへ保持順に :meth:`~mlib.nodes.transform.Transform.setParent` を適用する。

        Args:
            parent (object | None): 親。Noneはワールド。
            relative (bool): :meth:`~mlib.nodes.transform.Transform.setParent` と同じ。
            add (bool): :meth:`~mlib.nodes.transform.Transform.setParent` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Nodes: 自身。各要素は親変更後のパスを指す。

        Raises:
            TypeError: Transform以外を含む場合。
            ValueError: :meth:`~mlib.nodes.transform.Transform.setParent` と同じ。
            RuntimeError: 無効なノードを含む、またはMayaが親の変更を拒否した場合。
        """
        ...
    def copy(self) -> Nodes:
        """同じ参照を共有する、同じ具象型の独立した容器を返す。

        Returns:
            Nodes: 同じ参照を共有する、同じ具象型の独立した容器を返す。
        """
        ...
    def _forward(self, method: str, args: tuple, fast: bool | None) -> list:
        """保持順の各ノードへ単数のメソッドを適用し、結果の列を返す。

        全要素がメソッドを持ち有効であることを書込みの前に確かめ、通常は1回のUndoにまとめる。

        Args:
            method (str): 単数のノードのメソッド名。
            args (tuple): 位置引数。
            fast (bool | None): メソッドへ渡すfast。Noneはfast引数の無いメソッド。

        Returns:
            list: 要素順の戻り値。

        Raises:
            TypeError: メソッドを持たない要素を含む場合、またはfastがbool以外の場合。
            RuntimeError: 無効な要素を含む場合。
        """
        ...
    @staticmethod
    def _resolve_inputs(values: object) -> list:
        """対象列を一度だけ展開し、名前とNodeの混在を変換前に拒否する。

        Args:
            values (object): 単体、または対象の反復可能列。既存のAPI型も保持する。

        Returns:
            list: 入力順の対象。空列は空のまま返す。

        Raises:
            TypeError: 同じ対象列に文字列とNodeが混在している場合。
        """
        ...
    @staticmethod
    def _duplicate_key(node: Node) -> tuple[str | None, str]:
        """構築時の重複判定に使うキーを返す。

        Args:
            node (Node): 有効なノード参照。

        Returns:
            tuple[str | None, str]: UUIDと、DAGの完全パスまたはDGのノード名。
        """
        ...
    @staticmethod
    def _validate_inputs(values: list) -> None:
        """展開済み対象列の名前とNodeの混在を拒否する。

        Args:
            values (list): Objectが展開した対象列。値の変換は行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 名前とNodeが混在する場合。
        """
        ...
