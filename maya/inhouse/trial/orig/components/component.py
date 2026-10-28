"""Mayaのコンポーネント（頂点・エッジ・フェース・CV・UV）と同一シェイプの要素群。"""

import math
import operator

from ..core.object import Object


class Component(Object):
    """シェイプ参照と実番号を保持し、一つのMayaコンポーネントを表す。

    頂点・エッジ・フェース・UV・カーブCVの共通基底。Vertex等の具体型を使う。
    渡されたShapeラッパーを共有し、形状や座標のコピーは保持しない。
    番号は作成時に検証するが、トポロジー変更後も同じ要素を指し続ける保証はない。
    UVの番号範囲は現在のUVセットに従う。
    """

    shape_type = None
    component_type = None
    count_attribute = None

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
        self._validate()

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
        self._validate()
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
            self._validate()
        except (RuntimeError, TypeError, ValueError, IndexError):
            return False
        return True

    @staticmethod
    def _from_api(path, component):
        """OpenMayaの単一インデックス型コンポーネントを、要素別の参照へ展開する。

        明示番号はgetElements()の順序、complete指定は現在のShapeの全番号を使う。
        各参照は同じShapeラッパーを共有し、座標値は取得しない。

        Args:
            path (MDagPath): 所有Shapeのインスタンスパス。
            component (MObject): Meshの頂点/エッジ/フェース/UV、またはNurbsCurveのCV。
                NurbsSurfaceやLattice等の多次元コンポーネントは対象外。

        Returns:
            list[Component]: 新しい単数ラッパーのリスト。complete指定は0から要素数-1の順。

        Raises:
            TypeError: 非対応のコンポーネント種類、または対応しないShape型の場合。
            IndexError: 明示番号が現在のShapeの範囲外の場合。
            RuntimeError: 所有Shapeを解決・参照できない場合。
        """
        import maya.api.OpenMaya as om2
        from ..nodes.node import Node
        from .vertex import Vertex
        from .edge import Edge
        from .face import Face
        from .uv import UV
        from .cv import CV
        types = {
            om2.MFn.kMeshVertComponent: Vertex,
            om2.MFn.kMeshEdgeComponent: Edge,
            om2.MFn.kMeshPolygonComponent: Face,
            om2.MFn.kMeshMapComponent: UV,
            om2.MFn.kCurveCVComponent: CV,
        }
        cls = types.get(component.apiType())
        if cls is None:
            raise TypeError("Only mesh vertices/edges/faces/UVs and curve CVs are supported")
        shape = Node(path)
        fn = om2.MFnSingleIndexedComponent(component)
        if fn.isComplete:
            indices = range(getattr(shape, cls.count_attribute)())
        else:
            indices = fn.getElements()
        return [cls(shape, index) for index in indices]

    @staticmethod
    def _resolve_input(value):
        """コンポーネント名・既存参照・APIの組から、一つの要素参照を解決する。

        既存Componentは再検証せず同じラッパーを返す。文字列はMSelectionListで解決し、
        API入力は単一インデックス型かと要素数を確認してから展開する。
        単数でないと判定した入力は、展開前に拒否する。展開後も一件であることを確認する。

        Args:
            value (str | Component | tuple): コンポーネント名、既存参照、または
                (MDagPath, MObject)。頂点/エッジ/フェース/UV/カーブCVを対象とする。

        Returns:
            Component: 具体型の参照。既存入力以外は新しいラッパー。

        Raises:
            TypeError: 入力型またはコンポーネント種類が非対応の場合。
            ValueError: 空文字、または解決対象が単一要素でない場合。
            IndexError: 明示番号が現在のShapeの範囲外の場合。
            RuntimeError: 名前や所有Shapeを解決できない場合。
        """
        import maya.api.OpenMaya as om2
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
        if not value[1].hasFn(om2.MFn.kSingleIndexedComponent):
            raise TypeError("Expected a single-indexed component")
        component_fn = om2.MFnSingleIndexedComponent(value[1])
        if component_fn.isComplete:
            count = component_fn.getCompleteData()
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
            **space: 座標空間の指定。ws=Trueでワールド空間。
        """
        return self.getPosition(**space)[axis]

    def _set_coordinate(self, axis, value, *, fast=False, **space):
        """指定軸だけを置換し、派生クラスの座標更新へ委譲する。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            value: 指定軸へ設定する座標値。
            fast (bool): 座標更新へ渡す直接編集の指定。
            **space: 座標空間の指定。ws=Trueでワールド空間。
        """
        position = list(self.getPosition(**space))
        position[axis] = value
        return self.setPosition(position, fast=fast, **space)

    def _validate(self):
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
            self._validate_index(self._index, 0)
        self._validate_index(self._index, getattr(self._shape, self.count_attribute)())

    @staticmethod
    def _validate_shape(shape, shape_type):
        """生存と型を検査する。要素数は呼出し側で必要な時に照会する。

        Args:
            shape (Shape): 検査する参照。
            shape_type (str): 必要なMayaシェイプ型。

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
    def _validate_index(index, count):
        """正規化済みの実番号を、呼出し内で照会した要素数と比較する。

        Args:
            index (int): コンポーネントの実番号。
            count (int): 現在の要素数。

        Raises:
            IndexError: 番号が範囲外の場合。
        """
        if not 0 <= index < count:
            raise IndexError(f"Component index out of range: {index}")

    @staticmethod
    def _finite_coordinates(value, size):
        """有限な座標列に変換する。

        Args:
            value (Iterable[float]): 入力座標。
            size (int): 必要な成分数。

        Returns:
            tuple[float, ...]: 検証済み座標。

        Raises:
            ValueError: 成分数や数値が不正な場合。
        """
        try:
            result = tuple(float(item) for item in value)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid coordinates") from error
        if len(result) != size or not all(math.isfinite(item) for item in result):
            raise ValueError(f"Expected {size} finite coordinates")
        return result


# 利用側が標準単数処理を置換した場合は、その処理を一括経路から省略しない。
_COMPONENT_INIT = Component.__init__
_COMPONENT_VALIDATE = Component._validate
_COMPONENT_INDEX = Component.index
_COMPONENT_SHAPE = Component.shape
_COMPONENT_VALIDATE_SHAPE = Component._validate_shape
_COMPONENT_VALIDATE_INDEX = Component._validate_index


class Components:
    """同一シェイプ・同じ種類の実番号を、初出順の重複なしtupleで保持する。

    Vertices等の具体型が、単数参照の列挙と一括操作を担当する。
    Shapeラッパーを共有し、番号列は作成時に固定する。形状編集後の要素追加や削除には
    自動追従せず、トポロジー変更後の要素の同一性も保証しない。
    角括弧は保持列内の位置で、Mayaの実番号ではない。
    """

    component_class = Component

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
        selected = range(getattr(shape, self.component_class.count_attribute)()) if indices is None else indices
        # 一般の反復入力や独自__index__は従来どおり一件ずつ構築する。
        # これにより入力の副作用・途中例外・利用側constructor/_validateを維持する。
        if (self._has_standard_component() and self._has_standard_shape()
                and (type(selected) is range or (type(selected) in (list, tuple)
                     and all(type(index) is int for index in selected)))):
            count = len(selected) if indices is None else None
            for index in selected:
                if index < 0:
                    Component._validate_index(index, 0)
                if count is None:
                    count = getattr(shape, self.component_class.count_attribute)()
                Component._validate_index(index, count)
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

    def __getitem__(self, index):
        """保持列のPython添字から単数参照、sliceから同型の部分コレクションを取得する。

        添字はMayaの実番号ではない。負数とboolはtupleと同じ位置として扱う。
        取得対象の現在番号を再検証し、元と同じShapeラッパーを共有する。

        Args:
            index (int | slice): 保持列内の位置。

        Returns:
            Component | Components: 新しい単数参照または同じ型の新しいコレクション。

        Raises:
            TypeError: tupleが受理しない添字、またはShape型が不正な場合。
            IndexError: 保持列の位置または現在のMaya番号が範囲外の場合。
            ValueError: sliceのstepが0の場合。
            RuntimeError: Shapeが無効な場合。
        """
        if isinstance(index, slice):
            return type(self)(self._shape, self._indices[index])
        return self.component_class(self._shape, self._indices[index])

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
            self._validate()
        except (RuntimeError, TypeError, ValueError, IndexError):
            return False
        return all(index >= 0 for index in self._indices)

    def _has_standard_component(self, component_class=None):
        """単数の構築・検査・番号取得が標準の具体型か判定する。

        Args:
            component_class (type | None): 明示した単数型。Noneなら自身の単数型。

        Returns:
            bool: 利用側の派生型や置換された単数処理でなければTrue。
        """
        from .cv import CV
        from .edge import Edge
        from .face import Face
        from .uv import UV
        from .vertex import Vertex
        component_class = self.component_class if component_class is None else component_class
        return (component_class in (Vertex, Edge, Face, UV, CV)
                and component_class.__init__ is _COMPONENT_INIT
                and component_class._validate is _COMPONENT_VALIDATE
                and component_class.index is _COMPONENT_INDEX
                and component_class.shape is _COMPONENT_SHAPE
                and component_class._validate_shape is _COMPONENT_VALIDATE_SHAPE
                and component_class._validate_index is _COMPONENT_VALIDATE_INDEX)

    def _has_standard_shape(self, component_class=None):
        """標準のシェイプ型か判定し、利用側の形状派生の照会処理を維持する。

        Args:
            component_class (type | None): 要素数を照会する単数型。Noneなら自身の型。

        Returns:
            bool: MeshまたはNurbsCurveそのものならTrue。
        """
        from ..nodes.mesh import Mesh
        from ..nodes.nurbsCurve import NurbsCurve
        shape_class = type(self._shape)
        if shape_class not in (Mesh, NurbsCurve):
            return False
        component_class = self.component_class if component_class is None else component_class
        name = component_class.count_attribute
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
                Component._validate_index(index, count)
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
        self._validate()
        return f"{self._shape.getFullName()}.{self.component_class.component_type}"

    def _validate(self):
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
            if largest >= getattr(self._shape, component_class.count_attribute)():
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

    def _coordinate_rows(self, values, size):
        """要素別座標を全件検証する。個数・座標不正はValueError。

        Args:
            values (Iterable[Iterable[float]]): 保持順の座標列。
            size (int): 1座標の成分数。

        Returns:
            list[tuple[float, ...]]: 検証済みの座標列。

        Raises:
            ValueError: 座標が不正、または values の件数が保持している要素数と一致しない場合。
        """
        rows = [Component._finite_coordinates(value, size) for value in values]
        if len(rows) != len(self):
            raise ValueError("Coordinate count must match component count")
        return rows

    def _get_coordinate(self, axis, **space):
        """保持順の指定軸の値を返す。axisは派生クラスが選択する。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            **space: 座標空間の指定。ws=Trueでワールド空間。
        """
        return [point[axis] for point in self.getPosition(**space)]

    def _set_coordinate(self, axis, value, *, fast=False, **space):
        """全要素の指定軸を置換し、座標列の検証・更新へ委譲する。

        Args:
            axis: 座標成分の番号。0=X、1=Y、2=Z。
            value: 指定軸へ設定する座標値。
            fast (bool): 座標更新へ渡す直接編集の指定。
            **space: 座標空間の指定。ws=Trueでワールド空間。
        """
        return self.setPositions(self._axis_rows(self.getPosition(**space), axis, value), fast=fast, **space)

    def _axis_rows(self, positions, axis, value):
        """軸の一括設定用座標を作る。スカラーは全要素、列は保持順に対応する。

        Args:
            positions (Iterable[Iterable[float]]): 現在座標。
            axis (int): 成分番号。
            value (float | Iterable[float]): 軸の値。

        Returns:
            list[list[float]]: 更新後の座標列。シーンは変更しない。

        Raises:
            ValueError: value を反復した要素数が保持している要素数と一致しない場合。
        """
        try:
            values = list(value)
        except TypeError:
            values = [value] * len(self)
        if len(values) != len(self):
            raise ValueError("Axis value count must match component count")
        rows = [list(position) for position in positions]
        for row, item in zip(rows, values):
            row[axis] = item
        return rows


_COMPONENTS_INIT = Components.__init__
_COMPONENTS_ITER = Components.__iter__
