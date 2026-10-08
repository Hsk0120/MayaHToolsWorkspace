"""Maya のメッシュシェイプを扱う。"""

import math
from collections import Counter, defaultdict

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from .._core.fastWrite import writable
from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from .._core.space import world_space
from ..common._fast import fast_edit, is_fast
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..decorator import undoTransaction
from ..maths.vector import Vector
from .shape import Shape


class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""

    @flag_aliases(ws="worldSpace")
    @fast_edit
    def reorderVertices(self, reference, uv_set="map1", tolerance=1e-6, *, fast=False,
                        match="uv", worldSpace=False):
        """UVまたは頂点位置の対応から自身の頂点番号を基準メッシュに合わせる。

        Args:
            reference (Mesh | Node | str): 基準のメッシュまたは単一メッシュTransform。
            uv_set (str): UV照合のセット名。位置照合では使用しない。
            tolerance (float): 非負の有限誤差。UV照合は各成分の差、位置照合は距離(cm)。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定はcmds経由でUndo可能。
            match (str): uv（既定）またはposition。照合方法だけを切り替える。
            worldSpace (bool): 位置照合をワールド空間で行う。既定Falseは各形状のローカル空間。
                短縮名ws。UV照合では使用しない。

        Returns:
            Mesh: 自身。頂点位置・面の順序と向き・UV・法線・面マテリアルを維持する。

        Raises:
            ValueError: 頂点対応が曖昧、不完全、またはトポロジーが一致しない場合。
            NotImplementedError: 入出力履歴・インスタンス・色セット・クリース等の非対応形状。
            RuntimeError: ロック、または通常モードでUndoが無効の場合。

        スキン等の番号依存データは移し替えない。対象は履歴なしの独立メッシュに限定する。
        既存のComponent参照は古い番号を保持するため、処理後に取り直すこと。
        通常モードは非ゼロの頂点tweakに未対応。fastでは現在位置へベイクして番号を変更する。
        エッジ番号は再構築により変わる場合がある。
        UVシームは各頂点の面頂点UV群で照合する。重なりで候補が複数ある場合は変更しない。
        """
        from .node import Node
        if match not in ("uv", "position"):
            raise ValueError("match must be uv or position")
        if type(worldSpace) is not bool:
            raise TypeError("worldSpace must be bool")
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("tolerance must be finite and nonnegative")
        if match == "uv" and (not isinstance(uv_set, str) or not uv_set):
            raise ValueError("uv_set must be a nonempty name")
        reference = Node(Node._input_name(reference))
        if reference.mnode().hasFn(om2.MFn.kTransform):
            shapes = reference.getShapes()
            if len(shapes) != 1:
                raise ValueError("Reference transform must have exactly one shape")
            reference = shapes[0]
        if not isinstance(reference, Mesh):
            raise TypeError("reference must be a mesh")
        source, target = reference.meshFn(), self.meshFn()
        if source.numVertices != target.numVertices or source.numPolygons != target.numPolygons:
            raise ValueError("Meshes must have equal vertex and face counts")
        if not target.numPolygons:
            raise ValueError("Meshes must have polygon faces")
        mapping = (self._uv_vertex_mapping(source, target, uv_set, tolerance) if match == "uv"
                   else self._position_vertex_mapping(source, target, tolerance, worldSpace))
        counts, connects = target.getVertices()
        remapped = [mapping[v] for v in connects]
        if self._face_cycles(*source.getVertices()) != self._face_cycles(counts, remapped):
            raise ValueError("Vertex correspondence does not preserve face topology and winding")
        if all(old == new for old, new in enumerate(mapping)):
            return self
        self._check_reorder_supported(target)
        data = self._reordered_mesh_data(target, counts, connects, remapped, mapping)
        materials = self.getFaceShadingEngines()
        current_uv = target.currentUVSetName()
        if is_fast():
            points = self.getPlug("pnts").mplug()
            for i in points.getExistingArrayAttributeIndices():
                point = points.elementByLogicalIndex(i)
                for j in range(point.numChildren()):
                    point.child(j).setFloat(0)
            target.copyInPlace(data)
        else:
            if not cmds.undoInfo(query=True, state=True):
                raise RuntimeError("reorderVertices requires Undo enabled, or fast=True")
            with undoTransaction("hlibMeshReorderVertices"):
                # APIで作るのは一時形状のみ。対象への反映と履歴のベイクは標準コマンドでUndoに記録する。
                temporary = cmds.createNode("mesh", skipSelect=True)
                temp_node = Node(temporary)
                parent = cmds.listRelatives(temporary, parent=True, fullPath=True)[0]
                uv_names = om2.MFnMesh(data).getUVSetNames()
                for i, uv_set_name in enumerate(uv_names):
                    cmds.setAttr(temp_node.getFullName() + ".uvSet[{}].uvSetName".format(i), uv_set_name, type="string")
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

    @flag_aliases(ws="worldSpace")
    @fast_edit
    def mirror(self, axis="x", worldSpace=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """頂点位置をミラーし、自身を更新する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は 内部距離単位cm。Transform のピボットとは独立する。
            indices (Iterable[int] | None): 頂点番号。None は全頂点、空列は変更なし。
                重複は1回だけ処理し、負の番号は許容しない。

        Returns:
            Mesh: 編集した自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換が数値的にほぼ特異な場合。
            TypeError: 頂点番号が整数でない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Maya が形状の取得・編集を拒否した場合。

        頂点だけを編集し、Transform、頂点番号、面の接続・頂点順は維持する。
        複製・結合・片側からの対称化・法線反転は行わない。奇数軸で反転すると
        面の向きが反転するため、必要な法線処理は別途行う。1回の Undo で戻せる。
        インスタンス形状はデータを共有する全インスタンスへ影響する。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        ws = world_space(worldSpace)
        self.getVertices(indices).mirror(axis=axis, ws=ws, pivot=pivot)
        return self

    @flag_aliases(idx="index")
    def vertex(self, index):
        """頂点番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの頂点番号。 別名 ``idx`` も使用可能。

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
        """このDAGインスタンスのフェースへ割り当てられたShadingEngineを返す。

        Returns:
            list[ShadingEngine]: 使用中のセット。未割り当ては除外する。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self.meshFn().getConnectedShaders(self.mpath().instanceNumber())
        return [ShadingEngine(groups[i]) for i in sorted(set(indices)) if i >= 0]

    def getFaceShadingEngines(self):
        """面番号順の割り当てを取得する。

        Returns:
            list[ShadingEngine | None]: 全フェースの割り当て。未割り当てはNone。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self.meshFn().getConnectedShaders(self.mpath().instanceNumber())
        wrapped = [ShadingEngine(group) for group in groups]
        return [wrapped[i] if i >= 0 else None for i in indices]

    def meshFn(self):
        """MFnMesh を取得する。

        Returns:
            om2.MFnMesh: この mesh の function set。
        """
        return om2.MFnMesh(self.mpath())

    def getNumVertices(self):
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        return self.meshFn().numVertices

    def getNumPolygons(self):
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        return self.meshFn().numPolygons

    def getNumEdges(self):
        """エッジ数を取得する。

        Returns:
            int: メッシュのエッジ数。
        """
        return self.meshFn().numEdges

    @flag_aliases(ws="worldSpace")
    def getPoints(self, worldSpace=False):
        """全頂点の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

        Returns:
            om2.MPointArray: 頂点番号順の位置。距離は Maya API の内部単位。
        """
        ws = world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.meshFn().getPoints(space)

    @flag_aliases(ws="worldSpace")
    def getVertexNormals(self, worldSpace=False, angle_weighted=False):
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            angle_weighted (bool): True の場合は隣接面の角度で重み付けした法線を取得する。

        Returns:
            list[Vector]: 頂点番号順の平均法線。angle_weighted=False では
                角度による重み付けを行わない。MFnMesh.getVertexNormals() を使用する。
        """
        ws = world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return [Vector(value) for value in self.meshFn().getVertexNormals(angle_weighted, space)]

    @flag_aliases(ws="worldSpace")
    def getVertexAdjacency(self, worldSpace=False):
        """頂点IDごとの隣接頂点とエッジ長を照会する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

        Returns:
            list[list[tuple[int, float]]]: 頂点ID順の隣接リスト。
            各要素は隣接頂点IDとcm単位の距離で、エッジID順に格納する。
            孤立頂点は空リスト、重複エッジは別々に保持する。
        """
        points = self.getPoints(ws=worldSpace)
        adjacency = [[] for _ in points]
        mesh_fn = self.meshFn()
        for index in range(mesh_fn.numEdges):
            first, second = mesh_fn.getEdgeVertices(index)
            delta = points[first] - points[second]
            length = (delta.x * delta.x + delta.y * delta.y + delta.z * delta.z) ** 0.5
            adjacency[first].append((second, length))
            adjacency[second].append((first, length))
        return adjacency

    @flag_aliases(idx="index")
    def edge(self, index):
        """番号から Edge を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。

        Returns:
            Edge: シーンを参照する単体ラッパー。
        """
        return Edge(self, index)

    def edges(self, indices=None):
        """指定した Edge 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Edges: 重複を除いたコレクション。
        """
        return Edges(self, indices)

    @flag_aliases(idx="index")
    def face(self, index):
        """番号から Face を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。

        Returns:
            Face: シーンを参照する単体ラッパー。
        """
        return Face(self, index)

    def faces(self, indices=None):
        """指定した Face 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Faces: 重複を除いたコレクション。
        """
        return Faces(self, indices)

    @flag_aliases(idx="index")
    def uv(self, index):
        """番号から UV を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。

        Returns:
            UV: シーンを参照する単体ラッパー。
        """
        return UV(self, index)

    def uvs(self, indices=None):
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
        return self.meshFn().numUVs()

    @_getter_alias(getVertices)
    def vertices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVertices(*args, **kwargs)

    @_getter_alias(getShadingEngines)
    def shadingEngines(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShadingEngines(*args, **kwargs)

    @_getter_alias(getFaceShadingEngines)
    def faceShadingEngines(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFaceShadingEngines(*args, **kwargs)

    @_getter_alias(getNumVertices)
    def numVertices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNumVertices(*args, **kwargs)

    @_getter_alias(getNumPolygons)
    def numPolygons(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNumPolygons(*args, **kwargs)

    @_getter_alias(getNumEdges)
    def numEdges(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNumEdges(*args, **kwargs)

    @_getter_alias(getPoints)
    def points(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPoints(*args, **kwargs)

    @_getter_alias(getVertexNormals)
    def vertexNormals(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVertexNormals(*args, **kwargs)

    @_getter_alias(getVertexAdjacency)
    def vertexAdjacency(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVertexAdjacency(*args, **kwargs)

    @_getter_alias(getNumUVs)
    def numUVs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNumUVs(*args, **kwargs)

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
                raise ValueError("UV set does not exist: " + uv_set)
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

    def _check_reorder_supported(self, fn):
        """番号依存の外部接続や未対応のメッシュデータを変更前に拒否する。"""
        if self.mpath().isInstanced() or om2.MFnDependencyNode(self.mnode()).isFromReferencedFile:
            raise NotImplementedError("Instanced or referenced targets are not supported")
        if om2.MFnDependencyNode(self.mnode()).isLocked:
            raise RuntimeError("Mesh is locked")
        if self.getPlug("outMesh").mplug().isLocked:
            raise RuntimeError("Mesh output is locked")
        sets, members = fn.getConnectedSetsAndMembers(self.mpath().instanceNumber(), False)
        if any(not member.isNull() and not group.hasFn(om2.MFn.kShadingEngine)
               for group, member in zip(sets, members)):
            raise NotImplementedError("Component sets other than shading assignments are not supported")
        if self.getPlug("inMesh").mplug().isDestination:
            raise NotImplementedError("Target must have no input history")
        for name in ("outMesh", "worldMesh"):
            plug = self.getPlug(name).mplug()
            plugs = [plug.elementByLogicalIndex(i) for i in plug.getExistingArrayAttributeIndices()] if plug.isArray else [plug]
            if any(p.isSource for p in plugs):
                raise NotImplementedError("Target must not drive downstream geometry")
        creased = False
        for getter in (fn.getCreaseEdges, fn.getCreaseVertices):
            try:
                creased = creased or bool(getter()[0])
            except RuntimeError:
                # クリースデータ自体がない通常メッシュではMayaがkFailureを返す。
                pass
        if fn.getColorSetNames() or creased or fn.getHoles():
            raise NotImplementedError("Color sets, creases and polygon holes are not supported")
        if any(fn.hasBlindData(kind) for kind in (om2.MFn.kMeshVertComponent,
                                                  om2.MFn.kMeshEdgeComponent,
                                                  om2.MFn.kMeshPolygonComponent)):
            raise NotImplementedError("Mesh blind data is not supported")
        for name in ("inMesh", "cachedInMesh", "pnts"):
            plug = self.getPlug(name).mplug()
            writable(plug)
            if plug.isArray:
                for i in plug.getExistingArrayAttributeIndices():
                    item = plug.elementByLogicalIndex(i)
                    writable(item)
                    for j in range(item.numChildren()):
                        writable(item.child(j))
                        if not is_fast() and item.child(j).asFloat() != 0:
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
