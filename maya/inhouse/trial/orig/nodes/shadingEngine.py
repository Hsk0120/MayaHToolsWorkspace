"""マテリアル接続と形状への割り当てを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import _edit_context
from .node import Node
from .objectSet import ObjectSet


class ShadingEngine(ObjectSet):
    """Mayaのレンダー用セット。表面・ボリューム・変位シェーダーを保持する。"""

    def getShaderPlug(self, kind="surface"):
        """シェーダー接続元を取得する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            Plug | None: 接続元の出力Plug。未接続ならNone。
        """
        return self.getPlug(self._shader_attribute(kind)).getSource(scn=False)

    def getShader(self, kind="surface"):
        """接続元のシェーダーノードを取得する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            Node | None: 型付きノード。未接続ならNone。
        """
        plug = self.getShaderPlug(kind)
        return None if plug is None else plug.getNode()

    def setShader(self, shader, kind="surface", output=None, *, fast=False):
        """指定シェーダーの出力へ接続を置き換える。

        Args:
            shader (Node | Plug | str): ノードまたは出力Plug。
            kind (str): surface/volume/displacement。
            output (str | None): ノード指定時の出力名。既定はoutColor、変位はdisplacement。
            fast (bool): TrueはOpenMaya直接接続でUndoなし。

        Returns:
            ShadingEngine: 自身。

        Raises:
            ValueError: 種別が不正な場合。
            RuntimeError: Mayaが接続を拒否した場合。
        """
        with _edit_context("mlibShadingEngineSetShader", fast):
            # plugs は nodes を参照するため、循環importを避けて呼出し時に取得する。
            from ..plugs.plug import Plug
            target = self.getPlug(self._shader_attribute(kind))
            if isinstance(shader, Plug) or isinstance(shader, str) and "." in shader:
                source = Plug._resolve_input(shader)
            else:
                source = Node._resolve_input(shader).getPlug(output or ("displacement" if kind == "displacement" else "outColor"))
            source.connectTo(target, force=True, fast=fast)
            return self

    def assign(self, targets, *, fast=False):
        """形状またはフェースへ割り当て、既存の割り当てを置き換える。

        Args:
            targets (Node | Face | Faces | str | Iterable): 対象。選択に依存しない。
            fast (bool): Trueは単一インスタンスのポリゴン全体をOpenMayaで排他的に割り当てる。
                フェース単位・NURBS・子Transformを持つ階層は更新前に拒否する。

        Returns:
            ShadingEngine: 自身。空列では変更しない。

        Raises:
            RuntimeError: Mayaが割り当てを拒否した場合。
            NotImplementedError: fastでフェース・非ポリゴン・インスタンス・階層指定の場合。
        """
        with _edit_context("mlibShadingEngineAssign", fast):
            names = Object._input_names(targets)
            if names:
                if fast:
                    self._assign_meshes(names)
                else:
                    cmds.sets(names, edit=True, forceElement=self.getFullName())
            return self

    def getMembers(self):
        """割り当て先を型付き参照で取得する。

        Returns:
            list[Node | Face]: オブジェクトまたは単体フェース。インスタンスパスを保持する。
        """
        selection = om2.MFnSet(self.mnode()).getMembers(False)
        result = []
        for index in range(selection.length()):
            path, component = selection.getComponent(index)
            # 選択リストから取得したばかりのパスなので、入力の再解決を省いてラッパーにする。
            node = Node._wrap_dag_path(path)
            if component.hasFn(om2.MFn.kMeshPolygonComponent):
                fn = om2.MFnSingleIndexedComponent(component)
                indices = range(om2.MFnMesh(path).numPolygons) if fn.isComplete else fn.getElements()
                result.extend(node.getFace(value) for value in indices)
            else:
                result.append(node)
        return result

    def _assign_meshes(self, names):
        """共有パーティション内の既存割り当てを除去してポリゴン全体へ適用する。

        Args:
            names (Iterable[str]): 解決済みのポリゴンまたは末端Transform。

        Raises:
            NotImplementedError: フェース・非ポリゴン・インスタンス・階層指定の場合。
            RuntimeError: 割り当て対象または既存セットを安全に更新できない場合。
        """
        # nodes パッケージ内の読込み順に依存しないよう、Transform は呼出し時に取得する。
        from .transform import Transform

        target_fn = self._editable_set()
        meshes, seen = [], set()
        for name in names:
            if "." in name or "," in name:
                raise NotImplementedError("fast assignment supports whole polygon meshes only")
            node = Node(name)
            if isinstance(node, Transform):
                if node.getChildren():
                    raise NotImplementedError("fast assignment does not support transform hierarchies")
                shapes = node.getShapes()
            else:
                shapes = [node]
            if not shapes or any(not shape.mnode().hasFn(om2.MFn.kMesh) for shape in shapes):
                raise NotImplementedError("fast assignment supports polygon meshes only")
            for shape in shapes:
                if shape.mpath().isInstanced():
                    raise NotImplementedError("fast assignment does not support instanced meshes")
                fn = shape.mfn()
                if fn.isLocked or fn.isFromReferencedFile:
                    raise RuntimeError("Cannot edit a locked or referenced mesh membership")
                token = om2.MObjectHandle(shape.mnode()).hashCode()
                if token not in seen:
                    seen.add(token)
                    meshes.append(shape)

        def partitions(fn):
            """セットが所属するパーティションの識別子を取得する。"""
            return {om2.MObjectHandle(plug.node()).hashCode()
                    for plug in fn.findPlug("partition", False).connectedTo(False, True)}

        target_partitions = partitions(target_fn)
        removals = {}
        for mesh in meshes:
            shaders, _ = om2.MFnMesh(mesh.mpath()).getConnectedShaders(mesh.mpath().instanceNumber())
            for shader in shaders:
                fn = om2.MFnSet(shader)
                if shader != self.mnode() and not (partitions(fn) & target_partitions):
                    continue
                if fn.isLocked or fn.isFromReferencedFile:
                    raise RuntimeError("Cannot remove a locked or referenced shading membership")
                membership = fn.findPlug("dagSetMembers", False)
                if membership.isLocked or any(
                        membership.elementByLogicalIndex(i).isLocked
                        for i in membership.getExistingArrayAttributeIndices()):
                    raise RuntimeError("Shading membership is locked")
                token = om2.MObjectHandle(shader).hashCode()
                if token not in removals:
                    removals[token] = (fn, om2.MSelectionList())
                existing = fn.getMembers(False)
                for index in range(existing.length()):
                    path, component = existing.getComponent(index)
                    if path == mesh.mpath():
                        removals[token][1].add((path, component))
        for fn, selection in removals.values():
            if selection.length():
                fn.removeMembers(selection)
        assignment = om2.MSelectionList()
        for mesh in meshes:
            assignment.add(mesh.mpath())
        target_fn.addMembers(assignment)

    @staticmethod
    def _shader_attribute(kind):
        """接続種別をMayaのアトリビュート名へ変換する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            str: 対応する接続先名。

        Raises:
            ValueError: 未対応の種別の場合。
        """
        if kind not in ("surface", "volume", "displacement"):
            raise ValueError("kind must be surface, volume, or displacement")
        return kind + "Shader"
