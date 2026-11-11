"""Mayaのコンポーネント(頂点・エッジ・フェース・CV・UV)と同一シェイプの要素群。"""

import functools
import operator
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

import maya.api.OpenMaya as om2

from ..core.object import Object, _missing_member_message
from ..decorator import _edit_context, _require_bool

if TYPE_CHECKING:
    from ..nodes.shape import Shape


#: Components の repr に表示する、範囲へまとめた名前の最大数。
_REPR_LIMIT = 4


def _count_name(owner):
    """要素数を返すシェイプのメソッド名(count_attribute)を取り出す。

    Args:
        owner (type | Component): count_attributeを持つ単数型またはそのインスタンス。

    Returns:
        str: シェイプのメソッド名。

    Raises:
        TypeError: 基底クラス等でcount_attributeが文字列でない場合。getattrと同じ例外型にする。
    """
    name = owner.count_attribute
    if not isinstance(name, str):
        raise TypeError(f"attribute name must be string, not '{type(name).__name__}'")
    return name


def _indexed_component_fn(component):
    """コンポーネントの番号の次元に合う OpenMaya の関数セットを返す。

    Args:
        component (om2.MObject): コンポーネント。

    Returns:
        om2.MFnSingleIndexedComponent | om2.MFnDoubleIndexedComponent | om2.MFnTripleIndexedComponent | None:
            番号を持たない種類はNone。
    """
    if component.hasFn(om2.MFn.kSingleIndexedComponent):
        return om2.MFnSingleIndexedComponent(component)
    if component.hasFn(om2.MFn.kDoubleIndexedComponent):
        return om2.MFnDoubleIndexedComponent(component)
    if component.hasFn(om2.MFn.kTripleIndexedComponent):
        return om2.MFnTripleIndexedComponent(component)
    return None


class Component(Object):
    """シェイプ参照と実番号を保持し、一つのMayaコンポーネントを表す。

    頂点・エッジ・フェース・UV・カーブCVの共通基底。Vertex等の具体型を使う。
    渡されたShapeラッパーを共有し、形状や座標のコピーは保持しない。
    番号は作成時に検証するが、トポロジー変更後も同じ要素を指し続ける保証はない。
    UVの番号範囲は現在のUVセットに従う。
    """

    # シェイプ型・cmds用の種類名・要素数を返すシェイプのメソッド名。具体型が定義し、基底ではNone。
    shape_type: Optional[str] = None
    component_type: Optional[str] = None
    count_attribute: Optional[str] = None

    def __init__(self, shape, index):
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
        self._shape = shape
        if isinstance(index, bool):
            raise TypeError("Component index must be an integer, not bool")
        self._index = operator.index(index)
        self._require_valid()

    def __getattr__(self, name):
        """存在しないメソッド・アトリビュートの参照を、近い名前の案内付きのAttributeErrorにする。

        Args:
            name (str): 参照した名前。

        Raises:
            AttributeError: 常に送出する。``'Vertex' has no method '<name>'`` の形で、近い名前の
                メソッドとPyMEL・maya.cmdsの名前に対応するmlibの書き方を案内する。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        raise AttributeError(_missing_member_message(self, name))

    def __eq__(self, other):
        """同じシェイプのインスタンス・種類・番号を指すか比較する。

        Args:
            other: 比較・演算の相手。
        """
        if not isinstance(other, Component):
            return NotImplemented
        return (self._shape == other._shape and self.component_type == other.component_type
                and self._index == other._index)

    def __hash__(self):
        """保持シェイプ・種類・番号のハッシュを返す。位置の更新では変化しない。"""
        return hash((self._shape, self.component_type, self._index))

    def __repr__(self):
        """デバッグ用に、型名とシェイプの最短一意名を使ったコンポーネント名を返す。

        ``__str__`` (maya.cmds へ渡す完全パス名)とは別の表示で、名前はキャッシュしない。

        Returns:
            str: ``Vertex('boxShape.vtx[5]')`` のような文字列。シェイプの削除・種類違い・
                番号範囲外の場合は ``<Vertex invalid>``。
        """
        cls = type(self).__name__
        if not self.isValid():
            return f"<{cls} invalid>"
        full = self.getFullName()
        return f"{cls}({self._shape.getName() + full[full.rindex('.'):]!r})"

    def __str__(self):
        """コンポーネント名を返す。

        Returns:
            str: 現在の完全パス付きコンポーネント名。
        """
        return self.getFullName()

    @property
    def shape(self):
        """保持している所有シェイプの参照を返す。

        Returns:
            Shape: 構築時と同じラッパー。コピーや有効性の再照会は行わない。
        """
        return self._shape

    @property
    def index(self):
        """保持しているMayaコンポーネントの実番号を返す。

        Returns:
            int: 0始まりの番号。現在のトポロジーでの範囲は再検証しない。
                カーブCVはOpenMayaの番号で、周期末尾のcmds用表記とは異なる場合がある。
        """
        return self._index

    def getFullName(self):
        """現在の DAG パスを使ってコンポーネント名を取得する。

        Returns:
            str: シェイプの完全パスとコンポーネントの種類・番号を含む名前。
        """
        self._require_valid()
        return f"{self._shape.getFullName()}.{self.component_type}[{self._index}]"

    def isValid(self):
        """シェイプの生存・種類と、保持番号の現在の範囲を照会する。

        Returns:
            bool: 現在のシェイプで保持番号を参照できればTrue。

        Note:
            トポロジー変更前後で同じ要素を指す保証はない。
            UVは現在のUVセットの番号範囲を使う。
        """
        try:
            self._require_valid()
        except (RuntimeError, TypeError, ValueError, IndexError):
            return False
        return True

    @staticmethod
    def _from_api(path, component):
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
        # nodes・具体コンポーネント型はこのモジュールを継承・importするため、循環を避けて使う時点で読み込む。
        from ..nodes.node import Node
        from .vertex import Vertex
        from .edge import Edge
        from .face import Face
        from .uv import UV
        from .cv import CV
        from .latticePoint import LatticePoint
        from .surfaceCV import SurfaceCV
        from .vertexFace import VertexFace
        types = {
            om2.MFn.kMeshVertComponent: Vertex,
            om2.MFn.kMeshEdgeComponent: Edge,
            om2.MFn.kMeshPolygonComponent: Face,
            om2.MFn.kMeshMapComponent: UV,
            om2.MFn.kCurveCVComponent: CV,
            om2.MFn.kSurfaceCVComponent: SurfaceCV,
            om2.MFn.kLatticeComponent: LatticePoint,
            om2.MFn.kMeshVtxFaceComponent: VertexFace,
        }
        cls = types.get(component.apiType())
        if cls is None:
            raise TypeError("Only mesh vertices/edges/faces/UVs/vertex faces, curve CVs, "
                            "surface CVs and lattice points are supported")
        shape = Node(path)
        fn = _indexed_component_fn(component)
        if fn.isComplete:
            indices = range(cls._element_count(shape))
        else:
            indices = fn.getElements()
        return [cls(shape, index) for index in indices]

    @staticmethod
    def _resolve_input(value):
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
        if isinstance(value, Component):
            return value
        if isinstance(value, str):
            if not value:
                raise ValueError("Expected a non-empty component name")
            selection = om2.MSelectionList()
            selection.add(value)
            if selection.length() != 1:
                raise ValueError("Expected one component")
            value = selection.getComponent(0)
        if not (isinstance(value, tuple) and len(value) == 2
                and isinstance(value[0], om2.MDagPath) and isinstance(value[1], om2.MObject)):
            raise TypeError("Expected a component reference, name or (MDagPath, MObject)")
        # 単数解決では、広い範囲を単体ラッパーへ展開する前に拒否する。
        component_fn = _indexed_component_fn(value[1])
        if component_fn is None:
            raise TypeError("Expected an indexed component")
        if component_fn.isComplete:
            count = component_fn.getCompleteData()
            if isinstance(count, tuple):
                # 多次元の番号では、各方向の要素数の積が全体の数。
                count = functools.reduce(operator.mul, count, 1)
        else:
            count = component_fn.elementCount
        if count != 1:
            raise ValueError("Expected one component; use Selection for ranges")
        items = Component._from_api(*value)
        if len(items) != 1:
            raise ValueError("Expected one component; use Selection for ranges")
        return items[0]

    def _get_coordinate(self, axis, **space):
        """指定軸の現在座標を返す。axisは派生クラスが検証済みの整数。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            **space: 座標空間の指定。worldSpace=Trueでワールド空間。
        """
        return self.getPosition(**space)[axis]

    def _require_valid(self):
        """現在のシェイプ型と番号を再検査する。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._validate_shape(self._shape, self.shape_type)
        if self._index < 0:
            self._require_index_range(self._index, 0)
        self._require_index_range(self._index, self._element_count(self._shape))

    @classmethod
    def _element_count(cls, shape):
        """シェイプが現在持つこの種類の要素数を返す。

        Args:
            shape (Shape): 型を検査済みのシェイプ。

        Returns:
            int: 要素数。既定は ``count_attribute`` のシェイプのメソッドを呼ぶ。多次元の番号を持つ型は上書きする。
        """
        return getattr(shape, _count_name(cls))()

    @staticmethod
    def _validate_shape(shape, shape_type):
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
        if not callable(getattr(shape, "isValid", None)):
            raise TypeError("shape must be an mlib shape wrapper")
        if not shape.isValid():
            raise RuntimeError("Component shape is invalid")
        if shape.getType() != shape_type:
            raise TypeError(f"Expected a {shape_type} shape")

    @staticmethod
    def _require_index_range(index, count):
        """正規化済みの実番号を、呼出し内で照会した要素数と比較する。

        Args:
            index (int): コンポーネントの実番号。
            count (int): 現在の要素数。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 番号が範囲外の場合。
        """
        if not 0 <= index < count:
            raise IndexError(f"Component index out of range: {index}")


_COMPONENT_INIT = Component.__init__
_COMPONENT_REQUIRE_VALID = Component._require_valid
_COMPONENT_INDEX = Component.index
_COMPONENT_SHAPE = Component.shape
_COMPONENT_VALIDATE_SHAPE = Component._validate_shape
_COMPONENT_REQUIRE_INDEX_RANGE = Component._require_index_range


class Components:
    """同一シェイプ・同じ種類の実番号を、初出順の重複なしtupleで保持する。

    Vertices等の具体型が、単数参照の列挙と一括操作を担当する。
    Shapeラッパーを共有し、番号列は作成時に固定する。形状編集後の要素追加や削除には
    自動追従せず、トポロジー変更後の要素の同一性も保証しない。
    角括弧は保持列内の位置で、Mayaの実番号ではない。
    ``+``(同じシェイプ・同じ種類どうし)・``==``・:meth:`sort` に対応する。``==`` を定義するため、
    listと同じくハッシュ不可(dictのキー・setの要素にできない)。
    """

    component_class = Component
    __hash__ = None  # type: ignore[assignment]
    # __init__で設定する保持値。派生クラス(別モジュール)からも参照する。
    _shape: "Shape"
    _indices: Tuple[int, ...]

    if TYPE_CHECKING:
        # 座標の取得は派生クラス(PointComponents・UVs)が実装する。
        getPosition: Callable[..., List[Any]]

    def __init__(self, shape, indices=None):
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
        self._shape = shape
        Component._validate_shape(shape, self.component_class.shape_type)
        selected = range(self.component_class._element_count(shape)) if indices is None else indices
        # 一般の反復入力や独自__index__は従来どおり一件ずつ構築する。
        # これにより入力の副作用・途中例外・利用側constructor/_validateを維持する。
        if (self._has_standard_component() and self._has_standard_shape()
                and (type(selected) is range or (type(selected) in (list, tuple)
                     and all(type(index) is int for index in selected)))):
            count = len(selected) if indices is None else None
            for index in selected:
                if index < 0:
                    Component._require_index_range(index, 0)
                if count is None:
                    count = self.component_class._element_count(shape)
                Component._require_index_range(index, count)
            self._indices = tuple(dict.fromkeys(selected))
        else:
            self._indices = tuple(dict.fromkeys(self.component_class(shape, index).index for index in selected))

    def __len__(self):
        """保持している重複なし番号の件数を返す。

        Returns:
            int: 構築時に固定した件数。現在のShapeの要素数や生存は照会しない。
        """
        return len(self._indices)

    def __iter__(self):
        """保持番号の順に、新しい単数コンポーネント参照を作って反復する。

        各参照の構築時に現在のShapeと番号を検証する。全件を先に検証する処理ではないため、
        途中で失敗した場合も、それ以前の参照はすでにyieldされている。座標は取得しない。

        Yields:
            Component: 同じShapeラッパーを共有する新しい単数参照。
        """
        for index in self._indices:
            yield self.component_class(self._shape, index)

    def __repr__(self):
        """デバッグ用に、型名と範囲へまとめたコンポーネント名を返す。

        保持順で+1ずつ連続する番号を ``[start:end]`` へまとめ、シェイプは最短一意名で表示する。
        まとめた名前が ``_REPR_LIMIT`` 個を超える場合は先頭だけを表示し、件数を添える。

        Returns:
            str: ``CVs('curveShape.cv[0:7]')``、``Vertices('boxShape.vtx[0:2]', 'boxShape.vtx[5]')``、
                多数なら ``Vertices('boxShape.vtx[0]', ..., count=120)``、空なら
                ``Vertices('boxShape', count=0)``。無効なら ``<Vertices invalid>``。
        """
        cls = type(self).__name__
        if not self.isValid():
            return f"<{cls} invalid>"
        shape = self._shape.getName()
        if not self._indices:
            return f"{cls}({shape!r}, count=0)"
        prefix = f"{shape}.{self.component_class.component_type}"
        names = []
        start = previous = None
        for index in self._repr_indices():
            if previous is not None and index == previous + 1:
                previous = index
                continue
            if start is not None:
                names.append(self._range_name(prefix, start, previous))
            start = previous = index
        names.append(self._range_name(prefix, start, previous))
        if len(names) > _REPR_LIMIT:
            shown = ", ".join(repr(name) for name in names[:_REPR_LIMIT])
            return f"{cls}({shown}, ..., count={len(self._indices)})"
        return f"{cls}({', '.join(repr(name) for name in names)})"

    def __getitem__(self, index):
        """保持列のPythonの位置番号から単数参照、sliceから同型の部分コレクションを取得する。

        位置番号はMayaの実番号ではない。負数とboolはtupleと同じ位置として扱う。
        取得対象の現在番号を再検証し、元と同じShapeラッパーを共有する。

        Args:
            index (int | slice): 保持列内の位置。

        Returns:
            Component | Components: 新しい単数参照または同じ型の新しいコレクション。

        Raises:
            TypeError: tupleが受理しない番号、またはShape型が不正な場合。
            ValueError: sliceのstepが0の場合。
            IndexError: 保持列の位置または現在のMaya番号が範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        if isinstance(index, slice):
            return type(self)(self._shape, self._indices[index])
        return self.component_class(self._shape, self._indices[index])

    def __eq__(self, other):
        """同じシェイプ・同じ種類・同じ並びの番号か比較する。

        list・tupleとは、各位置の単数コンポーネントを ``==`` で比べる。

        Args:
            other (Components | list | tuple): 比較の相手。

        Returns:
            bool: 等しければTrue。対応しない型はNotImplemented。
        """
        if isinstance(other, Components):
            return (self.component_class.component_type == other.component_class.component_type
                    and self._shape == other._shape and self._indices == other._indices)
        if not isinstance(other, (list, tuple)):
            return NotImplemented
        if len(self._indices) != len(other):
            return False
        component_type = self.component_class.component_type
        return all(isinstance(item, Component) and item.component_type == component_type
                   and item._shape == self._shape and item._index == index
                   for item, index in zip(other, self._indices))

    def __getattr__(self, name):
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
        if name.startswith("_") or not callable(getattr(self.component_class, name, None)):
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

        def forward(*args, **kwargs):
            fast = kwargs.get("fast", False) is True
            with _edit_context(f"mlib{type(self).__name__}{name[:1].upper()}{name[1:]}", fast):
                return [getattr(component, name)(*args, **kwargs) for component in self]

        forward.__name__ = name
        forward.__qualname__ = f"{type(self).__name__}.{name}"
        forward.__doc__ = f"各要素の {name}() を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"
        return forward

    def __add__(self, other):
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
        if not isinstance(other, (Components, list, tuple)):
            return NotImplemented
        return type(self)(self._shape, self._indices + self._matching_indices(other))

    def __radd__(self, other):
        """左辺がlist・tupleの結合で、右辺と同じ型の新しいコレクションを返す。

        Args:
            other (list | tuple): 前へ結合する、同じシェイプ・同じ種類の単数コンポーネントの列。

        Returns:
            Components: 右辺(自身)と同じ具象型の新しいコレクション。

        Raises:
            TypeError: シェイプまたはコンポーネントの種類が異なる要素を含む場合。
        """
        if not isinstance(other, (list, tuple)):
            return NotImplemented
        return type(self)(self._shape, self._matching_indices(other) + self._indices)

    @property
    def shape(self):
        """保持している所有シェイプの参照を返す。

        Returns:
            Shape: 構築時と同じラッパー。コピーや有効性の再照会は行わない。
        """
        return self._shape

    @property
    def indices(self):
        """保持しているMaya実番号の不変tupleを返す。

        Returns:
            tuple[int, ...]: 初出順で重複を除いた保持値そのもの。新しいコピーは作らず、
                現在の番号範囲も再検証しない。カーブCVではOpenMayaの番号を保持する。
        """
        return self._indices

    def sort(self, key=None, reverse=False):
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
        _require_bool(reverse, "reverse")
        if key is not None and not callable(key):
            raise TypeError("key must be callable or None")
        if key is None:
            self._indices = tuple(sorted(self._indices, reverse=reverse))
            return self
        pairs = sorted(zip(self, self._indices), key=lambda pair: key(pair[0]), reverse=reverse)
        self._indices = tuple(index for _, index in pairs)
        return self

    def getFullNames(self):
        """保持順の完全コンポーネント名を取得する。

        全番号の再検証はまとめて1回だけ行う。

        Returns:
            list[str]: ``|cube|cubeShape.vtx[3]`` のような要素ごとの名前。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        prefix = self._name_prefix()
        return [f"{prefix}[{index}]" for index in self._indices]

    def getCompactNames(self):
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
        prefix = self._name_prefix()
        names = []
        start = previous = None
        for index in self._indices:
            if previous is not None and index == previous + 1:
                previous = index
                continue
            if start is not None:
                names.append(self._range_name(prefix, start, previous))
            start = previous = index
        if start is not None:
            names.append(self._range_name(prefix, start, previous))
        return names

    def isValid(self):
        """シェイプの生存・種類と、全保持番号の現在の範囲を照会する。

        Returns:
            bool: 全番号を参照できればTrue。空集合も生存する対応シェイプならTrue。

        Note:
            トポロジー変更前後で同じ要素を指す保証はない。
            UVは現在のUVセットの番号範囲を使う。
        """
        try:
            self._require_valid()
        except (RuntimeError, TypeError, ValueError, IndexError):
            return False
        return all(index >= 0 for index in self._indices)

    def isComplete(self):
        """シェイプが現在持つこの種類の要素を、すべて保持しているか照会する。

        保持順は問わない。``cmds.ls(..., flatten=True)`` で得る全要素(``vtx[*]`` 等)と同じ集まりかを調べる。

        Returns:
            bool: 全要素を保持していればTrue。要素が0個のシェイプで空の集まりもTrue。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        return len(self._indices) == self.component_class._element_count(self._shape)

    def _matching_indices(self, other):
        """結合する相手から、同じシェイプ・同じ種類であることを確かめた番号列を取り出す。

        Args:
            other (Components | list | tuple): 結合の相手。

        Returns:
            tuple[int, ...]: 相手の番号を保持順に並べた列。

        Raises:
            TypeError: シェイプまたはコンポーネントの種類が異なる場合。
        """
        name = type(self).__name__
        component_type = self.component_class.component_type
        if isinstance(other, Components):
            if other.component_class.component_type != component_type:
                raise TypeError(f"Cannot add {type(other).__name__} to {name}: different component type")
            if other._shape != self._shape:
                raise TypeError(f"Cannot add {type(other).__name__} to {name}: different shape")
            return other._indices
        indices = []
        for item in other:
            if not isinstance(item, Component) or item.component_type != component_type:
                raise TypeError(f"Cannot add {type(item).__name__} to {name}: "
                                f"expected {self.component_class.__name__} items")
            if item._shape != self._shape:
                raise TypeError(f"Cannot add {type(item).__name__} to {name}: different shape")
            indices.append(item._index)
        return tuple(indices)

    def _has_standard_component(self, component_class=None):
        """単数の構築・検査・番号取得が標準の具体型か判定する。

        Args:
            component_class (type | None): 明示した単数型。Noneなら自身の単数型。

        Returns:
            bool: 利用側の派生型や置換された単数処理でなければTrue。
        """
        # 具体コンポーネント型はこのモジュールを継承するため、循環を避けて使う時点で読み込む。
        from .cv import CV
        from .edge import Edge
        from .face import Face
        from .uv import UV
        from .vertex import Vertex
        component_class = self.component_class if component_class is None else component_class
        return (component_class in (Vertex, Edge, Face, UV, CV)
                and component_class.__init__ is _COMPONENT_INIT
                and component_class._require_valid is _COMPONENT_REQUIRE_VALID
                and component_class.index is _COMPONENT_INDEX
                and component_class.shape is _COMPONENT_SHAPE
                and component_class._validate_shape is _COMPONENT_VALIDATE_SHAPE
                and component_class._require_index_range is _COMPONENT_REQUIRE_INDEX_RANGE)

    def _has_standard_shape(self, component_class=None):
        """標準のシェイプ型か判定し、利用側の形状派生の照会処理を維持する。

        Args:
            component_class (type | None): 要素数を照会する単数型。Noneなら自身の型。

        Returns:
            bool: MeshまたはNurbsCurveそのものならTrue。
        """
        # nodes → components の循環importを避けるため、使う時点で読み込む。
        from ..nodes.mesh import Mesh
        from ..nodes.nurbsCurve import NurbsCurve
        shape_class = type(self._shape)
        if shape_class not in (Mesh, NurbsCurve):
            return False
        component_class = self.component_class if component_class is None else component_class
        name = _count_name(component_class)
        reader = getattr(self._shape, name, None)
        function = getattr(reader, "__func__", None)
        return (function is not None and function is getattr(shape_class, name, None)
                and function.__module__ == shape_class.__module__
                and function.__qualname__ == f"{shape_class.__name__}.{name}"
                and not hasattr(function, "__wrapped__"))

    def _uses_standard_iteration(self, component_class):
        """単数または反復が拡張されていない場合だけ一括照会を許可する。

        Args:
            component_class (type): 操作の標準単数型。

        Returns:
            bool: 単数・反復・シェイプが標準の実装ならTrue。
        """
        return (self.component_class is component_class
                and type(self).__iter__ is _COMPONENTS_ITER
                and self._has_standard_component() and self._has_standard_shape())

    def _uses_standard_vertices(self):
        """頂点の中間参照で呼ばれる構築・反復も標準処理か判定する。

        Returns:
            bool: Vertices/Vertexへの利用側の差替えを省略しなければTrue。
        """
        # vertexはこのモジュールを継承するため、循環を避けて使う時点で読み込む。
        from .vertex import Vertex, Vertices
        return (Vertices.component_class is Vertex and self._has_standard_component(Vertex)
                and self._has_standard_shape(Vertex)
                and Vertices.__init__ is _COMPONENTS_INIT
                and Vertices.__iter__ is _COMPONENTS_ITER)

    def _mesh_vertex_indices(self, count_name, vertices_method):
        """現在のメッシュから保持順に隣接頂点番号を集める。

        Args:
            count_name (str): MFnMeshのコンポーネント数プロパティ名。
            vertices_method (str): 要素の頂点番号を返すMFnMeshメソッド名。

        Returns:
            list[int]: 接続順を保った頂点番号。重複除去は呼出元のVerticesへ委ねる。
        """
        Component._validate_shape(self.shape, self.component_class.shape_type)
        indices = []
        if self._indices:
            mesh_fn = self.shape._geometry_fn()
            count = getattr(mesh_fn, count_name)
            for index in self._indices:
                Component._require_index_range(index, count)
                indices.extend(getattr(mesh_fn, vertices_method)(index))
        return indices

    def _name_prefix(self):
        """全番号をまとめて再検証し、``<シェイプの完全パス>.<種類>`` を返す。

        Returns:
            str: ``|cube|cubeShape.vtx`` のような接頭辞。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        return f"{self._shape.getFullName()}.{self.component_class.component_type}"

    def _repr_indices(self):
        """repr に表示する番号を保持順で返す。カーブCVはcmds用の番号へ写す。

        Returns:
            Sequence[int]: 表示用の番号列。
        """
        return self._indices

    def _require_valid(self):
        """シェイプと保持番号を一括検証し、名前や単数ラッパーは生成しない。

        Raises:
            TypeError: シェイプ型が異なる場合。
            IndexError: トポロジー変更により番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        component_class = self.component_class
        if not self._shape.isValid():
            raise RuntimeError("Component shape is invalid")
        if self._shape.getType() != component_class.shape_type:
            raise TypeError(f"Expected a {component_class.shape_type} shape")
        if self._indices:
            largest = max(self._indices)
            if largest >= component_class._element_count(self._shape):
                raise IndexError(f"Component index out of range: {largest}")

    @staticmethod
    def _range_name(prefix, start, end):
        """範囲指定のコンポーネント名を作る。

        Args:
            prefix (str): ``<シェイプの完全パス>.<種類>``。
            start (int): 先頭の番号。
            end (int): 末尾の番号(先頭と同じなら単体)。

        Returns:
            str: ``prefix[start]`` または ``prefix[start:end]``。
        """
        if start == end:
            return f"{prefix}[{start}]"
        return f"{prefix}[{start}:{end}]"

    def _get_coordinate(self, axis, **space):
        """保持順の指定軸の値を返す。axisは派生クラスが選択する。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            **space: 座標空間の指定。worldSpace=Trueでワールド空間。
        """
        return [point[axis] for point in self.getPosition(**space)]


_COMPONENTS_INIT = Components.__init__
_COMPONENTS_ITER = Components.__iter__


def _flat_input(cls, shape, items):
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
    result = []
    positions = []
    multis = []
    for item in items:
        if isinstance(item, (tuple, list)):
            if len(item) != cls.index_size:
                raise ValueError(f"{cls.__name__} index must have {cls.index_size} numbers, got {len(item)}")
            numbers = []
            for number in item:
                if isinstance(number, bool):
                    raise TypeError("Component index must be an integer, not bool")
                number = operator.index(number)
                if number < 0:
                    raise IndexError(f"Component index out of range: {tuple(item)}")
                numbers.append(number)
            positions.append(len(result))
            multis.append(tuple(numbers))
            result.append(None)
            continue
        if isinstance(item, bool):
            raise TypeError("Component index must be an integer, not bool")
        result.append(operator.index(item))
    if multis:
        for position, flat in zip(positions, cls._flat_indices(shape, multis)):
            result[position] = flat
    return result


def _component_name(prefix, numbers):
    """``<シェイプ>.<種類>`` と多次元の番号から ``cv[1][2]`` のようなコンポーネント名を作る。

    Args:
        prefix (str): ``<シェイプの名前>.<種類>``。
        numbers (Sequence[int]): cmds用の番号。

    Returns:
        str: コンポーネント名。
    """
    return prefix + "".join(f"[{number}]" for number in numbers)


class _MultiIndexComponent:
    """複数の番号(``cv[u][v]``・``pt[s][t][u]``・``vtxFace[v][f]``)を持つ単数コンポーネントの共通処理。

    :class:`Component` の具体型と組み合わせる(``class SurfaceCV(_MultiIndexComponent, PointComponent)``)。
    保持する :attr:`~Component.index` は、要素を一列に並べた平坦な実番号で、``==``・ハッシュ・
    :attr:`Components.indices` はこの番号を使う。多次元の番号は :meth:`getMultiIndex` で照会する。
    具体型は ``index_size`` と、``_element_count``・``_multi_indices``・``_flat_indices`` を定義する。
    """

    #: 多次元の番号の数。具体型が定義する。
    index_size = 0

    if TYPE_CHECKING:
        _shape: "Shape"
        _index: int
        shape_type: Optional[str]
        component_type: Optional[str]
        _validate_shape: Callable[..., None]
        _require_valid: Callable[[], None]
        _multi_indices: Callable[..., List[Tuple[int, ...]]]
        _flat_indices: Callable[..., List[int]]

    def __init__(self, shape, index):
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
        self._shape = shape
        self._validate_shape(shape, self.shape_type)
        self._index = _flat_input(type(self), shape, [index])[0]
        self._require_valid()

    def getFullName(self):
        """現在のDAGパスと多次元の番号を使ってコンポーネント名を取得する。

        Returns:
            str: ``|plane|planeShape.cv[1][2]`` のような名前。周期曲面の重複CVは先頭の対応番号で表す。
        """
        self._require_valid()
        numbers = self._multi_indices(self._shape, [self._index], command=True)[0]
        return _component_name(f"{self._shape.getFullName()}.{self.component_type}", numbers)

    def getMultiIndex(self):
        """保持する要素の多次元の番号を、現在の形状から照会する。

        Returns:
            tuple[int, ...]: ``(u, v)``・``(s, t, u)``・``(頂点, フェース)`` のような番号。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        return self._multi_indices(self._shape, [self._index])[0]


class _MultiIndexComponents:
    """複数の番号を持つコンポーネントの集まりの共通処理。

    :class:`Components` の具体型と組み合わせる。番号の指定には平坦な実番号と多次元の番号を混ぜられ、
    保持は平坦な実番号で行う。名前は範囲へまとめない。
    """

    if TYPE_CHECKING:
        _shape: "Shape"
        _indices: Tuple[int, ...]
        component_class: Any
        isValid: Callable[[], bool]
        _require_valid: Callable[[], None]

    def __init__(self, shape, indices=None):
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
        self._shape = shape
        component_class = self.component_class
        Component._validate_shape(shape, component_class.shape_type)
        count = component_class._element_count(shape)
        if indices is None:
            self._indices = tuple(range(count))
            return
        if isinstance(indices, (str, bytes)):
            raise TypeError("indices must be an iterable of component indices")
        flats = _flat_input(component_class, shape, list(indices))
        for index in flats:
            Component._require_index_range(index, count)
        self._indices = tuple(dict.fromkeys(flats))

    def __repr__(self):
        """デバッグ用に、型名と先頭の要素の名前を返す。

        Returns:
            str: ``SurfaceCVs('planeShape.cv[0][0]', 'planeShape.cv[0][1]')``、多数なら件数を添える。
                空なら ``SurfaceCVs('planeShape', count=0)``、無効なら ``<SurfaceCVs invalid>``。
        """
        cls = type(self).__name__
        if not self.isValid():
            return f"<{cls} invalid>"
        shape = self._shape.getName()
        if not self._indices:
            return f"{cls}({shape!r}, count=0)"
        prefix = f"{shape}.{self.component_class.component_type}"
        shown = self.component_class._multi_indices(self._shape, self._indices[:_REPR_LIMIT], command=True)
        text = ", ".join(repr(_component_name(prefix, numbers)) for numbers in shown)
        if len(self._indices) > _REPR_LIMIT:
            return f"{cls}({text}, ..., count={len(self._indices)})"
        return f"{cls}({text})"

    def getFullNames(self):
        """保持順の完全コンポーネント名を取得する。

        Returns:
            list[str]: ``|plane|planeShape.cv[1][2]`` のような要素ごとの名前。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        prefix = f"{self._shape.getFullName()}.{self.component_class.component_type}"
        return [_component_name(prefix, numbers)
                for numbers in self.component_class._multi_indices(self._shape, self._indices, command=True)]

    def getCompactNames(self):
        """cmds用の名前を返す。多次元の番号は範囲へまとめず、:meth:`getFullNames` と同じ名前を返す。

        Returns:
            list[str]: 保持順のコンポーネント名。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: いずれかの番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        return self.getFullNames()
