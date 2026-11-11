# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのコンポーネント(頂点・エッジ・フェース・CV・UV)と同一シェイプの要素群。"""

import functools
import operator
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple
import maya.api.OpenMaya as om2
from ..core.object import Object, _missing_member_message
from ..decorator import _edit_context, _require_bool
from ..nodes.shape import Shape
from typing import Any, Iterable, Iterator, Sequence
from typing import overload
from typing_extensions import Self

_REPR_LIMIT: int

def _count_name(owner: type | Component) -> str:
    """要素数を返すシェイプのメソッド名(count_attribute)を取り出す。

    Args:
        owner (type | Component): count_attributeを持つ単数型またはそのインスタンス。

    Returns:
        str: シェイプのメソッド名。

    Raises:
        TypeError: 基底クラス等でcount_attributeが文字列でない場合。getattrと同じ例外型にする。
    """
    ...

def _indexed_component_fn(component: om2.MObject) -> om2.MFnSingleIndexedComponent | om2.MFnDoubleIndexedComponent | om2.MFnTripleIndexedComponent | None:
    """コンポーネントの番号の次元に合う OpenMaya の関数セットを返す。

    Args:
        component (om2.MObject): コンポーネント。

    Returns:
        om2.MFnSingleIndexedComponent | om2.MFnDoubleIndexedComponent | om2.MFnTripleIndexedComponent | None:
            番号を持たない種類はNone。
    """
    ...


class Component(Object):
    """シェイプ参照と実番号を保持し、一つのMayaコンポーネントを表す。

    頂点・エッジ・フェース・UV・カーブCVの共通基底。Vertex等の具体型を使う。
    渡されたShapeラッパーを共有し、形状や座標のコピーは保持しない。
    番号は作成時に検証するが、トポロジー変更後も同じ要素を指し続ける保証はない。
    UVの番号範囲は現在のUVセットに従う。
    """
    shape_type: Optional[str] = ...
    component_type: Optional[str] = ...
    count_attribute: Optional[str] = ...
    def __init__(self, shape: Shape, index: int) -> None:
        """シェイプとコンポーネントの実番号を検証して保持する。

        名前やTransformからのShape解決は行わず、渡されたShapeラッパーをそのまま保持する。

        Args:
            shape (Shape): 具体型に対応するMeshまたはNurbsCurveラッパー。
            index (int): 0始まりのMaya番号。__index__対応値も受け付けるが、boolは拒否する。
                負数を末尾からの位置としては扱わない。

        Raises:
            TypeError: シェイプ型が不正、またはindexがboolか整数として扱えない場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def __getattr__(self, name: str):
        """存在しないメソッド・アトリビュートの参照を、近い名前の案内付きのAttributeErrorにする。

        Args:
            name (str): 参照した名前。

        Raises:
            AttributeError: 常に送出する。``'Vertex' has no method '<name>'`` の形で、近い名前の
                メソッドとPyMEL・maya.cmdsの名前に対応するmlibの書き方を案内する。
        """
        ...
    def __eq__(self, other):
        """同じシェイプのインスタンス・種類・番号を指すか比較する。

        Args:
            other: 比較・演算の相手。
        """
        ...
    def __hash__(self):
        """保持シェイプ・種類・番号のハッシュを返す。位置の更新では変化しない。"""
        ...
    def __repr__(self) -> str:
        """デバッグ用に、型名とシェイプの最短一意名を使ったコンポーネント名を返す。

        ``__str__`` (maya.cmds へ渡す完全パス名)とは別の表示で、名前はキャッシュしない。

        Returns:
            str: ``Vertex('boxShape.vtx[5]')`` のような文字列。シェイプの削除・種類違い・
                番号範囲外の場合は ``<Vertex invalid>``。
        """
        ...
    def __str__(self) -> str:
        """コンポーネント名を返す。

        Returns:
            str: 現在の完全パス付きコンポーネント名。
        """
        ...
    @property
    def shape(self) -> Shape:
        """保持している所有シェイプの参照を返す。

        Returns:
            Shape: 構築時と同じラッパー。コピーや有効性の再照会は行わない。
        """
        ...
    @property
    def index(self) -> int:
        """保持しているMayaコンポーネントの実番号を返す。

        Returns:
            int: 0始まりの番号。現在のトポロジーでの範囲は再検証しない。
                カーブCVはOpenMayaの番号で、周期末尾のcmds用表記とは異なる場合がある。
        """
        ...
    def getFullName(self) -> str:
        """現在の DAG パスを使ってコンポーネント名を取得する。

        Returns:
            str: シェイプの完全パスとコンポーネントの種類・番号を含む名前。
        """
        ...
    def isValid(self) -> bool:
        """シェイプの生存・種類と、保持番号の現在の範囲を照会する。

        Returns:
            bool: 現在のシェイプで保持番号を参照できればTrue。

        Note:
            トポロジー変更前後で同じ要素を指す保証はない。
            UVは現在のUVセットの番号範囲を使う。
        """
        ...
    @staticmethod
    def _from_api(path: om2.MDagPath, component: om2.MObject) -> list[Component]:
        """OpenMayaのコンポーネントを、要素別の参照へ展開する。

        明示番号はgetElements()の順序、complete指定は現在のShapeの全番号を使う。
        各参照は同じShapeラッパーを共有し、座標値は取得しない。

        Args:
            path (MDagPath): 所有Shapeのインスタンスパス。
            component (MObject): Meshの頂点/エッジ/フェース/UV/頂点フェース、NurbsCurveのCV、
                NurbsSurfaceのCV、またはLatticeの点。

        Returns:
            list[Component]: 新しい単数ラッパーのリスト。complete指定は0から要素数-1の順。

        Raises:
            TypeError: 非対応のコンポーネント種類、または対応しないShape型の場合。
            IndexError: 明示番号が現在のShapeの範囲外の場合。
            RuntimeError: 所有Shapeを解決・参照できない場合。
        """
        ...
    @staticmethod
    def _resolve_input(value: str | Component | tuple) -> Component:
        """コンポーネント名・既存参照・APIの組から、一つの要素参照を解決する。

        既存Componentは再検証せず同じラッパーを返す。文字列はMSelectionListで解決し、
        API入力は単一番号型かと要素数を確認してから展開する。
        単数でないと判定した入力は、展開前に拒否する。展開後も一件であることを確認する。

        Args:
            value (str | Component | tuple): コンポーネント名、既存参照、または
                (MDagPath, MObject)。:meth:`_from_api` が展開できる種類を対象とする。

        Returns:
            Component: 具体型の参照。既存入力以外は新しいラッパー。

        Raises:
            TypeError: 入力型またはコンポーネント種類が非対応の場合。
            ValueError: 空文字、または解決対象が単一要素でない場合。
            IndexError: 明示番号が現在のShapeの範囲外の場合。
            RuntimeError: 名前や所有Shapeを解決できない場合。
        """
        ...
    def _get_coordinate(self, axis, **space):
        """指定軸の現在座標を返す。axisは派生クラスが検証済みの整数。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            **space: 座標空間の指定。worldSpace=Trueでワールド空間。
        """
        ...
    def _require_valid(self) -> None:
        """現在のシェイプ型と番号を再検査する。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    @classmethod
    def _element_count(cls, shape: Shape) -> int:
        """シェイプが現在持つこの種類の要素数を返す。

        Args:
            shape (Shape): 型を検査済みのシェイプ。

        Returns:
            int: 要素数。既定は ``count_attribute`` のシェイプのメソッドを呼ぶ。多次元の番号を持つ型は上書きする。
        """
        ...
    @staticmethod
    def _validate_shape(shape: Shape, shape_type: str | None) -> None:
        """生存と型を検査する。要素数は呼出し側で必要な時に照会する。

        Args:
            shape (Shape): 検査する参照。
            shape_type (str | None): 必要なMayaシェイプ型。基底クラスのNoneはどのシェイプとも一致しない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: シェイプ参照または型が不正な場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    @staticmethod
    def _require_index_range(index: int, count: int) -> None:
        """正規化済みの実番号を、呼出し内で照会した要素数と比較する。

        Args:
            index (int): コンポーネントの実番号。
            count (int): 現在の要素数。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 番号が範囲外の場合。
        """
        ...
_COMPONENT_INIT: Any
_COMPONENT_REQUIRE_VALID: Any
_COMPONENT_INDEX: Any
_COMPONENT_SHAPE: Any
_COMPONENT_VALIDATE_SHAPE: Any
_COMPONENT_REQUIRE_INDEX_RANGE: Any


class Components:
    """同一シェイプ・同じ種類の実番号を、初出順の重複なしtupleで保持する。

    Vertices等の具体型が、単数参照の列挙と一括操作を担当する。
    Shapeラッパーを共有し、番号列は作成時に固定する。形状編集後の要素追加や削除には
    自動追従せず、トポロジー変更後の要素の同一性も保証しない。
    角括弧は保持列内の位置で、Mayaの実番号ではない。
    ``+``(同じシェイプ・同じ種類どうし)・``==``・:meth:`sort` に対応する。``==`` を定義するため、
    listと同じくハッシュ不可(dictのキー・setの要素にできない)。
    """
    def __iter__(self) -> Iterator[Component]: ...
    @overload
    def __getitem__(self, index: int) -> Component: ...
    @overload
    def __getitem__(self, index: slice) -> Components: ...
    component_class: Any
    __hash__: None
    _shape: 'Shape'
    _indices: Tuple[int, ...]
    def __init__(self, shape: Shape, indices: Iterable[int] | None = ...) -> None:
        """指定番号を検証し、初出順を維持して重複を除いて保持する。

        番号をソートせず、不変tupleへ取り込む。一般の反復入力や独自の__index__は
        単数ラッパーを一件ずつ構築し、拡張側の検証や途中例外を省略しない。

        Args:
            shape (Shape): 具体型に対応するShapeラッパー。同じ参照を保持する。
            indices (Iterable[int] | None): Mayaの実番号。Noneは構築時の全要素を昇順で保持する。
                空列は空集合。各番号は__index__に対応し、boolと負数は拒否する。

        Raises:
            TypeError: シェイプ型または番号の型が不正な場合。
            IndexError: いずれかの番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def __len__(self) -> int:
        """保持している重複なし番号の件数を返す。

        Returns:
            int: 構築時に固定した件数。現在のShapeの要素数や生存は照会しない。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用に、型名と範囲へまとめたコンポーネント名を返す。

        保持順で+1ずつ連続する番号を ``[start:end]`` へまとめ、シェイプは最短一意名で表示する。
        まとめた名前が ``_REPR_LIMIT`` 個を超える場合は先頭だけを表示し、件数を添える。

        Returns:
            str: ``CVs('curveShape.cv[0:7]')``、``Vertices('boxShape.vtx[0:2]', 'boxShape.vtx[5]')``、
                多数なら ``Vertices('boxShape.vtx[0]', ..., count=120)``、空なら
                ``Vertices('boxShape', count=0)``。無効なら ``<Vertices invalid>``。
        """
        ...
    def __eq__(self, other: Components | list | tuple) -> bool:
        """同じシェイプ・同じ種類・同じ並びの番号か比較する。

        list・tupleとは、各位置の単数コンポーネントを ``==`` で比べる。

        Args:
            other (Components | list | tuple): 比較の相手。

        Returns:
            bool: 等しければTrue。対応しない型はNotImplemented。
        """
        ...
    def __getattr__(self, name: str) -> Callable[..., list]:
        """単数のコンポーネントのメソッドを、全要素へ保持順に呼ぶ関数として取得する。

        このコレクションに無い公開メソッド名を取得すると、保持順の各単数参照(``component_class``)の
        同名メソッドを同じ引数で呼び、戻り値を保持順のリストで返す関数になる。通常は1回のUndoにまとめ、
        ``fast=True`` はそのまま各メソッドへ渡してUndoのまとめは行わない。後続の要素で失敗しても、
        先行の変更は自動では戻さない。

        Args:
            name (str): 単数のコンポーネントの公開メソッド名。

        Returns:
            Callable[..., list]: 各要素のメソッドを呼び、戻り値を保持順のリストで返す関数。

        Raises:
            AttributeError: 先頭 ``_`` の名前、または ``component_class`` が持たないメソッド名の場合。
        """
        ...
    def __add__(self, other: Components | list | tuple) -> Components:
        """同じシェイプ・同じ種類の要素を後ろへ結合した、左辺と同じ型の新しいコレクションを返す。

        構築と同じく、初出順を保って重複した番号を除く。

        Args:
            other (Components | list | tuple): 同じシェイプ・同じ種類のコレクション、または単数
                コンポーネントの列。

        Returns:
            Components: 左辺と同じ具象型の新しいコレクション。自身と相手は変更しない。

        Raises:
            TypeError: シェイプまたはコンポーネントの種類が異なる要素を含む場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def __radd__(self, other: list | tuple) -> Components:
        """左辺がlist・tupleの結合で、右辺と同じ型の新しいコレクションを返す。

        Args:
            other (list | tuple): 前へ結合する、同じシェイプ・同じ種類の単数コンポーネントの列。

        Returns:
            Components: 右辺(自身)と同じ具象型の新しいコレクション。

        Raises:
            TypeError: シェイプまたはコンポーネントの種類が異なる要素を含む場合。
        """
        ...
    @property
    def shape(self) -> Shape:
        """保持している所有シェイプの参照を返す。

        Returns:
            Shape: 構築時と同じラッパー。コピーや有効性の再照会は行わない。
        """
        ...
    @property
    def indices(self) -> tuple[int, ...]:
        """保持しているMaya実番号の不変tupleを返す。

        Returns:
            tuple[int, ...]: 初出順で重複を除いた保持値そのもの。新しいコピーは作らず、
                現在の番号範囲も再検証しない。カーブCVではOpenMayaの番号を保持する。
        """
        ...
    def sort(self, key: Callable[[Component], object] | None = ..., reverse: bool = ...) -> Self:
        """保持する番号列をその場で並べ替え、並べ替えた自身を返す。

        ``key`` を省略した場合はMayaの実番号の順にする。``key`` を渡した場合は、保持順の単数
        コンポーネント(``__iter__`` と同じ新しい参照)を引数に呼ぶ。並べ替えるのはこの
        コレクションの番号列だけで、スライス・``+`` で作った別のコレクションの順序は変わらない
        (シェイプのラッパーは共有している)。

        Args:
            key (Callable[[Component], object] | None): 各要素から比較用の値を返す関数。Noneは実番号。
            reverse (bool): Trueなら降順。

        Returns:
            Components: 並べ替えた自身(新しいコレクションは作らない)。派生クラスでは自身の型。

        Raises:
            TypeError: keyが呼び出せない、またはreverseがbool以外の場合。
        """
        ...
    def getFullNames(self) -> list[str]:
        """保持順の完全コンポーネント名を取得する。

        全番号の再検証はまとめて1回だけ行う。

        Returns:
            list[str]: ``|cube|cubeShape.vtx[3]`` のような要素ごとの名前。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getCompactNames(self) -> list[str]:
        """保持順で連続する番号を範囲指定にまとめた名前を取得する。

        ``maya.cmds`` へ多数の要素を渡す用途向け(``mlib.select`` などが使う)。
        番号 ``[0, 1, 2, 5, 3]`` は ``vtx[0:2]``・``vtx[5]``・``vtx[3]`` になり、
        番号をソートせず、保持順で+1ずつ連続する区間だけをまとめる。
        全番号の再検証はまとめて1回だけ行う。

        Returns:
            list[str]: ``|cube|cubeShape.vtx[0:2]`` のような名前。空のコレクションは空リスト。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def isValid(self) -> bool:
        """シェイプの生存・種類と、全保持番号の現在の範囲を照会する。

        Returns:
            bool: 全番号を参照できればTrue。空集合も生存する対応シェイプならTrue。

        Note:
            トポロジー変更前後で同じ要素を指す保証はない。
            UVは現在のUVセットの番号範囲を使う。
        """
        ...
    def isComplete(self) -> bool:
        """シェイプが現在持つこの種類の要素を、すべて保持しているか照会する。

        保持順は問わない。``cmds.ls(..., flatten=True)`` で得る全要素(``vtx[*]`` 等)と同じ集まりかを調べる。

        Returns:
            bool: 全要素を保持していればTrue。要素が0個のシェイプで空の集まりもTrue。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def _matching_indices(self, other: Components | list | tuple) -> tuple[int, ...]:
        """結合する相手から、同じシェイプ・同じ種類であることを確かめた番号列を取り出す。

        Args:
            other (Components | list | tuple): 結合の相手。

        Returns:
            tuple[int, ...]: 相手の番号を保持順に並べた列。

        Raises:
            TypeError: シェイプまたはコンポーネントの種類が異なる場合。
        """
        ...
    def _has_standard_component(self, component_class: type | None = ...) -> bool:
        """単数の構築・検査・番号取得が標準の具体型か判定する。

        Args:
            component_class (type | None): 明示した単数型。Noneなら自身の単数型。

        Returns:
            bool: 利用側の派生型や置換された単数処理でなければTrue。
        """
        ...
    def _has_standard_shape(self, component_class: type | None = ...) -> bool:
        """標準のシェイプ型か判定し、利用側の形状派生の照会処理を維持する。

        Args:
            component_class (type | None): 要素数を照会する単数型。Noneなら自身の型。

        Returns:
            bool: MeshまたはNurbsCurveそのものならTrue。
        """
        ...
    def _uses_standard_iteration(self, component_class: type) -> bool:
        """単数または反復が拡張されていない場合だけ一括照会を許可する。

        Args:
            component_class (type): 操作の標準単数型。

        Returns:
            bool: 単数・反復・シェイプが標準の実装ならTrue。
        """
        ...
    def _uses_standard_vertices(self) -> bool:
        """頂点の中間参照で呼ばれる構築・反復も標準処理か判定する。

        Returns:
            bool: Vertices/Vertexへの利用側の差替えを省略しなければTrue。
        """
        ...
    def _mesh_vertex_indices(self, count_name: str, vertices_method: str) -> list[int]:
        """現在のメッシュから保持順に隣接頂点番号を集める。

        Args:
            count_name (str): MFnMeshのコンポーネント数プロパティ名。
            vertices_method (str): 要素の頂点番号を返すMFnMeshメソッド名。

        Returns:
            list[int]: 接続順を保った頂点番号。重複除去は呼出元のVerticesへ委ねる。
        """
        ...
    def _name_prefix(self) -> str:
        """全番号をまとめて再検証し、``<シェイプの完全パス>.<種類>`` を返す。

        Returns:
            str: ``|cube|cubeShape.vtx`` のような接頭辞。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def _repr_indices(self) -> Sequence[int]:
        """repr に表示する番号を保持順で返す。カーブCVはcmds用の番号へ写す。

        Returns:
            Sequence[int]: 表示用の番号列。
        """
        ...
    def _require_valid(self):
        """シェイプと保持番号を一括検証し、名前や単数ラッパーは生成しない。

        Raises:
            TypeError: シェイプ型が異なる場合。
            IndexError: トポロジー変更により番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    @staticmethod
    def _range_name(prefix: str, start: int, end: int) -> str:
        """範囲指定のコンポーネント名を作る。

        Args:
            prefix (str): ``<シェイプの完全パス>.<種類>``。
            start (int): 先頭の番号。
            end (int): 末尾の番号(先頭と同じなら単体)。

        Returns:
            str: ``prefix[start]`` または ``prefix[start:end]``。
        """
        ...
    def _get_coordinate(self, axis, **space):
        """保持順の指定軸の値を返す。axisは派生クラスが選択する。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            **space: 座標空間の指定。worldSpace=Trueでワールド空間。
        """
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
_COMPONENTS_INIT: Any
_COMPONENTS_ITER: Any

def _flat_input(cls, shape: Shape, items: list[int | Sequence[int]]) -> list[int]:
    """番号の指定(平坦な実番号、または多次元の番号のtuple)を、平坦な実番号のリストへ変換する。

    多次元の番号はシェイプの現在の形状で変換し、範囲外ならIndexErrorにする。平坦な実番号の範囲は
    呼出し側が検査する。

    Args:
        cls (type): ``index_size`` と ``_flat_indices`` を持つ多次元の番号の単数型。
        shape (Shape): 型を検査済みのシェイプ。
        items (list[int | Sequence[int]]): 番号の指定。

    Returns:
        list[int]: 指定順の平坦な実番号。

    Raises:
        TypeError: 番号が整数として扱えない、またはboolの場合。
        ValueError: 多次元の番号の数が ``index_size`` と違う場合。
        IndexError: 多次元の番号が範囲外の場合。
    """
    ...

def _component_name(prefix: str, numbers: Sequence[int]) -> str:
    """``<シェイプ>.<種類>`` と多次元の番号から ``cv[1][2]`` のようなコンポーネント名を作る。

    Args:
        prefix (str): ``<シェイプの名前>.<種類>``。
        numbers (Sequence[int]): cmds用の番号。

    Returns:
        str: コンポーネント名。
    """
    ...


class _MultiIndexComponent:
    """複数の番号(``cv[u][v]``・``pt[s][t][u]``・``vtxFace[v][f]``)を持つ単数コンポーネントの共通処理。

    :class:`Component` の具体型と組み合わせる(``class SurfaceCV(_MultiIndexComponent, PointComponent)``)。
    保持する :attr:`~Component.index` は、要素を一列に並べた平坦な実番号で、``==``・ハッシュ・
    :attr:`Components.indices` はこの番号を使う。多次元の番号は :meth:`getMultiIndex` で照会する。
    具体型は ``index_size`` と、``_element_count``・``_multi_indices``・``_flat_indices`` を定義する。
    """
    index_size: int
    def __init__(self, shape: Shape, index: int | Sequence[int]) -> None:
        """シェイプと番号を検証して保持する。

        Args:
            shape (Shape): 具体型に対応するシェイプのラッパー。
            index (int | Sequence[int]): 平坦な実番号、または多次元の番号(``(u, v)`` 等)。
                boolと負数は拒否する。

        Raises:
            TypeError: シェイプ型が不正、または番号が整数として扱えない・boolの場合。
            ValueError: 多次元の番号の数が違う場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getFullName(self) -> str:
        """現在のDAGパスと多次元の番号を使ってコンポーネント名を取得する。

        Returns:
            str: ``|plane|planeShape.cv[1][2]`` のような名前。周期曲面の重複CVは先頭の対応番号で表す。
        """
        ...
    def getMultiIndex(self) -> tuple[int, ...]:
        """保持する要素の多次元の番号を、現在の形状から照会する。

        Returns:
            tuple[int, ...]: ``(u, v)``・``(s, t, u)``・``(頂点, フェース)`` のような番号。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...


class _MultiIndexComponents:
    """複数の番号を持つコンポーネントの集まりの共通処理。

    :class:`Components` の具体型と組み合わせる。番号の指定には平坦な実番号と多次元の番号を混ぜられ、
    保持は平坦な実番号で行う。名前は範囲へまとめない。
    """
    def __init__(self, shape: Shape, indices: Iterable[int | Sequence[int]] | None = ...) -> None:
        """指定番号を検証し、初出順を維持して重複を除いて保持する。

        Args:
            shape (Shape): 具体型に対応するシェイプのラッパー。
            indices (Iterable[int | Sequence[int]] | None): 平坦な実番号または多次元の番号の列。
                Noneは構築時の全要素を平坦な実番号の昇順で保持する。

        Raises:
            TypeError: シェイプ型または番号の型が不正な場合。
            ValueError: 多次元の番号の数が違う場合。
            IndexError: いずれかの番号が現在の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用に、型名と先頭の要素の名前を返す。

        Returns:
            str: ``SurfaceCVs('planeShape.cv[0][0]', 'planeShape.cv[0][1]')``、多数なら件数を添える。
                空なら ``SurfaceCVs('planeShape', count=0)``、無効なら ``<SurfaceCVs invalid>``。
        """
        ...
    def getFullNames(self) -> list[str]:
        """保持順の完全コンポーネント名を取得する。

        Returns:
            list[str]: ``|plane|planeShape.cv[1][2]`` のような要素ごとの名前。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getCompactNames(self) -> list[str]:
        """cmds用の名前を返す。多次元の番号は範囲へまとめず、:meth:`getFullNames` と同じ名前を返す。

        Returns:
            list[str]: 保持順のコンポーネント名。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
