"""Maya のメッシュシェイプを扱う。"""

import math
from collections import Counter, defaultdict

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.pointComponent import _mirror_plan, _write_points
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _pick_alias, _require_bool, undoChunk, undoTransaction
from ..maths.vector import Vector, _vector_of, _vectors_of_points
from ..util import _PointGrid, _UNSET, _checked_tolerance, _finite_vector, _mirror_axis, _world_space
from .shape import Shape

#: :meth:`Mesh.intersect` で maxDistance=None のときに Maya へ渡す最大距離(単精度で表せる大きな値)。
_NO_DISTANCE_LIMIT = 1.0e30
#: :meth:`Mesh.intersect` で同じ面の交点を1つにまとめる距離の差(cm。単精度の誤差を見込む)。
_INTERSECT_MERGE = 1.0e-4
#: 色の無い頂点を表す、``MFnMesh.getVertexColors`` の既定の色の成分。
_UNSET_COLOR_VALUES = (-1.0, -1.0, -1.0, -1.0)
#: 色の無い頂点に ``MFnMesh.getVertexColors`` が返す色。
_UNSET_COLOR = om2.MColor(_UNSET_COLOR_VALUES)


class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""

    def reorderVertices(self, reference, uvSet="map1", tolerance=1e-6, *, fast=False, match="uv",
        worldSpace=_UNSET, ws=_UNSET):
        """UVまたは頂点位置の一意な対応で、対象の頂点番号を基準メッシュへ合わせる。

        頂点位置・面順/向き・UV・法線・面マテリアルは保持する。エッジ番号は変わり得る。
        スキン等の番号依存データは移し替えず、既存Component参照は処理後に取り直す。
        UVシームは各頂点の面頂点UV群で照合し、曖昧な対応は変更前に拒否する。

        Args:
            reference (Mesh | Node | str): 基準Meshまたは単一メッシュTransform。
            uvSet (str): UV照合のセット名。位置照合では使わない。
            tolerance (float): 非負有限値。UVは成分差、位置はcm距離の許容誤差。
            fast (bool): TrueはUndoなしで再構築し、非ゼロtweakを現在位置へベイクする。
                既定FalseはUndo有効が必須で、非ゼロtweakは未対応。
            match (str): 既定uv、またはposition。
            worldSpace (bool): 位置照合でTrueはワールド空間、Falseは各Shapeのオブジェクト空間。UV照合では使わない。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Mesh: 自身。番号対応が既に同一なら再構築せず返し、再構築用の制限検査にも進まない。

        Raises:
            TypeError: 入力型・fast/worldSpaceが不正な場合。
            ValueError: 対応が曖昧/不完全、トポロジー/面の向きが一致しない、または再構築時に
                入出力履歴・インスタンス・参照・色セット・クリース等がある場合。
            RuntimeError: 再構築時にロック、または通常処理でUndoが無効の場合。
            NotImplementedError: 通常経路で頂点のtweakがある法線の並べ替えの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        from .node import Node
        if match not in ("uv", "position"):
            raise ValueError("match must be uv or position")
        _require_bool(worldSpace, "worldSpace")
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("tolerance must be finite and nonnegative")
        if match == "uv" and (not isinstance(uvSet, str) or not uvSet):
            raise ValueError("uvSet must be a nonempty name")
        reference = Node(Node._input_name(reference))
        if reference.hasFn(om2.MFn.kTransform):
            shapes = reference.getShapes()
            if len(shapes) != 1:
                raise ValueError("Reference transform must have exactly one shape")
            reference = shapes[0]
        if not isinstance(reference, Mesh):
            raise TypeError("reference must be a mesh")
        source, target = reference._geometry_fn(), self._geometry_fn()
        if source.numVertices != target.numVertices or source.numPolygons != target.numPolygons:
            raise ValueError("Meshes must have equal vertex and face counts")
        if not target.numPolygons:
            raise ValueError("Meshes must have polygon faces")
        mapping = (self._uv_vertex_mapping(source, target, uvSet, tolerance) if match == "uv"
                   else self._position_vertex_mapping(source, target, tolerance, worldSpace))
        counts, connects = target.getVertices()
        remapped = [mapping[v] for v in connects]
        if self._face_cycles(*source.getVertices()) != self._face_cycles(counts, remapped):
            raise ValueError("Vertex correspondence does not preserve face topology and winding")
        if all(old == new for old, new in enumerate(mapping)):
            return self
        self._require_reorder_supported(target, fast=fast)
        data = self._reordered_mesh_data(target, counts, connects, remapped, mapping)
        materials = self.getFaceShadingEngines()
        current_uv = target.currentUVSetName()
        if fast:
            points = self.getPlug("pnts").mplug()
            for i in points.getExistingArrayAttributeIndices():
                point = points.elementByLogicalIndex(i)
                for j in range(point.numChildren()):
                    point.child(j).setFloat(0)
            target.copyInPlace(data)
        else:
            if not cmds.undoInfo(query=True, state=True):
                raise RuntimeError("reorderVertices requires Undo enabled, or fast=True")
            with undoTransaction("mlibMeshReorderVertices"):
                # APIで作るのは一時形状のみ。対象への反映と履歴のベイクは標準コマンドでUndoに記録する。
                temporary = cmds.createNode("mesh", skipSelect=True)
                temp_node = Node(temporary)
                parent = cmds.listRelatives(temporary, parent=True, fullPath=True)[0]
                uv_names = om2.MFnMesh(data).getUVSetNames()
                for i, uv_set_name in enumerate(uv_names):
                    cmds.setAttr(temp_node.getFullName() + f".uvSet[{i}].uvSetName", uv_set_name, type="string")
                temp_node.getPlug("cachedInMesh").mplug().setMObject(data)
                # 元のキャッシュをsetAttrのUndoへ保存する。接続のUndoだけではデータは復元されない。
                cmds.setAttr(self.getFullName() + ".outMesh", "v", 0, "vn", 0, "e", 0, type="mesh")
                for uv_set_name in uv_names:
                    if uv_set_name not in (cmds.polyUVSet(self.getFullName(), query=True, allUVSets=True) or []):
                        cmds.polyUVSet(self.getFullName(), create=True, uvSet=uv_set_name)
                cmds.connectAttr(temp_node.getFullName() + ".outMesh", self.getFullName() + ".inMesh")
                cmds.delete(self.getFullName(), constructionHistory=True)
                cmds.delete(parent)
                cmds.polyUVSet(self.getFullName(), currentUVSet=True, uvSet=current_uv)
                groups = defaultdict(list)
                for face, material in enumerate(materials):
                    if material is not None:
                        groups[material.getFullName()].append("{}.f[{}]".format(self.getFullName(), face))
                for material, faces in groups.items():
                    cmds.sets(faces, edit=True, forceElement=material)
        return self

    def getVertex(self, index):
        """頂点番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの頂点番号。

        Returns:
            Vertex: シーン上の頂点を参照するラッパー。

        Raises:
            IndexError: 頂点番号が範囲外の場合。
        """
        return Vertex(self, index)

    def getVertices(self, indices=None):
        """指定した頂点群を取得する。

        Args:
            indices (Iterable[int] | None): 頂点番号。None は現在の全頂点。

        Returns:
            Vertices: 番号順を維持し、重複を除いたコレクション。
        """
        return Vertices(self, indices)

    def getShadingEngines(self):
        """このDAGインスタンスのフェースへ割り当てられたShadingEngineを取得する。

        Returns:
            list[ShadingEngine]: 使用中のセット。未割り当ては除外する。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self._geometry_fn().getConnectedShaders(self.mpath().instanceNumber())
        return [ShadingEngine(groups[i]) for i in sorted(set(indices)) if i >= 0]

    def getFaceShadingEngines(self):
        """面番号順の割り当てを取得する。

        Returns:
            list[ShadingEngine | None]: 全フェースの割り当て。未割り当てはNone。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self._geometry_fn().getConnectedShaders(self.mpath().instanceNumber())
        wrapped = [ShadingEngine(group) for group in groups]
        return [wrapped[i] if i >= 0 else None for i in indices]

    def mfn(self):
        """この mesh で最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持つ場合は ``om2.MFnMesh``。``mlib.createNode("mesh")`` 直後のように形状データを
        持たない空のシェイプは ``om2.MFnMesh`` が使えない(Maya 2027 では作成時に ValueError、
        版により作成後の照会で RuntimeError)ため、``om2.MFnDagNode`` を返す。DagNode 共通の照会
        (中間オブジェクト判定・親の列挙等)は空のシェイプでも使える。

        Returns:
            om2.MFnMesh | om2.MFnDagNode: この mesh の function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        path = self.mpath()
        try:
            fn = om2.MFnMesh(path)
            # 版により作成は通り照会で失敗するため、形状データの有無を作成直後に確かめる。
            fn.typeId
        except (RuntimeError, ValueError):
            return om2.MFnDagNode(path)
        return fn

    def getNumVertices(self):
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        return self._geometry_fn().numVertices

    def getNumPolygons(self):
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        return self._geometry_fn().numPolygons

    def getNumEdges(self):
        """エッジ数を取得する。

        Returns:
            int: メッシュのエッジ数。
        """
        return self._geometry_fn().numEdges

    def getPoints(self, worldSpace=_UNSET, *, ws=_UNSET):
        """全頂点の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: 頂点番号順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。そのまま :meth:`setPoints` へ渡せる。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return _vectors_of_points(self._geometry_fn().getPoints(space))

    def setPoints(self, points, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """全頂点の位置を一度に書き込み、自身を返す。

        :meth:`getPoints` と同じ並び・単位(内部単位cm)の点列を受け付け、通常は ``cmds.xform`` で
        書き込んで1回のUndoにまとめる。``fast=True`` は ``MFnMesh.setPoints`` で全頂点を1回で書き込み、
        Undoに記録しない。頂点数・トポロジー・UVは変更しない。
        :meth:`NurbsCurve.setCvPositions <mlib.nodes.nurbsCurve.NurbsCurve.setCvPositions>` と同じ形の入口。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 頂点番号順の位置。
                :meth:`getPoints` の結果(list[Vector])・3個の数値のtupleの列・``om2.MPointArray`` を
                そのまま受け付ける。各点は3個の有限な数値。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または点の型・成分が不正な場合。
            ValueError: 点の数が頂点数と合わない、または成分が有限でない場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。

        Note:
            現在と同じ位置の頂点は書き込まない(``getPoints()`` の結果を一部だけ変えて戻す使い方では、
            変えた頂点だけを書き込む)。書き込む頂点ごとに ``cmds.xform`` を呼ぶため(``setCvPositions``
            と同じ)、多数の頂点を動かす場合は頂点数に比例して時間がかかる(目安は1頂点あたり約1ms)。
            ``fast=True`` は全頂点をまとめて書くため、頂点数が多いほど差が大きい。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        values = geometry_edit.point_list(points)
        fn = self._geometry_fn()
        count = fn.numVertices
        if len(values) != count:
            raise ValueError(f"Expected {count} points, got {len(values)}")
        current = fn.getPoints(om2.MSpace.kWorld if ws else om2.MSpace.kObject)
        changed = [index for index, (value, point) in enumerate(zip(values, current))
                   if value != (point.x, point.y, point.z)]
        with _edit_context("mlibMeshSetPoints", fast, transaction=True):
            geometry_edit.set_positions(self, changed, [values[index] for index in changed], ws, fast=fast)
        return self

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False, ws=_UNSET):
        """頂点座標を、指定空間の中心pivotに対して反転する(``2 * pivot - 現在座標``)。

        Transform・トポロジー(頂点番号・面の接続と頂点順)は変更しない。共有Shapeの全インスタンスへ影響する。
        複製・結合・片側からの対称化・法線の反転は行わない(奇数軸の反転で面の向きが裏返る)。
        入力をすべて検証してから書き込み、通常は ``cmds.xform`` を頂点ごとに呼んで1回のUndoにまとめる
        (目安は1頂点あたり約0.2ms)。``fast=True`` は ``MFnMesh.setPoints`` で全頂点を1回で書く。
        :meth:`Vertices.mirror <mlib.components.pointComponent.PointComponents.mirror>` と同じ処理。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。既定は原点で、Transformのピボットとは独立。
            indices (Iterable[int] | None): 頂点番号。Noneは全頂点、空列は変更なし。重複は1回だけ処理する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、axisが文字列・int以外、または番号の型が不正な場合。
            ValueError: axis・pivotが不正、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 頂点番号が負または範囲外の場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        _write_points([self._mirror_plan(axis, ws, pivot, indices, fast)], fast, "mlibMeshMirror")
        return self

    def getVertexNormals(self, worldSpace=_UNSET, angleWeighted=False, *, ws=_UNSET):
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            angleWeighted (bool): True の場合は隣接面の角度でウェイト付けした法線を取得する。

        Returns:
            list[Vector]: 頂点番号順の平均法線。angleWeighted=False では
                角度によるウェイト付けを行わない。MFnMesh.getVertexNormals() を使用する。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        # MFloatVectorはom2の多重定義の解決を通さず、成分を写して同じ値のVectorにする。
        return [_vector_of(Vector, value) for value in self._geometry_fn().getVertexNormals(angleWeighted, space)]

    def getVertexAdjacency(self, worldSpace=_UNSET, *, ws=_UNSET):
        """頂点IDごとの隣接頂点とエッジ長を照会する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[list[tuple[int, float]]]: 頂点ID順の隣接リスト。
            各要素は隣接頂点IDとcm単位の距離で、エッジID順に格納する。
            孤立頂点は空リスト、重複エッジは別々に保持する。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        mesh_fn = self._geometry_fn()
        # 距離だけを求めるため、Vector へ変換せずに om2 の点列を読む。
        points = mesh_fn.getPoints(om2.MSpace.kWorld if ws else om2.MSpace.kObject)
        adjacency = [[] for _ in points]
        for index in range(mesh_fn.numEdges):
            first, second = mesh_fn.getEdgeVertices(index)
            delta = points[first] - points[second]
            length = (delta.x * delta.x + delta.y * delta.y + delta.z * delta.z) ** 0.5
            adjacency[first].append((second, length))
            adjacency[second].append((first, length))
        return adjacency

    def getShells(self):
        """辺でつながった頂点のまとまり(シェル)を取得する。

        Returns:
            list[Vertices]: シェルごとの頂点(番号の昇順)。シェルは最小の頂点番号の順に並ぶ。
                孤立した頂点は1頂点のシェルになる。
        """
        fn = self._geometry_fn()
        neighbors = [[] for _ in range(fn.numVertices)]
        for edge in range(fn.numEdges):
            first, second = fn.getEdgeVertices(edge)
            neighbors[first].append(second)
            neighbors[second].append(first)
        seen = [False] * len(neighbors)
        shells = []
        for start in range(len(neighbors)):
            if seen[start]:
                continue
            seen[start] = True
            shell = []
            stack = [start]
            # 再帰を使わず、大きなシェルでも深さの上限に当たらないようにする。
            while stack:
                vertex = stack.pop()
                shell.append(vertex)
                for neighbor in neighbors[vertex]:
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        stack.append(neighbor)
            shells.append(Vertices(self, sorted(shell)))
        return shells

    def getTriangles(self):
        """Maya の三角形分割で、ポリゴンを三角形に分けた頂点の組を取得する。

        Returns:
            list[tuple[int, int, int]]: 三角形ごとの頂点番号。フェース番号の順で、各フェース内は Maya の分割順。
        """
        _counts, vertices = self._geometry_fn().getTriangles()
        return [(vertices[index], vertices[index + 1], vertices[index + 2]) for index in range(0, len(vertices), 3)]

    def getMirrorVertexMap(self, axis="x", tolerance=0.01, worldSpace=_UNSET, *, ws=_UNSET):
        """頂点ごとに、位置を軸で反転した反対側の頂点を取得する。

        反転した位置から ``tolerance`` 以内で最も近い頂点を反対側とする。トポロジーは見ない。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、ミラー面 ``"YZ"``・``"XZ"``・``"XY"``、または0/1/2。既定 ``"x"``。
            tolerance (float): 反転した位置と頂点の距離の許容量(cm)。正の有限値。既定0.01。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            dict[int, int]: {頂点番号: 反対側の頂点番号}。反対側が見つからない頂点は含めない。
                軸の上の頂点は自身へ対応する(キーと値が同じ)。

        Raises:
            TypeError: axisが文字列・int以外、toleranceが実数以外、またはworldSpaceがbool以外の場合。
            ValueError: axisが不正、またはtoleranceが正の有限値でない場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        component = _mirror_axis(axis)
        limit = _checked_tolerance(tolerance, positive=True)
        points = [(point.x, point.y, point.z) for point in self._raw_points(worldSpace)]
        if not points:
            return {}
        grid = _PointGrid(points)
        result = {}
        for index, point in enumerate(points):
            mirrored = list(point)
            mirrored[component] = -mirrored[component]
            found, _ = grid.nearest(mirrored, maxDistance=limit)
            if found is not None:
                result[index] = found
        return result

    def getClosestVertex(self, point, worldSpace=_UNSET, *, ws=_UNSET):
        """指定した位置に最も近い頂点を取得する。

        頂点の位置だけで比べる(面の上の最近点ではない)。多数の点を調べるなら :meth:`getClosestVertices` を使う。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vertex: 最も近い頂点。

        Raises:
            TypeError: 点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに頂点が無い場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        return Vertex(self, self.getClosestVertices([point], worldSpace=worldSpace)[0])

    def getClosestVertices(self, points, worldSpace=_UNSET, *, ws=_UNSET):
        """点ごとに、最も近い頂点の番号を取得する。

        頂点の位置に一様な格子を作って探す(面の上の最近点ではない)。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 位置(cm)の並び。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[int]: 点の順の、最も近い頂点の番号。

        Raises:
            TypeError: 点列・点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに頂点が無い場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        values = geometry_edit.point_list(points)
        vertices = [(point.x, point.y, point.z) for point in self._raw_points(worldSpace)]
        if not vertices:
            raise ValueError(f"Mesh has no vertices: {self.getFullName()}")
        grid = _PointGrid(vertices)
        return [grid.nearest(value)[0] for value in values]

    def getEdge(self, index):
        """番号から Edge を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Edge: シーンを参照する単体ラッパー。
        """
        return Edge(self, index)

    def getEdges(self, indices=None):
        """指定した Edge 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Edges: 重複を除いたコレクション。
        """
        return Edges(self, indices)

    def getFace(self, index):
        """番号から Face を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Face: シーンを参照する単体ラッパー。
        """
        return Face(self, index)

    def getFaces(self, indices=None):
        """指定した Face 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Faces: 重複を除いたコレクション。
        """
        return Faces(self, indices)

    def getUV(self, index):
        """番号から UV を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            UV: シーンを参照する単体ラッパー。
        """
        return UV(self, index)

    def getUVs(self, indices=None):
        """指定した UV 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            UVs: 重複を除いたコレクション。
        """
        return UVs(self, indices)

    def getNumUVs(self):
        """現在の UV セットの要素数。

        Returns:
            int: UV 数。
        """
        return self._geometry_fn().numUVs()

    def getClosestPoint(self, point, worldSpace=_UNSET, *, ws=_UNSET):
        """指定した位置に最も近い、メッシュの面の上の点を取得する。

        ``MFnMesh.getClosestPoint`` を使う。頂点だけを比べる :meth:`getClosestVertex` と違い、
        面の内部・エッジの上の点も返す。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[Vector, int]: 面の上の最も近い点(cm)と、その点を含む面の番号。

        Raises:
            TypeError: 点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに面が無い場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        value = self._resolve_query_point(point)
        fn = self._require_faces()
        closest, face = fn.getClosestPoint(value, om2.MSpace.kWorld if ws else om2.MSpace.kObject)
        return _vector_of(Vector, closest), face

    def getClosestNormal(self, point, worldSpace=_UNSET, *, ws=_UNSET):
        """指定した位置に最も近い面の上の点で、補間した法線を取得する。

        最も近い点を含む三角形の3つの面頂点法線(ハード/ソフトエッジを反映した、表示に使う法線)を、
        その点の重心座標で補間して長さ1にする。``MFnMesh.getClosestNormal`` が返す面法線ではない。
        ハードエッジだけのメッシュ(立方体等)では面法線と同じ向きになる。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の法線。ワールド空間ではオブジェクト空間の法線をマトリクスの逆転置で変換する。

        Raises:
            TypeError: 点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに面が無い場合。

        Note:
            最も近い点はオブジェクト空間で探す(``MMeshIntersector``)。非一様なスケールを持つ
            メッシュのワールド空間では、:meth:`getClosestPoint` と違う面の点になることがある。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        value = self._resolve_query_point(point)
        fn, face, corners = self._closest_triangle(value, ws)
        normal = om2.MVector()
        for vertex, weight in corners:
            normal += om2.MVector(fn.getFaceVertexNormal(face, vertex, om2.MSpace.kObject)) * weight
        if normal.length() < 1e-12:
            # 補間で打ち消し合う退化した場合は面法線を使う。
            normal = fn.getPolygonNormal(face, om2.MSpace.kObject)
        if ws:
            normal = normal * self.mpath().inclusiveMatrixInverse().transpose()
        return _vector_of(Vector, normal.normal())

    def intersect(self, origin, direction, *, maxDistance=None, worldSpace=_UNSET, ws=_UNSET):
        """半直線とメッシュの交点を、近い順に取得する。

        ``MFnMesh.allIntersections`` を使い、``origin`` から ``direction`` の向きへだけ調べる(逆向きは調べない)。
        面の向き(法線)に関係なく、表からでも裏からでも当たる(両面)。

        Args:
            origin (Sequence[float] | om2.MPoint | om2.MVector): 半直線の始点(cm)。
            direction (Sequence[float] | om2.MVector): 向き。長さは問わない(内部で長さ1にする)。
            maxDistance (float | None): 始点からの最大距離(cm)。正の有限値。Noneは制限なし。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[tuple[Vector, int, float]]: (交点、面の番号、始点からの距離cm)の距離の昇順。
                当たらなければ空。同じ面を三角形の境目で2回当てた結果は1つにまとめる。
                面と面の境目のエッジに当たった場合は、それぞれの面を別の要素で返す。

        Raises:
            TypeError: 点・向きの型・成分が不正、maxDistanceが数値・None以外、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、directionの長さが0、またはmaxDistanceが正の有限値でない場合。

        Note:
            Mayaの交差判定は単精度(float)で計算するため、交点と距離は1e-5程度の誤差を含む。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        source = self._resolve_query_point(origin, "origin")
        vector = om2.MVector(*geometry_edit.point_list([direction])[0])
        if vector.length() == 0:
            raise ValueError("direction must have a nonzero length")
        if maxDistance is None:
            limit = _NO_DISTANCE_LIMIT
        else:
            if isinstance(maxDistance, bool) or not isinstance(maxDistance, (int, float)):
                raise TypeError("maxDistance must be a number or None")
            if not math.isfinite(maxDistance) or maxDistance <= 0:
                raise ValueError("maxDistance must be positive and finite")
            limit = float(maxDistance)
        fn = self._geometry_fn()
        if not fn.numPolygons:
            return []
        vector.normalize()
        found = fn.allIntersections(om2.MFloatPoint(source.x, source.y, source.z),
                                    om2.MFloatVector(vector.x, vector.y, vector.z),
                                    om2.MSpace.kWorld if ws else om2.MSpace.kObject, limit, False,
                                    sortHits=True)
        if found is None:
            return []
        points, distances, faces = found[0], found[1], found[2]
        result = []
        for distance, face, index in sorted(zip(distances, faces, range(len(faces)))):
            # 四角形などの面を分けた三角形の境目に当たると、同じ面・同じ距離の交点が2つ返る。
            if any(face == other and abs(distance - previous) <= _INTERSECT_MERGE
                   for _point, other, previous in result):
                continue
            hit = points[index]
            result.append((_vector_of(Vector, (hit.x, hit.y, hit.z)), face, float(distance)))
        return result

    def getUVAtPoint(self, point, uvSet=None, worldSpace=_UNSET, *, ws=_UNSET):
        """指定した位置に最も近い面の上の点の UV を取得する。

        位置が面の上に無ければ、最も近い面の上の点の UV になる。最も近い点を含む三角形の3つの面頂点UVを、
        その点の重心座標で補間する(``closestPointOnMesh`` ノードの ``parameterU/V`` と同じ値)。
        ``MFnMesh.getUVAtPoint`` は面の境目の近くで隣の面のUVを返すことがあるため使わない。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[float, float]: (u, v)。

        Raises:
            TypeError: 点の型・成分が不正、uvSetが文字列・None以外、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、UVセットが無い、またはメッシュに面が無い場合。
            RuntimeError: 最も近い面にUVが割り当てられていない場合。

        Note:
            最も近い点は :meth:`getClosestNormal` と同じくオブジェクト空間で探す。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        value = self._resolve_query_point(point)
        name = self._resolve_uv_set(uvSet)
        fn, face, corners = self._closest_triangle(value, ws)
        local = list(fn.getPolygonVertices(face))
        u = v = 0.0
        for vertex, weight in corners:
            try:
                corner_u, corner_v = fn.getUV(fn.getPolygonUVid(face, local.index(vertex), name), name)
            except RuntimeError:
                raise RuntimeError(f"The closest face has no UVs in {name}: {self.getFullName()}") from None
            u += corner_u * weight
            v += corner_v * weight
        return u, v

    def getPointAtUV(self, u, v, uvSet=None, worldSpace=_UNSET, *, ws=_UNSET):
        """UV の位置に対応する、面の上の点を取得する。

        面番号の順に、UVの範囲に (u, v) を含む面を ``MFnMesh.getPointAtUV`` で調べ、最初に見つかった面の点を返す。
        UVが重なっていて複数の面に当たる場合も、番号の最も小さい面の点になる。

        Args:
            u (float): U座標。
            v (float): V座標。
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector | None: 面の上の点(cm)。どの面のUVにも含まれない位置ならNone。

        Raises:
            TypeError: u・vが数値以外、uvSetが文字列・None以外、またはworldSpaceがbool以外の場合。
            ValueError: u・vが有限でない、またはUVセットが無い場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        values = []
        for label, value in (("u", u), ("v", v)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{label} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{label} must be finite")
            values.append(float(value))
        u, v = values
        name = self._resolve_uv_set(uvSet)
        fn = self._geometry_fn()
        counts, ids = fn.getAssignedUVs(name)
        us, vs = fn.getUVs(name)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        offset = 0
        margin = 1e-6
        for face, count in enumerate(counts):
            face_ids = ids[offset:offset + count]
            offset += count
            if not count:
                continue
            face_u = [us[i] for i in face_ids]
            face_v = [vs[i] for i in face_ids]
            if not (min(face_u) - margin <= u <= max(face_u) + margin
                    and min(face_v) - margin <= v <= max(face_v) + margin):
                continue
            try:
                found = fn.getPointAtUV(face, u, v, space, name, margin)
            except RuntimeError:
                # UVの外接矩形には入るが面のUVの外にある場合、Mayaは失敗を返す。
                continue
            return _vector_of(Vector, found)
        return None

    def getVertexColors(self, colorSet=None):
        """頂点ごとの色を取得する。

        ``MFnMesh.getVertexColors`` を使う。面ごとに違う色を持つ頂点(面頂点の色)は、その平均になる。

        Args:
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット。

        Returns:
            list[tuple[float, float, float, float] | None]: 頂点番号順の(R, G, B, A)。
                色の無い頂点はNone。Noneを指定してカラーセットが1つも無い場合は全てNone。

        Raises:
            TypeError: colorSetが文字列・None以外の場合。
            ValueError: 指定した名前のカラーセットが無い場合。
        """
        fn = self._geometry_fn()
        name = self._resolve_color_set(colorSet, fn)
        if name is None:
            return [None] * fn.numVertices
        result = []
        for color in fn.getVertexColors(name, _UNSET_COLOR):
            value = (color.r, color.g, color.b, color.a)
            result.append(None if value == _UNSET_COLOR_VALUES else value)
        return result

    def setVertexColors(self, colors, vertices=None, *, colorSet=None, fast=False):
        """頂点ごとの色を設定し、自身を返す。

        通常は ``cmds.polyColorPerVertex`` で、同じ色の頂点をまとめて1回ずつ書き、1回のUndoにまとめる。
        色の数が多いと時間がかかる(目安は1色あたり約1ms)。``fast=True`` は ``MFnMesh.setVertexColors`` で
        1回で書き、Undoに記録しない。頂点のすべての面頂点の色を同じ色にする。

        Args:
            colors (Iterable[Sequence[float] | om2.MColor]): 頂点の色。各色は (R, G, B) または (R, G, B, A) の
                有限な数値(Aを省略すると1.0)。vertices と同じ数(None なら頂点数)。
            vertices (Component | Components | Iterable[int] | None): 書き込む頂点の番号。None は全頂点。
                重複は不可。指定した順に colors と対応する。
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット(無ければMayaが
                ``colorSet1`` を作る)。名前を指定した場合は既にある必要があり、現在のカラーセットは変えない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: fastがbool以外、colorSetが文字列・None以外、または色・頂点の型が不正な場合。
            ValueError: 色の数が頂点の数と合わない、成分の数が3・4以外か有限でない、頂点が重複している、
                別のメッシュの頂点を渡した、またはカラーセットが無い場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: シェイプのロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。

        Note:
            通常経路は、コンストラクションヒストリのあるメッシュでは ``polyColorPerVertex`` ノードを履歴へ足す。
        """
        _require_bool(fast, "fast")
        with _edit_context("mlibMeshSetVertexColors", fast):
            fn = self._geometry_fn()
            name = self._resolve_color_set(colorSet, fn)
            indices = (list(range(fn.numVertices)) if vertices is None
                       else self._resolve_vertex_indices(vertices, fn.numVertices))
            values = self._resolve_colors(colors, len(indices))
            if fast:
                self._set_vertex_colors_fast(fn, name, indices, values)
            else:
                self._set_vertex_colors_cmds(name, indices, values)
        return self

    def getUVSetNames(self):
        """UVセットの名前を取得する。

        Returns:
            list[str]: Mayaの並び順のUVセットの名前。先頭が既定のUVセット(``uvSet[0]``)。
        """
        return list(self._geometry_fn().getUVSetNames())

    def getCurrentUVSet(self):
        """現在のUVセットの名前を取得する。

        Returns:
            str: 現在のUVセットの名前。
        """
        return self._geometry_fn().currentUVSetName()

    def setCurrentUVSet(self, name):
        """現在のUVセットを設定し、自身を返す。

        ``cmds.polyUVSet(currentUVSet=True)`` で設定し、1回のUndoで戻る。

        Args:
            name (str): 既にあるUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、またはそのUVセットが無い場合。
        """
        self._require_uv_set(name, "name", exists=True)
        with undoChunk("mlibMeshSetCurrentUVSet"):
            cmds.polyUVSet(self.getFullName(), currentUVSet=True, uvSet=name)
        return self

    def createUVSet(self, name):
        """空のUVセットを作り、自身を返す。

        ``cmds.polyUVSet(create=True)`` で作り、1回のUndoで戻る。現在のUVセットは変えない。
        コンストラクションヒストリのあるメッシュでは ``createUVSet`` ノードを履歴へ足す。

        Args:
            name (str): 新しいUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または同じ名前のUVセットが既にある場合。
        """
        self._require_uv_set(name, "name", exists=False)
        with undoChunk("mlibMeshCreateUVSet"):
            cmds.polyUVSet(self.getFullName(), create=True, uvSet=name)
        return self

    def copyUVSet(self, source, target):
        """UVセットを新しい名前へ複製し、自身を返す。

        ``cmds.polyUVSet(copy=True)`` で複製し、1回のUndoで戻る。現在のUVセットは変えない。

        Args:
            source (str): 複製元のUVセットの名前。
            target (str): 新しいUVセットの名前。既にある名前は不可(上書きしない)。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: source・targetが文字列以外の場合。
            ValueError: 名前が空、sourceが無い、またはtargetが既にある場合。
        """
        self._require_uv_set(source, "source", exists=True)
        self._require_uv_set(target, "target", exists=False)
        with undoChunk("mlibMeshCopyUVSet"):
            cmds.polyUVSet(self.getFullName(), copy=True, uvSet=source, newUVSet=target)
        return self

    def renameUVSet(self, name, newName):
        """UVセットの名前を変え、自身を返す。

        ``cmds.polyUVSet(rename=True)`` で変え、1回のUndoで戻る。現在のUVセットの名前を変えた場合は、
        新しい名前が現在のUVセットになる。

        Args:
            name (str): 既にあるUVセットの名前。
            newName (str): 新しい名前。既にある名前は不可。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: name・newNameが文字列以外の場合。
            ValueError: 名前が空、nameが無い、またはnewNameが既にある場合。
        """
        self._require_uv_set(name, "name", exists=True)
        self._require_uv_set(newName, "newName", exists=False)
        with undoChunk("mlibMeshRenameUVSet"):
            cmds.polyUVSet(self.getFullName(), rename=True, uvSet=name, newUVSet=newName)
        return self

    def deleteUVSet(self, name):
        """UVセットを削除し、自身を返す。

        ``cmds.polyUVSet(delete=True)`` で削除し、1回のUndoで戻る。現在のUVセットを削除すると、
        Mayaは既定のUVセット(:meth:`getUVSetNames` の先頭)を現在のUVセットにする。

        Args:
            name (str): 既にあるUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、そのUVセットが無い、または既定のUVセット(``uvSet[0]``。通常 ``map1``)の場合。
                Mayaは既定のUVセットを削除できない(名前が ``map1`` でなくても同じ)。
        """
        self._require_uv_set(name, "name", exists=True)
        if name == self._default_uv_set():
            raise ValueError(f"The default UV set cannot be deleted: {name}")
        with undoChunk("mlibMeshDeleteUVSet"):
            cmds.polyUVSet(self.getFullName(), delete=True, uvSet=name)
        return self

    def getBorderEdges(self):
        """メッシュの縁(接する面が1つだけ)のエッジを取得する。

        3つ以上の面が接する非多様体のエッジと、面の無いエッジは含めない。

        Returns:
            Edges: 番号の昇順のエッジ。縁が無ければ空。
        """
        iterator = om2.MItMeshEdge(self.mpath())
        found = []
        while not iterator.isDone():
            if iterator.numConnectedFaces() == 1:
                found.append(iterator.index())
            iterator.next()
        return Edges(self, found)

    def getBorderVertices(self):
        """メッシュの縁のエッジ(:meth:`getBorderEdges`)の端の頂点を取得する。

        Returns:
            Vertices: 番号の昇順の頂点。縁が無ければ空。
        """
        fn = self._geometry_fn()
        found = set()
        for edge in self.getBorderEdges().indices:
            found.update(fn.getEdgeVertices(edge))
        return Vertices(self, sorted(found))

    def _raw_points(self, worldSpace):
        """全頂点の位置を om2 の点列で返す(Vector へ変換しない照会用)。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。

        Returns:
            om2.MPointArray: 頂点番号順の位置。
        """
        ws = _world_space(worldSpace)
        return self._geometry_fn().getPoints(om2.MSpace.kWorld if ws else om2.MSpace.kObject)

    @staticmethod
    def _position_vertex_mapping(source, target, tolerance, world_space):
        """指定空間で許容距離内の一意な頂点対応を空間セルから求める。"""
        space = om2.MSpace.kWorld if world_space else om2.MSpace.kObject
        source_points, target_points = source.getPoints(space), target.getPoints(space)
        buckets = defaultdict(list)

        def key(point):
            values = (point.x, point.y, point.z)
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Vertex positions must be finite")
            return tuple(math.floor(v / tolerance) for v in values) if tolerance else values

        for index, point in enumerate(source_points):
            buckets[key(point)].append(index)
        mapping = []
        for point in target_points:
            cell = key(point)
            cells = [(cell[0] + x, cell[1] + y, cell[2] + z)
                     for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)] if tolerance else [cell]
            candidates = [index for neighbor in cells for index in buckets.get(neighbor, ())
                          if (point - source_points[index]).length() <= tolerance]
            if len(candidates) != 1:
                raise ValueError("Position correspondence is missing or ambiguous within tolerance")
            mapping.append(candidates[0])
        if len(set(mapping)) != len(mapping):
            raise ValueError("Position correspondence is not one-to-one")
        return mapping

    @staticmethod
    def _uv_vertex_mapping(source, target, uv_set, tolerance):
        """面頂点UV群が一意に一致する旧対象番号→基準番号を求める。"""
        def signatures(fn):
            if uv_set not in fn.getUVSetNames():
                raise ValueError(f"UV set does not exist: {uv_set}")
            counts, connects = fn.getVertices()
            uv_counts, uv_ids = fn.getAssignedUVs(uv_set)
            if list(counts) != list(uv_counts):
                raise ValueError("Every face vertex must have a UV")
            u, v = fn.getUVs(uv_set)
            values = [[] for _ in range(fn.numVertices)]
            for vertex, uv in zip(connects, uv_ids):
                value = (u[uv], v[uv])
                if not all(math.isfinite(x) for x in value):
                    raise ValueError("UV coordinates must be finite")
                values[vertex].append(value)
            if any(not row for row in values):
                raise ValueError("Isolated vertices cannot be matched by UV")
            return [sorted(row) for row in values]

        source_rows, target_rows = signatures(source), signatures(target)
        buckets = defaultdict(list)
        def key(value):
            return tuple(math.floor(x / tolerance) for x in value) if tolerance else value
        for i, row in enumerate(source_rows):
            buckets[(len(row), key(row[0]))].append(i)
        mapping = []
        for row in target_rows:
            anchor = key(row[0])
            keys = [(anchor[0] + x, anchor[1] + y) for x in (-1, 0, 1) for y in (-1, 0, 1)] if tolerance else [anchor]
            candidates = [i for cell in keys for i in buckets.get((len(row), cell), ())
                          if all(abs(a - b) <= tolerance for pair, other in zip(row, source_rows[i])
                                 for a, b in zip(pair, other))]
            if len(candidates) != 1:
                raise ValueError("UV vertex correspondence is missing or ambiguous")
            mapping.append(candidates[0])
        if len(set(mapping)) != len(mapping):
            raise ValueError("UV correspondence is not one-to-one")
        return mapping

    @staticmethod
    def _face_cycles(counts, connects):
        """面の開始頂点に依存せず、面の向きと頂点接続を比較する。"""
        result, offset = [], 0
        for count in counts:
            row = list(connects[offset:offset + count])
            pivot = row.index(min(row))
            result.append(tuple(row[pivot:] + row[:pivot]))
            offset += count
        return Counter(result)

    def _require_reorder_supported(self, fn, *, fast=False):
        """番号依存の外部接続や未対応のメッシュデータを変更前に拒否する。"""
        if self.mpath().isInstanced() or self._dependency_fn().isFromReferencedFile:
            raise ValueError("Instanced or referenced targets are not supported")
        if self._dependency_fn().isLocked:
            raise RuntimeError("Mesh is locked")
        if self.getPlug("outMesh").mplug().isLocked:
            raise RuntimeError("Mesh output is locked")
        sets, members = fn.getConnectedSetsAndMembers(self.mpath().instanceNumber(), False)
        if any(not member.isNull() and not group.hasFn(om2.MFn.kShadingEngine)
               for group, member in zip(sets, members)):
            raise ValueError("Component sets other than shading assignments are not supported")
        if self.getPlug("inMesh").mplug().isDestination:
            raise ValueError("Target must have no input history")
        for name in ("outMesh", "worldMesh"):
            plug = self.getPlug(name).mplug()
            plugs = [plug.elementByLogicalIndex(i) for i in plug.getExistingArrayAttributeIndices()] if plug.isArray else [plug]
            if any(p.isSource for p in plugs):
                raise ValueError("Target must not drive downstream geometry")
        creased = False
        for getter in (fn.getCreaseEdges, fn.getCreaseVertices):
            try:
                creased = creased or bool(getter()[0])
            except RuntimeError:
                # クリースデータ自体がない通常メッシュではMayaがkFailureを返す。
                pass
        if fn.getColorSetNames() or creased or fn.getHoles():
            raise ValueError("Color sets, creases and polygon holes are not supported")
        if any(fn.hasBlindData(kind) for kind in (om2.MFn.kMeshVertComponent,
                                                  om2.MFn.kMeshEdgeComponent,
                                                  om2.MFn.kMeshPolygonComponent)):
            raise ValueError("Mesh blind data is not supported")
        for name in ("inMesh", "cachedInMesh", "pnts"):
            plug = self.getPlug(name).mplug()
            require_writable(plug)
            if plug.isArray:
                for i in plug.getExistingArrayAttributeIndices():
                    item = plug.elementByLogicalIndex(i)
                    require_writable(item)
                    for j in range(item.numChildren()):
                        require_writable(item.child(j))
                        if not fast and item.child(j).asFloat() != 0:
                            raise NotImplementedError("Normal reorder does not support vertex tweaks; use fast=True on a copy")

    @staticmethod
    def _reordered_mesh_data(fn, counts, connects, remapped, mapping):
        """シーン外のメッシュデータを作り、面順・UVと法線を移す。"""
        points = fn.getPoints()
        reordered = om2.MPointArray(points)
        for old, new in enumerate(mapping):
            reordered[new] = points[old]
        data = om2.MFnMeshData().create()
        rebuilt = om2.MFnMesh()
        rebuilt.create(reordered, counts, remapped, parent=data)
        # UVセットの追加はmesh dataではなくmeshノードに対してのみ使用できる。
        # 一時ノードで全セットを構築し、コピー後に必ず破棄する。Undo履歴には残さない。
        modifier = om2.MDagModifier()
        parent = modifier.createNode("transform")
        temporary = modifier.createNode("mesh", parent)
        modifier.doIt()
        try:
            om2.MFnDependencyNode(temporary).findPlug("cachedInMesh", False).setMObject(data)
            rebuilt = om2.MFnMesh(temporary)
            Mesh._copy_reorder_details(fn, rebuilt, counts, remapped, mapping)
            result = om2.MFnMeshData().create()
            om2.MFnMesh().copy(temporary, result)
            return result
        finally:
            modifier.undoIt()

    @staticmethod
    def _copy_reorder_details(fn, rebuilt, counts, remapped, mapping):
        """一時メッシュへ全UVセット・エッジの硬軟・固定法線を移す。"""
        if "map1" not in fn.getUVSetNames():
            rebuilt.renameUVSet("map1", fn.getUVSetNames()[0])
        for uv_set in fn.getUVSetNames():
            if uv_set not in rebuilt.getUVSetNames():
                rebuilt.createUVSet(uv_set)
            rebuilt.setUVs(*fn.getUVs(uv_set), uvSet=uv_set)
            rebuilt.assignUVs(*fn.getAssignedUVs(uv_set), uvSet=uv_set)
        rebuilt.setCurrentUVSetName(fn.currentUVSetName())
        smooth = {tuple(sorted(mapping[v] for v in fn.getEdgeVertices(i))): fn.isEdgeSmooth(i)
                  for i in range(fn.numEdges)}
        for i in range(rebuilt.numEdges):
            rebuilt.setEdgeSmoothing(i, smooth[tuple(sorted(rebuilt.getEdgeVertices(i)))])
        rebuilt.cleanupEdgeSmoothing()
        normals = fn.getNormals()
        _, normal_ids = fn.getNormalIds()
        faces = [i for i, count in enumerate(counts) for _ in range(count)]
        locked = [i for i, normal in enumerate(normal_ids) if fn.isNormalLocked(normal)]
        if locked:
            rebuilt.setFaceVertexNormals([om2.MVector(normals[normal_ids[i]]) for i in locked],
                                         [faces[i] for i in locked], [remapped[i] for i in locked])
            rebuilt.lockFaceVertexNormals([faces[i] for i in locked], [remapped[i] for i in locked])

    @staticmethod
    def _resolve_query_point(point, name="point"):
        """照会に使う位置を検証し、``om2.MPoint`` にする。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            name (str): 例外メッセージに使う引数名。

        Returns:
            om2.MPoint: XYZを写した点(wは1)。

        Raises:
            TypeError: 点の型・成分が不正な場合。
            ValueError: 成分の数が3でない、または有限でない場合。
        """
        if isinstance(point, (str, bytes)):
            raise TypeError(f"{name} must be a sequence of 3 numbers")
        return om2.MPoint(*geometry_edit.point_list([point])[0])

    def _require_faces(self):
        """面のあるメッシュの ``om2.MFnMesh`` を返す。

        Returns:
            om2.MFnMesh: この mesh の function set。

        Raises:
            ValueError: メッシュに面が無い場合。
        """
        fn = self._geometry_fn()
        if not fn.numPolygons:
            raise ValueError(f"Mesh has no faces: {self.getFullName()}")
        return fn

    def _closest_triangle(self, point, worldSpace):
        """最も近い面の上の点を含む三角形と、その点の重心座標を返す。

        ``MMeshIntersector`` でオブジェクト空間の最近点を探す。

        Args:
            point (om2.MPoint): 位置(cm)。
            worldSpace (bool): Trueは point をワールド空間とみなし、オブジェクト空間へ変換して探す。

        Returns:
            tuple[om2.MFnMesh, int, list[tuple[int, float]]]: function set・面の番号・三角形の
                (頂点番号, 重心座標のウェイト)の3組。

        Raises:
            ValueError: メッシュに面が無い場合。
        """
        fn = self._require_faces()
        path = self.mpath()
        if worldSpace:
            point = point * path.inclusiveMatrixInverse()
        intersector = om2.MMeshIntersector()
        intersector.create(path.node(), om2.MMatrix())
        found = intersector.getClosestPoint(point)
        first, second = found.barycentricCoords
        vertices = fn.getPolygonTriangleVertices(found.face, found.triangle)
        return fn, found.face, list(zip(vertices, (first, second, 1.0 - first - second)))

    def _resolve_uv_set(self, uvSet):
        """UVセットの指定を、実在する名前にする。

        Args:
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。

        Returns:
            str: UVセットの名前。

        Raises:
            TypeError: uvSetが文字列・None以外の場合。
            ValueError: 名前が空、そのUVセットが無い、またはメッシュにUVセットが無い場合。
        """
        if uvSet is None:
            name = self._geometry_fn().currentUVSetName()
            if not name:
                raise ValueError(f"Mesh has no UV set: {self.getFullName()}")
            return name
        self._require_uv_set(uvSet, "uvSet", exists=True)
        return uvSet

    def _require_uv_set(self, name, label, *, exists):
        """UVセットの名前の型と、その有無を検証する。

        Args:
            name (str): UVセットの名前。
            label (str): 例外メッセージに使う引数名。
            exists (bool): Trueは既にあること、Falseはまだ無いことを求める。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または有無が求める状態と違う場合。
        """
        if not isinstance(name, str):
            raise TypeError(f"{label} must be a str")
        if not name:
            raise ValueError(f"{label} must be a non-empty string")
        found = name in self._geometry_fn().getUVSetNames()
        if exists and not found:
            raise ValueError(f"UV set does not exist: {name}")
        if not exists and found:
            raise ValueError(f"UV set already exists: {name}")

    def _default_uv_set(self):
        """既定のUVセット(``uvSet[0]``)の名前を返す。

        Returns:
            str: 既定のUVセットの名前。
        """
        plug = self._dependency_fn().findPlug("uvSet", False)
        return plug.elementByLogicalIndex(0).child(0).asString()

    def _resolve_color_set(self, colorSet, fn):
        """カラーセットの指定を、実在する名前にする。

        Args:
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット。
            fn (om2.MFnMesh): この mesh の function set。

        Returns:
            str | None: カラーセットの名前。Noneを指定してカラーセットが無ければNone。

        Raises:
            TypeError: colorSetが文字列・None以外の場合。
            ValueError: 名前が空、またはそのカラーセットが無い場合。
        """
        if colorSet is None:
            if not fn.numColorSets:
                return None
            return fn.currentColorSetName() or None
        if not isinstance(colorSet, str):
            raise TypeError("colorSet must be a str or None")
        if not colorSet:
            raise ValueError("colorSet must be a non-empty string")
        if colorSet not in fn.getColorSetNames():
            raise ValueError(f"Color set does not exist: {colorSet}")
        return colorSet

    def _resolve_vertex_indices(self, vertices, count):
        """頂点の指定を、範囲内で重複の無い番号の list にする。

        Args:
            vertices (Component | Components | Iterable[int]): 頂点の参照または番号。
            count (int): 頂点の数。

        Returns:
            list[int]: 指定順の番号。

        Raises:
            TypeError: 番号に変換できない型の場合。
            ValueError: 番号が重複している、または別のメッシュの頂点の場合。
            IndexError: 番号が範囲外の場合。
        """
        shape = getattr(vertices, "shape", None)
        if shape is not None and shape != self:
            raise ValueError(f"vertices belong to another mesh: {shape.getFullName()}")
        if hasattr(vertices, "indices"):
            vertices = vertices.indices
        elif isinstance(getattr(vertices, "index", None), int):
            vertices = [vertices.index]
        if isinstance(vertices, (str, bytes)):
            raise TypeError("vertices must be an iterable of ints")
        try:
            items = list(vertices)
        except TypeError:
            raise TypeError("vertices must be an iterable of ints") from None
        indices = []
        for value in items:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"vertex must be an int, got {type(value).__name__}")
            if not 0 <= value < count:
                raise IndexError(f"Vertex index out of range: {value}")
            indices.append(value)
        if len(set(indices)) != len(indices):
            raise ValueError("vertices must not contain duplicates")
        return indices

    @staticmethod
    def _resolve_colors(colors, count):
        """色の列を検証し、(R, G, B, A) の float tuple の list にする。

        Args:
            colors (Iterable[Sequence[float] | om2.MColor]): 色の列。
            count (int): 必要な数。

        Returns:
            list[tuple[float, float, float, float]]: 色。Aを省略した色は1.0を補う。

        Raises:
            TypeError: 色の列・色・成分の型が不正な場合。
            ValueError: 数が合わない、成分の数が3・4以外、または有限でない場合。
        """
        if isinstance(colors, (str, bytes, om2.MColor)):
            raise TypeError("colors must be an iterable of colors")
        try:
            items = list(colors)
        except TypeError:
            raise TypeError("colors must be an iterable of colors") from None
        if len(items) != count:
            raise ValueError(f"Expected {count} colors, got {len(items)}")
        result = []
        for item in items:
            if isinstance(item, om2.MColor):
                item = (item.r, item.g, item.b, item.a)
            elif isinstance(item, (str, bytes)):
                raise TypeError("each color must be a sequence of 3 or 4 numbers")
            try:
                values = tuple(item)
            except TypeError:
                raise TypeError("each color must be a sequence of 3 or 4 numbers") from None
            if len(values) not in (3, 4):
                raise ValueError("each color must have 3 or 4 components")
            if len(values) == 3:
                values += (1.0,)
            result.append(_finite_vector(values, 4, "color"))
        return result

    def _set_vertex_colors_cmds(self, color_set, indices, values):
        """同じ色の頂点をまとめて ``cmds.polyColorPerVertex`` で書く。

        カラーセットを指定した場合は、書く間だけ現在のカラーセットを切り替えて戻す
        (``polyColorPerVertex`` は現在のカラーセットへ書くため)。

        Args:
            color_set (str | None): 書き込むカラーセット。Noneは現在のカラーセット。
            indices (list[int]): 頂点番号。
            values (list[tuple[float, float, float, float]]): indices と同じ順の色。

        Returns:
            None: 値を返さない。
        """
        if not indices:
            return
        name = self.getFullName()
        current = None
        if color_set is not None:
            current = (cmds.polyColorSet(name, query=True, currentColorSet=True) or [None])[0]
            if current != color_set:
                cmds.polyColorSet(name, currentColorSet=True, colorSet=color_set)
        groups = defaultdict(list)
        for index, value in zip(indices, values):
            groups[value].append(index)
        for (red, green, blue, alpha), group in groups.items():
            cmds.polyColorPerVertex(["{}.vtx[{}]".format(name, index) for index in group],
                                    rgb=(red, green, blue), alpha=alpha)
        if current is not None and current != color_set:
            cmds.polyColorSet(name, currentColorSet=True, colorSet=current)

    def _set_vertex_colors_fast(self, fn, color_set, indices, values):
        """``MFnMesh.setVertexColors`` で色をまとめて書く。Undoに記録しない。

        Args:
            fn (om2.MFnMesh): この mesh の function set。
            color_set (str | None): 書き込むカラーセット。Noneは現在のカラーセット(無ければ ``colorSet1`` を作る)。
            indices (list[int]): 頂点番号。
            values (list[tuple[float, float, float, float]]): indices と同じ順の色。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: シェイプがロックされている場合。
            NotImplementedError: inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        if self.getPlug("inMesh").mplug().isDestination:
            raise NotImplementedError("fast setVertexColors does not support a mesh with input history")
        if self._dependency_fn().isLocked:
            raise RuntimeError(f"Mesh is locked: {self.getFullName()}")
        if not indices:
            return
        if color_set is None:
            if not fn.numColorSets:
                fn.setCurrentColorSetName(fn.createColorSet("colorSet1", False))
            color_set = fn.currentColorSetName()
        current = fn.currentColorSetName()
        if current != color_set:
            fn.setCurrentColorSetName(color_set)
        try:
            fn.setVertexColors(om2.MColorArray([om2.MColor(value) for value in values]), indices)
        finally:
            if current and current != color_set:
                fn.setCurrentColorSetName(current)

    def _mirror_plan(self, axis, ws, pivot, indices, fast):
        """頂点を反転した座標を求め、書込みの計画を返す。シーンは変更しない。

        :meth:`Transform.mirrorGeometry <mlib.nodes.transform.Transform.mirrorGeometry>` が
        全Shapeを検証してから書き込むために使う。

        Args:
            axis (str | int): 反転する軸またはミラー面。
            ws (bool): Trueならワールド空間。検証済み。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。
            indices (Iterable[int] | None): 頂点番号。Noneは全頂点。
            fast (bool): TrueならOpenMayaで直接書けるかも確かめる。

        Returns:
            tuple | None: ``(shape, indices, rows, ws)``。対象が無ければNone。
        """
        self._geometry_fn()
        return _mirror_plan(self.getVertices(indices), axis, ws, pivot, fast)

    def _geometry_fn(self):
        """形状データを要する照会用に ``om2.MFnMesh`` を返す。

        Returns:
            om2.MFnMesh: この mesh の function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        fn = self.mfn()
        if not isinstance(fn, om2.MFnMesh):
            raise RuntimeError("mesh has no geometry data: %s" % self.getFullName())
        return fn
