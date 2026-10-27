"""Maya のメッシュシェイプを扱う。"""

import math
from collections import Counter, defaultdict

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..core.fastWrite import writable
from ..decorator import undoTransaction
from ..maths.vector import Vector, _vector_of
from ..util import _world_space
from ..util import _ArgumentError, _UNSET
from .shape import Shape


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
            worldSpace (bool): 位置照合でTrueはworld、既定Falseは各Shapeのobject空間。UV照合では使わない。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Mesh: 自身。番号対応が既に同一なら再構築せず返し、再構築用の制限検査にも進まない。

        Raises:
            TypeError: 入力型・fast/worldSpaceが不正、または長短名を同時指定した場合。
            ValueError: 対応が曖昧/不完全、またはトポロジー/面の向きが一致しない場合。
            NotImplementedError: 再構築時に入出力履歴・インスタンス・参照・色セット・クリース等がある場合。
            RuntimeError: 再構築時にロック、または通常処理でUndoが無効の場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        from .node import Node
        if match not in ("uv", "position"):
            raise ValueError("match must be uv or position")
        if type(worldSpace) is not bool:
            raise TypeError("worldSpace must be bool")
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("tolerance must be finite and nonnegative")
        if match == "uv" and (not isinstance(uvSet, str) or not uvSet):
            raise ValueError("uvSet must be a nonempty name")
        reference = Node(Node._input_name(reference))
        if reference.mnode().hasFn(om2.MFn.kTransform):
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
        self._check_reorder_supported(target, fast=fast)
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

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False, ws=_UNSET):
        """頂点座標を指定空間の中心で反転する。Transformとトポロジーは変更しない。

        共有Shapeの全インスタンスへ影響する。複製・結合・片側からの対称化・法線反転は行わない。
        奇数軸の反転で面の向きが変わる場合、必要な法線処理は別途行う。

        Args:
            axis (str): 重複しないx/y/zの組合せ。大文字も可。
            worldSpace (bool): Trueは保持パスのworld、既定FalseはShapeのobject空間。短縮名ws。
            pivot (Iterable[float]): 指定空間の反転中心XYZ（cm）。既定は原点で、Transformのピボットとは独立。
            indices (Iterable[int] | None): 頂点番号。Noneは全頂点、空列は変更なし。重複は1回だけ処理する。
            fast (bool): TrueはUndoなし。既定FalseはUndo有効時に1回で戻せる通常更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Mesh: 自身。頂点番号・面の接続と頂点順は保持する。

        Raises:
            ValueError: 軸・空間・中心が不正、またはworld変換が数値的にほぼ特異な場合。
            TypeError: 番号型・fastが不正、または長短名を同時指定した場合。
            IndexError: 頂点番号が負または範囲外の場合。
            RuntimeError: Mayaが形状の取得・更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeを編集する場合。

        Note:
            途中失敗で完了済みの変更は自動で戻さない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        ws = _world_space(worldSpace)
        self.getVertices(indices).mirror(axis=axis, ws=ws, pivot=pivot, fast=fast)
        return self

    def getVertex(self, index=_UNSET, *, idx=_UNSET):
        """頂点番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの頂点番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Vertex: シーン上の頂点を参照するラッパー。

        Raises:
            IndexError: 頂点番号が範囲外の場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
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
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            om2.MPointArray: 頂点番号順の位置。距離は Maya API の内部単位。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self._geometry_fn().getPoints(space)

    def getVertexNormals(self, worldSpace=_UNSET, angleWeighted=False, *, ws=_UNSET):
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            angleWeighted (bool): True の場合は隣接面の角度で重み付けした法線を取得する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[Vector]: 頂点番号順の平均法線。angleWeighted=False では
                角度による重み付けを行わない。MFnMesh.getVertexNormals() を使用する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        # MFloatVectorはom2の多重定義の解決を通さず、成分を写して同じ値のVectorにする。
        return [_vector_of(Vector, value) for value in self._geometry_fn().getVertexNormals(angleWeighted, space)]

    def getVertexAdjacency(self, worldSpace=_UNSET, *, ws=_UNSET):
        """頂点IDごとの隣接頂点とエッジ長を照会する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[list[tuple[int, float]]]: 頂点ID順の隣接リスト。
            各要素は隣接頂点IDとcm単位の距離で、エッジID順に格納する。
            孤立頂点は空リスト、重複エッジは別々に保持する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        points = self.getPoints(ws=worldSpace)
        adjacency = [[] for _ in points]
        mesh_fn = self._geometry_fn()
        for index in range(mesh_fn.numEdges):
            first, second = mesh_fn.getEdgeVertices(index)
            delta = points[first] - points[second]
            length = (delta.x * delta.x + delta.y * delta.y + delta.z * delta.z) ** 0.5
            adjacency[first].append((second, length))
            adjacency[second].append((first, length))
        return adjacency

    def getEdge(self, index=_UNSET, *, idx=_UNSET):
        """番号から Edge を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Edge: シーンを参照する単体ラッパー。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        return Edge(self, index)

    def getEdges(self, indices=None):
        """指定した Edge 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Edges: 重複を除いたコレクション。
        """
        return Edges(self, indices)

    def getFace(self, index=_UNSET, *, idx=_UNSET):
        """番号から Face を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Face: シーンを参照する単体ラッパー。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        return Face(self, index)

    def getFaces(self, indices=None):
        """指定した Face 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Faces: 重複を除いたコレクション。
        """
        return Faces(self, indices)

    def getUV(self, index=_UNSET, *, idx=_UNSET):
        """番号から UV を取得する。

        Args:
            index (int): ゼロ始まりの番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            UV: シーンを参照する単体ラッパー。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
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

    def _check_reorder_supported(self, fn, *, fast=False):
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
