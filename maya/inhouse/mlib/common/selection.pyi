# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノード・アトリビュート・コンポーネントの取得時点の選択を保持する。"""

from typing import Any, List, Optional, Tuple
import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel
from ..components.component import Component, Components
from ..components.cv import CV, CVs
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..core.object import _exists, _selection_component, _selection_plug
from ..decorator import undoChunk
from ..nodes.node import Node
from ..plugs.plug import Plug
from .keyframe import Keyframe, Keyframes
from typing import Iterator, Sequence

_NAME_CHUNK: int
_REPR_LIMIT: int
_CHANNEL_BOX_SECTIONS: tuple


class Selection:
    """取得時点の順序で単数参照を保持する。現在選択には自動追従しない。

    コンポーネントは単体へ展開し、同じ完全名は最初だけ残す。
    トポロジーやUVセット変更後の要素の同一性は保証しない。
    選択の復元には :meth:`select` を使い、無効参照はmissingで扱う。
    maya.cmdsへ直接渡す場合、コンパウンドアトリビュート・マルチアトリビュートのPlugは文字列化が必要。
    """
    def __init__(self, items=...) -> None:
        """明示した対象を保持する。省略時は空。

        Args:
            items (Iterable[Node | Plug | Component | Components | Selection | str |
                om2.MObject | om2.MDagPath | om2.MPlug | om2.MSelectionList]): 対象。
                文字列には範囲指定も使える。単一対象も指定可能。MObject・MDagPath は
                ノード、MPlug はアトリビュート、MSelectionList と Selection はその要素として扱う。
                fullName が重複する対象は最初の1件のみを保持する。

        Raises:
            TypeError: 非対応型、またはMesh/NurbsCurve以外のコンポーネントの場合。
            RuntimeError: 名前が解決できない場合。

        Note:
            ノード名だけの文字列(「.」・ワイルドカードを含まないもの)は1つの選択リストへまとめて
            解決するが、対応付けは文字列の順に行うため、保持順と重複の除き方は名前ごとの解決と同じ。
        """
        ...
    def __len__(self) -> int:
        """保持している単体参照の数を返す。

        fullName が重複する対象は構築時に除かれている(__init__ 参照)。

        Returns:
            int: コンポーネントは単体で数え、削除済み参照も含む保持数。
        """
        ...
    def __iter__(self) -> Iterator:
        """保持順に参照を返す。

        Returns:
            Iterator: 保持順に参照を返す。
        """
        ...
    def __getitem__(self, index: int | slice) -> Node | Plug | Component | tuple:
        """単体参照、またはsliceに対応する参照のtupleを返す。

        Args:
            index (int | slice): 保持順の番号または範囲。負の番号もPythonのtupleと同じ意味。

        Returns:
            Node | Plug | Component | tuple: 番号に対応する単体参照、またはsliceに対応するtuple。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用に、型名と保持参照の repr を返す。

        Returns:
            str: ``Selection([Transform('a'), Vertex('boxShape.vtx[5]')])`` のような文字列。
                ``_REPR_LIMIT`` 件を超える場合は先頭だけを表示し、``..., count=N`` を添える。
                削除済みの参照は各型の無効表示(``<Transform invalid>`` 等)になる。
        """
        ...
    @classmethod
    def capture(cls) -> Selection:
        """Mayaの現在選択を保持する。Channel Boxのアトリビュート選択は含めない。

        Returns:
            Selection: Mayaの現在選択を保持する。Channel Boxのアトリビュート選択は含めない。
        """
        ...
    @classmethod
    def getChannelBoxPlugs(cls) -> list[Plug]:
        """メインのChannel Boxで選択中のアトリビュートをPlugとして取得する。

        Channel Boxの表示区分(オブジェクト・シェイプ・入力・出力)ごとに、選択中のアトリビュートと
        その区分に表示中のノードを ``cmds.channelBox`` で照会し、ノードごと・アトリビュートの選択順に
        並べる。:meth:`capture` はChannel Boxの選択を含めないため、こちらを使う。シーンは変更しない。

        Returns:
            list[Plug]: 選択中のアトリビュート。区分の順(オブジェクト→シェイプ→入力→出力)で、
                同じ完全名は最初だけ残す。バッチ・mayapy・Channel Boxが無いGUI、または
                選択が無い場合は空リスト。表示中のノードに存在しないアトリビュートは除く。
        """
        ...
    @classmethod
    def getKeyframes(cls) -> Keyframes:
        """Graph Editor・Dope Sheet で選んでいるキーを取得する。シーンは変更しない。

        Returns:
            Keyframes: 選んでいるキー(Mayaが返すカーブの順、カーブ内は番号の昇順)。選んでいなければ空。
        """
        ...
    @property
    def items(self) -> list[Node | Plug | Component]:
        """list[Node | Plug | Component]: 保持順の対象。削除済み参照も保持する。
        fullName が重複する対象は構築時に除かれている(__init__ 参照)。:meth:`getItems` と同じ値。"""
        ...
    def getItems(self) -> list[Node | Plug | Component]:
        """保持順の対象を新しいリストで取得する。:attr:`items` と同じ値。

        Returns:
            list[Node | Plug | Component]: 保持順の単数参照。削除済み参照も含む。
                リストを変更しても自身の保持内容は変わらない。
        """
        ...
    def getNodes(self, type: str | None = ...) -> list[Node]:
        """ノードとして選ばれた対象を取得する。

        Args:
            type (str | None): 継承型を含むノード型。Noneは全型。

        Returns:
            list[Node]: 有効なノード。コンポーネントの所有者は含めない。
        """
        ...
    def getPlugs(self) -> list[Plug]:
        """有効なアトリビュート参照。Channel Box選択は自動取得しない。

        Returns:
            list[Plug]: 有効なアトリビュート参照。Channel Box選択は自動取得しない。
        """
        ...
    def getComponents(self) -> list[Components]:
        """有効な要素をshapeのDAGパス・種類ごとにまとめる。

        Returns:
            list[Components]: 有効な要素をshapeのDAGパス・種類ごとにまとめる。
        """
        ...
    def getOwners(self) -> list[Node]:
        """有効な対象の所有ノード。DAGパス別に重複を除く。

        Returns:
            list[Node]: 有効な対象の所有ノード。DAGパス別に重複を除く。
        """
        ...
    def filter(self, type: str) -> Selection:
        """ノード型、またはコンポーネント種類で絞った新しい集合を返す。

        Args:
            type (str): joint等のノード型、vertex/edge/face/uv/controlVertex、またはplug。
                コンポーネント記号vtx/e/f/map/cvも使用できる。

        Returns:
            Selection: 有効な該当要素。元の集合は変更しない。
        """
        ...
    def select(self, mode: str = ..., missing: str = ...) -> Selection:
        """保持した対象を現在の選択に反映する。

        ``cmds.select(noExpand=True)`` でUndo有効時に一つのチャンクへ記録する。fast引数は持たない。

        Args:
            mode (str): replaceは置換、addは追加、removeは除外。
            missing (str): skipは無効対象を除外、errorは変更前に例外。

        Returns:
            Selection: 自身。空集合はreplaceだけ選択を解除する。

        Raises:
            ValueError: modeまたはmissingが未対応の場合。
            RuntimeError: missingがerrorで対象が削除済みの場合。
        """
        ...
    @staticmethod
    def _resolve(selection: om2.MSelectionList, name: str | None = ...) -> list[Node | Plug | Component]:
        """MSelectionListをmlibの単体参照へ変換する。非対応要素はTypeError。

        name は要素を追加したときの文字列で、1要素の場合にインスタンス化された
        ノードのアトリビュートの所有インスタンスを求めるために使う(selection_owner 参照)。

        Args:
            selection (om2.MSelectionList): 変換元の選択リスト。
            name (str | None): 単一要素を追加した際の入力名。所有するDAGインスタンスの解決に使う。

        Returns:
            list[Node | Plug | Component]: 選択要素の順序を維持した単数参照の列。
        """
        ...
    def _valid(self, item: Node | Plug | Component) -> bool:
        """削除されたノード・アトリビュート・範囲外要素を検出する。

        Args:
            item (Node | Plug | Component): 有効性を確認する保持参照。

        Returns:
            bool: 参照先が存在し、種類に応じた有効条件を満たすか。
        """
        ...
    def _names(self, missing: str) -> list[str]:
        """変更前に有効な名前を解決する。missing不正はValueError、欠落はRuntimeError。

        Args:
            missing (str): skipなら欠落を除外し、errorなら変更前に例外を送出する。

        Returns:
            list[str]: 有効な対象のフル名。missingがskipなら欠落した参照を除く。
        """
        ...

def _selection_node(selection: om2.MSelectionList, index: int) -> om2.MDagPath | om2.MObject:
    """選択リストのノード要素を、DAGノードは選択されたインスタンスのDAGパスで取得する。

    Args:
        selection (om2.MSelectionList): 選択リスト。
        index (int): 要素の番号。

    Returns:
        om2.MDagPath | om2.MObject: DAGノードならDAGパス、DGノードならMObject。
    """
    ...

def _is_plain_node_name(name: str) -> bool:
    """ワイルドカード・アトリビュート・コンポーネントを含まない、ノード名だけの文字列か判定する。

    Args:
        name (str): 判定する名前。

    Returns:
        bool: 「.」「*」「?」のいずれも含まない空でない文字列なら True。
    """
    ...

def _resolve_names(names: Sequence[str], plugs: bool = ...) -> list[tuple | None]:
    """名前の列を、名前ごとに選択リストを作らずに解決する(ls・Selection の内部補助)。

    ``_NAME_CHUNK`` 件ずつ同じ選択リストを使い回して追加し、追加で要素が丁度1つ増えた名前だけを
    その要素へ対応付ける。対応付けは選択リストの並びではなく names の順に行うため、戻り値の順は
    names と同じになる。次の名前は対応付けず None とし、呼出し元が従来の名前ごとの経路で解決する
    (結果と例外は名前ごとの解決と同じになる)。

    - 解決できない名前(存在しない・一意でない)。
    - 同じリストに既にある要素と重複・統合されて要素が増えない名前(重複は統合せず、名前ごとに返す)。
    - 複数の要素に一致する名前、ワイルドカード(「*」「?」)を含む名前。
    - plugs が True で、要素がアトリビュート(MPlug)にならない名前(コンポーネントなど)。

    Args:
        names (Sequence[str]): 解決する名前。ノード名とアトリビュート名は混ぜずに渡す。
        plugs (bool): True はアトリビュート名(「.」を含む名前)、False はノード名として対応付ける。

    Returns:
        list[tuple | None]: names と同じ長さの列。対応付けた名前は
            ``(MObject, MDagPath | None, MPlug | None)`` (DG ノードの DAG パスと、ノード名の MPlug は None)。
    """
    ...
