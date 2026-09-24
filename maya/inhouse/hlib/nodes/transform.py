"""変換行列を介して Transform ノードを操作する。"""

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk
from .._core.registry import node_wrapper
from ..maths import Matrix, Translate, Vector
from .node import Node


@node_wrapper("transform")
class Transform(Node):
    """Maya transform ノードを matrix-first API で扱うラッパー。

    評価済み値を取得する ``get_*`` 系メソッドは cymel の ``getMatrix(ws=...)`` に
    倣い、``ws=False`` （既定）でローカル空間、``ws=True`` でワールド空間の値を返す。
    """

    @undo_chunk("hlibTransformAddConstraint")
    def add_constraint(self, sources, type="parent", maintainOffset=False):
        """自身を拘束するコンストレイントを作成する。

        Args:
            sources (Node | str | Iterable[Node | str]): 拘束元の単一ノードまたはノード列。
            type (str): parent、point、orient、scale、aim、poleVector、
                geometry、normal、tangent、pointOnPoly。または Constraint 接尾辞付きの型名。
            maintainOffset (bool): True の場合は現在の相対位置・回転を維持する。
                False の場合は Maya の既定動作で拘束する。

        Returns:
            Constraint: 対応する具象ラッパー。同じ種類が既存なら Maya の規則で
                ターゲットが追加される場合がある。

        Raises:
            ValueError: 未対応の型または空のソースの場合。
            TypeError: 型名やターゲットの入力型が不正な場合。
            RuntimeError: ノードが無効、または Maya が作成を拒否した場合。

        PoleVector は RP IK ハンドル、Geometry/Normal/PointOnPoly は適切な形状、
        Tangent は NURBS カーブが必要。選択状態による対象補完は行わない。
        """
        from .constraint import Constraint

        if not isinstance(type, str):
            raise TypeError("type must be a string")
        command_name = type if type.endswith("Constraint") else type + "Constraint"
        # 型登録を重複管理せず、登録メタデータを持つ具象クラスから対象を判定する。
        supported = {
            cls.__dict__["__hlib_node_type__"]
            for cls in Constraint.__subclasses__()
            if "__hlib_node_type__" in cls.__dict__
        }
        if command_name not in supported:
            raise ValueError(f"Unsupported constraint type: {type}")
        if not self.is_valid():
            raise RuntimeError("Cannot constrain an invalid transform")
        if isinstance(sources, (Node, str)):
            sources = [sources]
        names = []
        for source in sources:
            if isinstance(source, Node):
                if not source.is_valid():
                    raise RuntimeError("Constraint target is invalid")
                source = source.full_name
            if not isinstance(source, str) or not source:
                raise TypeError("Constraint sources must be non-empty names or Node objects")
            names.append(source)
        if not names:
            raise ValueError("At least one constraint source is required")
        command_kwargs = {}
        if command_name in {
            "parentConstraint",
            "pointConstraint",
            "orientConstraint",
            "scaleConstraint",
            "aimConstraint",
        }:
            command_kwargs["maintainOffset"] = maintainOffset
        result = getattr(cmds, command_name)(*names, self.full_name, **command_kwargs)
        return Node(result[0])

    def dag_path(self):
        """Transform の MDagPath を取得する。

        Returns:
            om2.MDagPath | None: 有効な DAG パス。取得できない場合は ``None``。
        """
        if self._dag_path is None and self.is_valid():
            self._dag_path = om2.MFnDagNode(self.mobject()).getPath()
        return self._dag_path

    def dag_node(self):
        """Transform 用の MFnDagNode を取得する。

        Returns:
            om2.MFnDagNode: この Transform の function set。
        """
        return om2.MFnDagNode(self.dag_path())

    def transform_fn(self):
        """Transform 用の MFnTransform を取得する。

        Returns:
            om2.MFnTransform: この Transform の function set。
        """
        return om2.MFnTransform(self.dag_path())

    def pivot(self, ws=False):
        """回転ピボットを取得する。

        スケールピボットは set_pivot() で常に同じ位置に揃えて設定するため、
        別途取得するメソッドは提供しない。

        Args:
            ws (bool): True はワールド空間、False はオブジェクト空間(ローカル)。

        Returns:
            Translate: ピボット位置。Maya API の内部距離単位。
        """
        space = om2.MSpace.kWorld if ws else om2.MSpace.kTransform
        point = self.transform_fn().rotatePivot(space)
        return Translate(point.x, point.y, point.z)

    @undo_chunk("hlibTransformSetPivot")
    def set_pivot(self, value, ws=False):
        """回転ピボットとスケールピボットを同じ位置にまとめて設定する。

        Args:
            value (Iterable[float]): 新しいピボット位置。Maya API の内部距離単位。
            ws (bool): True はワールド空間、False はオブジェクト空間(ローカル)。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効、または Maya が設定を拒否した場合。
        """
        point = om2.MPoint(*value)
        coordinates = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in (point.x, point.y, point.z)]
        cmds.xform(self.full_name, pivots=coordinates, worldSpace=ws, objectSpace=not ws, preserve=False)
        return self

    @undo_chunk("hlibTransformCenterPivot")
    def center_pivot(self):
        """Maya標準のバウンディングボックス中心へ両ピボットを移動する。

        xformのcenterPivotsと同じ対象範囲を使用する。preserve=Trueで
        オブジェクトの変換結果を維持し、回転・スケールピボットを変更する。
        コンポーネントの選択状態は使用しない。

        Returns:
            Transform: 自身。一回のUndoで戻せる。

        Raises:
            RuntimeError: 無効なノードやロックなどでMayaが変更を拒否した場合。
        """
        cmds.xform(self.full_name, centerPivots=True, preserve=True)
        return self

    def bounding_box(self, ws=False):
        """直下の Shape 階層を含むバウンディングボックスを取得する。

        MFnDagNode.boundingBox は自身の translate/rotate/scale は含むが、
        親から継承した変換は含まない（``cmds.xform(-boundingBox)`` と同じ）。
        ``ws=True`` はそこへ親のワールド行列をさらに適用し、真のワールド空間の
        バウンディングボックスを返す。

        Args:
            ws (bool): True はワールド空間、False は自身の変換のみを含む空間
                （親の変換は含まない）。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い場合は原点のみを含む空に近いボックスになる。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot compute the bounding box of an invalid transform")
        box = self.dag_node().boundingBox
        if not ws:
            return box
        parent_matrix = self._parent_world_matrix()
        world_box = om2.MBoundingBox()
        for x in (box.min.x, box.max.x):
            for y in (box.min.y, box.max.y):
                for z in (box.min.z, box.max.z):
                    corner = parent_matrix.transform_point((x, y, z))
                    world_box.expand(om2.MPoint(corner.x, corner.y, corner.z))
        return world_box

    def parent_path(self):
        """親ノードの DAG パスを取得する。

        Returns:
            om2.MDagPath | None: 親のパス。親がない場合は ``None``。
        """
        if not self.is_valid() or self.dag_path().length() <= 1:
            return None
        parent_path = om2.MDagPath(self.dag_path())
        parent_path.pop()
        return parent_path

    def parent_node(self):
        """親ノードを汎用 Node として取得する。

        Returns:
            Node | None: 親ノード。親がない場合は ``None``。
        """
        parent_path = self.parent_path()
        return Node(parent_path) if parent_path is not None else None

    def root(self):
        """DAG 階層の最上位祖先を取得する。

        DAG 上の親は常に Transform であるため、祖先も常に Transform になる。

        Returns:
            Transform: ワールド直下の祖先ノード。自身がワールド直下ならその自身を返す。
        """
        node = self
        parent = node.parent_node()
        while parent is not None:
            node = parent
            parent = node.parent_node()
        return node

    def child_nodes(self):
        """直接の子ノードを汎用 Node のリストとして取得する。

        Returns:
            list[Node]: 直接の子ノード。
        """
        if not self.is_valid():
            return []
        dag_path = self.dag_path()
        dag_fn = self.dag_node()
        children = []
        for index in range(dag_fn.childCount()):
            child_path = om2.MDagPath(dag_path)
            child_path.push(dag_fn.child(index))
            children.append(Node(child_path))
        return children

    def child_transforms(self):
        """直接の子 Transform のみを取得する（Shape 子は含まない）。

        Returns:
            list[Transform]: 直接の子 Transform。
        """
        return [child for child in self.child_nodes() if isinstance(child, Transform)]

    def leaves(self):
        """Transform 階層下の葉ノード（子 Transform を持たないもの）をすべて取得する。

        Shape の有無は判定に関与しない。

        Returns:
            list[Transform]: 葉ノードのリスト。子 Transform が無い場合は自身のみを含む。
        """
        children = self.child_transforms()
        if not children:
            return [self]
        result = []
        for child in children:
            result.extend(child.leaves())
        return result

    def siblings(self):
        """親を同じくする兄弟 Transform を取得する（自身は含まない）。

        自身がワールド直下の場合は、他のワールド直下 Transform を対象にする。

        Returns:
            list[Transform]: 兄弟 Transform のリスト。
        """
        if not self.is_valid():
            return []
        parent = self.parent_node()
        if parent is not None:
            candidates = parent.child_transforms()
        else:
            candidates = self._world_assemblies()
        self_uuid = self.uuid
        return [
            candidate for candidate in candidates
            if isinstance(candidate, Transform) and candidate.uuid != self_uuid
        ]

    @staticmethod
    def _world_assemblies():
        """ワールド直下の Transform をすべて取得する。

        Returns:
            list[Node]: ワールド直下(DAGパスの長さが1)の Transform ラッパー。
        """
        iterator = om2.MItDag(om2.MItDag.kBreadthFirst, om2.MFn.kTransform)
        assemblies = []
        while not iterator.isDone():
            path = iterator.getPath()
            if path.length() == 1:
                assemblies.append(Node(path))
            iterator.next()
        return assemblies

    def shapes(self, intermediates=False):
        """このTransform直下のShapeを取得する。

        Args:
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            list[Shape]: 条件に一致するShapeのリスト。
        """
        from .shape import Shape

        if not self.is_valid():
            return []
        shapes = []
        dag_path = self.dag_path()
        dag_fn = self.dag_node()
        for index in range(dag_fn.childCount()):
            child = dag_fn.child(index)
            if not child.hasFn(om2.MFn.kShape):
                continue
            child_fn = om2.MFnDagNode(child)
            if not intermediates and child_fn.isIntermediateObject:
                continue
            child_path = om2.MDagPath(dag_path)
            child_path.push(child)
            shapes.append(Shape(child_path))
        return shapes

    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0), indices=None):
        """直下のすべてのShapeのジオメトリをミラーする。

        直下の各Shape（Mesh、NurbsCurveなど mirror を実装するもの）へ同じ引数で
        処理を委譲する。indices は Shape ごとの要素番号（Mesh は頂点、NurbsCurve は
        CV）として解釈される。Transform自身の行列やShapeの構造は変更しない。

        Args:
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            ws (bool): True はワールド軸、False はオブジェクト空間の軸。既定は False。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は Maya の現在の距離単位。Transform のピボットとは独立する。
            indices (Iterable[int] | None): 各Shapeへそのまま渡す要素番号。
                None は全要素、空列は変更なし。

        Returns:
            Transform: 編集した自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換が数値的にほぼ特異な場合。
            TypeError: 要素番号が整数でない場合、または直下のShapeが mirror を実装しない場合。
            IndexError: 要素番号が範囲外の場合。
            RuntimeError: Maya が形状の取得・編集を拒否した場合。

        複数のShapeを持つ場合、途中のShapeで失敗すると以降のShapeは処理されない
        （それまでに成功した分はロールバックしない）。
        """
        for shape in self.shapes():
            shape.mirror(axis=axis, ws=ws, pivot=pivot, indices=indices)
        return self

    def shape(self, index=0, intermediates=False):
        """指定位置のShapeを取得する。

        Args:
            index (int): Shapeのインデックス。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            Shape: 指定位置のShape。

        Raises:
            IndexError: 指定したインデックスにShapeがない場合。
        """
        shapes = self.shapes(intermediates=intermediates)
        try:
            return shapes[index]
        except IndexError as original_error:
            raise IndexError(f"Shape index out of range: {index}") from original_error

    def transform(self):
        """Transform自身を返す。

        Returns:
            Transform: 自身。
        """
        return self

    @undo_chunk("hlibTransformSetParent")
    def set_parent(self, parent=None, relative=False, add=False):
        """Transformの親を変更する。

        Args:
            parent (Node | str | None): 新しい親。None はワールド直下。
            relative (bool): True は親変更前のローカル変換を保持する。False は Maya の既定動作。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。

        Returns:
            Transform: 自身。
        """
        if parent is None:
            cmds.parent(self.name(), world=True, relative=relative)
        else:
            parent_name = parent.name() if isinstance(parent, Node) else parent
            cmds.parent(self.name(), parent_name, relative=relative, add=add)
        return self

    @undo_chunk("hlibTransformMatch")
    def match_transform(self, target, position=True, rotation=True, scale=True, pivots=False):
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

        Args:
            target (Transform | str): 合わせ先のTransformまたはjoint。
            position (bool): 位置を合わせる。
            rotation (bool): 回転を合わせる。
            scale (bool): スケールを合わせる。
            pivots (bool): 回転・スケールピボットも合わせる。

        Returns:
            Transform: 自身。全フラグFalseなら何も変更しない。

        Raises:
            TypeError: targetがTransformではない場合。
            RuntimeError: ノードが無効、またはMayaが変更を拒否した場合。

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用する。
        shearの一致や行列全体のコピーは保証しない。
        """
        from .._core.coerce import to_node

        target = to_node(target)
        if not isinstance(target, Transform):
            raise TypeError("Target must be a transform or joint")
        if any((position, rotation, scale, pivots)):
            cmds.matchTransform(self.full_name, target.full_name, position=position,
                                rotation=rotation, scale=scale, pivots=pivots)
        return self

    def get_matrix(self, ws=False):
        """変換行列を取得する。

        Maya が評価・キャッシュ済みの ``matrix`` / ``worldMatrix`` 属性値をそのまま
        使うため、``jnt.plug("matrix")`` / ``jnt.plug("worldMatrix")`` と常に一致する。

        Args:
            ws (bool): ``True`` でワールド空間（``worldMatrix``）、``False`` （既定）で
                ローカル空間（``matrix``）の値を取得する。

        Returns:
            Matrix: 指定空間の評価済み行列。ノードが無効な場合は単位行列。
        """
        if not self.is_valid():
            return Matrix()
        if ws:
            return self.plug("worldMatrix").element(0, create=True).get()
        return self.plug("matrix").get()

    def get_translate(self, ws=False):
        """Translate を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Translate: 評価済みの位置。
        """
        return self.get_matrix(ws=ws).translate

    def get_rotate(self, ws=False):
        """Euler 回転値を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian）。
        """
        return self.get_matrix(ws=ws).rotation

    def get_scale(self, ws=False):
        """Scale を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Scale: 評価済みのスケール値。
        """
        return self.get_matrix(ws=ws).scale

    def get_shear(self, ws=False):
        """Shear を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Shear: 評価済みの shear 値。
        """
        return self.get_matrix(ws=ws).shear

    def get_quaternion(self, ws=False):
        """Quaternion を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Quaternion: 評価済みの回転値。
        """
        return self.get_matrix(ws=ws).quaternion

    def get_euler(self, ws=False):
        """EulerRotation を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian）。
        """
        return self.get_matrix(ws=ws).euler

    def decompose(self, ws=True):
        """指定空間の変換行列を取得する互換メソッド。

        Args:
            ws (bool): ``True`` （既定）でワールド空間、``False`` でローカル空間の値を取得する。

        Returns:
            Matrix: get_matrix(ws=ws) の結果。成分辞書は返さない。
        """
        return self.get_matrix(ws=ws)

    def _parent_world_matrix(self):
        """親Transformのワールド行列を取得する。

        Returns:
            Matrix: 親のワールド行列。親がない、または親に get_matrix がなければ単位行列。
        """
        parent = self.parent_node()
        if parent is None or not hasattr(parent, "get_matrix"):
            return Matrix()
        return parent.get_matrix(ws=True)

    def _apply_local_matrix(self, matrix):
        """ローカル行列の各成分をMaya属性へ適用する。

        平行移動・XYZ のオイラー回転・スケール・シアーを順に書き込む。回転はラジアンから度へ変換するため、Maya の角度単位が度であることを前提とする。ピボットや rotateAxis の補正は行わない。

        Args:
            matrix (Matrix): ローカル空間の変換行列。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 行列を分解できない場合。
            RuntimeError: Maya が属性の書き込みを拒否した場合。
        """
        name = self.full_name
        cmds.setAttr(f"{name}.translate", *matrix.translate)
        cmds.setAttr(f"{name}.rotate", *(math.degrees(component) for component in matrix.euler))
        cmds.setAttr(f"{name}.scale", *matrix.scale)
        cmds.setAttr(f"{name}.shear", *matrix.shear)

    @undo_chunk("hlibTransformSetMatrix")
    def set_matrix(self, matrix, ws=False):
        """行列をローカルまたはワールド空間で設定する。

        Args:
            matrix (Matrix | sequence): 適用する変換行列。
            ws (bool): ``True`` でワールド空間、``False`` でローカル空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なノード、または Maya が属性設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。
        """
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        if not self.is_valid():
            raise RuntimeError("Cannot set an invalid transform")
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix)
        return self

    @undo_chunk("hlibTransformSetTranslate")
    def set_translate(self, value, ws=False):
        """平行移動をローカルまたはワールド空間で設定する。

        Args:
            value (Translate | sequence): 新しい平行移動値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。
        """
        matrix = self.get_matrix(ws=ws)
        matrix.translate = value
        return self.set_matrix(matrix, ws=ws)

    @undo_chunk("hlibTransformSetRotate")
    def set_rotate(self, value, unit="rad", ws=False):
        """Euler回転を設定する。

        Args:
            value (Iterable[float] | Quaternion): XYZ 回転値。unit が rad の場合は Quaternion も受け入れる。EulerRotation の order は引き継がない。
            unit (str): rad はラジアン、deg は度の3成分。既定は rad。
            ws (bool): True はワールド、False はローカル空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: unit が rad/deg 以外、行列が分解不能、または必要な親行列が反転不能の場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。
        """
        if unit not in ("rad", "deg"):
            raise ValueError("unit must be 'rad' or 'deg'")
        if unit == "deg":
            value = tuple(math.radians(component) for component in value)
        matrix = self.get_matrix(ws=ws)
        matrix.rotation = value
        return self.set_matrix(matrix, ws=ws)

    @undo_chunk("hlibTransformSetScale")
    def set_scale(self, value, ws=False):
        """スケールをローカルまたはワールド空間で設定する。

        Args:
            value (Scale | sequence): 新しいスケール値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。
        """
        matrix = self.get_matrix(ws=ws)
        matrix.scale = value
        return self.set_matrix(matrix, ws=ws)

    @undo_chunk("hlibTransformSetShear")
    def set_shear(self, value, ws=False):
        """Shearをローカルまたはワールド空間で設定する。

        Args:
            value (Shear | sequence): 新しいShear値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。
        """
        matrix = self.get_matrix(ws=ws)
        matrix.shear = value
        return self.set_matrix(matrix, ws=ws)

    @undo_chunk("hlibTransformCompose")
    def compose(self, matrix, ws=False):
        """Matrix の TRS/shear 成分をローカルまたはワールド空間へ適用する。

        Args:
            matrix (Matrix): 適用する hlib 行列。
            ws (bool): True はワールド、False はローカル空間として解釈する。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: matrix が Matrix でない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。
            ValueError: 行列を分解できない、または必要な親行列を反転できない場合。
        """
        if not isinstance(matrix, Matrix):
            raise TypeError("matrix must be an hlib Matrix")
        if not self.is_valid():
            raise RuntimeError("Cannot compose an invalid transform")
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix)
        return self

    @undo_chunk("hlibTransformShow")
    def show(self):
        """visibility を True に設定する。

        Returns:
            Transform: 自身。
        """
        self.plug("visibility").set(True)
        return self

    @undo_chunk("hlibTransformHide")
    def hide(self):
        """visibility を False に設定する。

        Returns:
            Transform: 自身。
        """
        self.plug("visibility").set(False)
        return self

    @undo_chunk("hlibTransformMakeIdentity")
    def make_identity(self, **kwargs):
        """cmds.makeIdentity のシンプルなラッパー。

        Args:
            kwargs: cmds.makeIdentity にそのまま渡す追加のフラグ
                (apply、translate、rotate、scale、normal など)。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効、または Maya が拒否した場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot freeze transform of an invalid transform")
        cmds.makeIdentity(self.full_name, **kwargs)
        return self

    @undo_chunk("hlibTransformReleaseSRT")
    def release_srt(self):
        """translate/rotate/scale/shear とその子チャンネルを一括でアンロック・切断する。

        各チャンネルとその X/Y/Z 子の両方についてロック解除と接続解除を行う。
        既にアンロック・未接続のチャンネルは変化しない。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot release SRT channels of an invalid transform")
        for channel in ("translate", "rotate", "scale", "shear"):
            plug = self.plug(channel)
            plug.set_locked(False)
            plug.disconnect()
            for child in plug.children():
                child.set_locked(False)
                child.disconnect()
        return self

    def closest_axis_to_vector(self, ref_vector, include_negative=True):
        """自身のローカル軸のうち、ワールド空間の方向ベクトルに最も近いものを求める。

        各ローカル軸をワールド行列（回転・スケールのみ、平行移動は無視）で変換し、
        正規化した上で ref_vector との内積が最大のものを選ぶ。

        Args:
            ref_vector (Vector | Iterable[float]): 比較対象のワールド空間方向ベクトル。
            include_negative (bool): True の場合、負方向の軸（-x/-y/-z）も候補に含める。

        Returns:
            str: 最も近い軸名("x"、"y"、"z"。include_negative が True なら
                "-x"、"-y"、"-z" も返り得る)。

        Raises:
            RuntimeError: ノードが無効な場合。
            ValueError: ref_vector またはいずれかのローカル軸がワールド変換後にゼロベクトルになる場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot evaluate axes of an invalid transform")
        if not isinstance(ref_vector, Vector):
            ref_vector = Vector(*ref_vector)
        ref_vector = ref_vector.normalized()
        matrix = self.get_matrix(ws=True)
        axes = {"x": Vector(1.0, 0.0, 0.0), "y": Vector(0.0, 1.0, 0.0), "z": Vector(0.0, 0.0, 1.0)}
        if include_negative:
            axes.update({f"-{name}": axis * -1.0 for name, axis in axes.items()})
        best_axis = None
        best_dot = None
        for name, axis in axes.items():
            world_axis = matrix.transform_vector(axis).normalized()
            dot = world_axis.dot(ref_vector)
            if best_dot is None or dot > best_dot:
                best_dot = dot
                best_axis = name
        return best_axis

    @undo_chunk("hlibTransformCreateOffsetGroups")
    def create_offset_groups(self, *names):
        """自身を現在のワールド行列に一致させたオフセット(ゼロ)グループで包む。

        names の並びは外側から内側の順(例: ``"zero", "offset"`` なら zero が
        元の親の直下、offset が自身の直上の親になる)。各グループは作成時点の
        自身のワールド行列にそのまま一致するため、自身をそこへ付け替えても
        ワールド位置は変化しない。

        Args:
            names (str): 作成するグループ名。外側から内側の順。省略時は
                ``"<自身の名前>_offset"`` という1個のグループを作成する。

        Returns:
            list[Transform]: 作成したグループ。names と同じ並び(外側から内側)。

        Raises:
            RuntimeError: ノードが無効、または Maya がグループ作成・親変更を拒否した場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot create offset groups for an invalid transform")
        if not names:
            names = (f"{self.name()}_offset",)
        matrix = self.get_matrix(ws=True)
        parent = self.parent_node()
        groups = []
        for name in names:
            kwargs = {}
            if parent is not None:
                kwargs["parent"] = parent.full_name
            group = Transform(cmds.group(empty=True, name=name, **kwargs))
            group.set_matrix(matrix, ws=True)
            groups.append(group)
            parent = group
        self.set_parent(groups[-1])
        return groups
