"""マテリアル接続と形状への割り当てを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import _edit_context, undoChunk
from .node import Node
from .objectSet import ObjectSet


class ShadingEngine(ObjectSet):
    """Mayaのレンダー用セット。表面・ボリューム・変位シェーダーを保持する。

    マテリアルの割り当ては、シェーダーを :meth:`setShader` で接続し、形状・フェースへ
    :meth:`assign` で割り当てる。

    .. code-block:: python

        import maya.cmds as cmds
        import mlib
        from mlib.nodes import ShadingEngine

        shader = mlib.createNode("lambert", name="red_MAT")
        shader.getPlug("color").set((1, 0, 0))
        engine = ShadingEngine(cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="red_SG"))
        engine.setShader(shader)        # shader.outColor -> red_SG.surfaceShader
        engine.assign(mlib.getNode("pCube1"))  # 形状全体。フェースは Face/Faces や "pCube1.f[0:3]"
    """

    def getShaderPlug(self, kind="surface"):
        """シェーダー接続元を取得する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            Plug | None: 接続元の出力Plug。未接続ならNone。
        """
        return self.getPlug(self._shader_attribute(kind)).getSource(skipConversionNodes=False)

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

        例えば ``engine.setShader(lambert)`` は ``lambert.outColor`` を ``surfaceShader`` へ接続する
        (既存の接続は置き換える)。形状への割り当ては :meth:`assign` で行う(クラスの説明の例を参照)。

        Args:
            shader (Node | Plug | str): ノードまたは出力Plug。
            kind (str): surface/volume/displacement。
            output (str | None): ノード指定時の出力名。既定はoutColor、変位はdisplacement。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

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

    def assign(self, targets):
        """形状またはフェースへ割り当て、既存の割り当てを置き換える。

        例えば ``engine.assign(mlib.getNode("pCube1"))`` は形状全体、``engine.assign("pCube1.f[0:3]")``
        はフェースだけへ割り当てる(``cmds.sets(forceElement=...)`` 相当)。シェーダーの接続は
        :meth:`setShader` で行う(クラスの説明の例を参照)。fast引数は持たない(OpenMayaの
        割り当ては ``cmds.sets`` より遅いため)。

        Args:
            targets (Node | Face | Faces | str | Iterable): 対象。選択に依存しない。

        Returns:
            ShadingEngine: 自身。空列では変更しない。

        Raises:
            RuntimeError: Mayaが割り当てを拒否した場合。
        """
        with undoChunk("mlibShadingEngineAssign"):
            names = Object._input_names(targets)
            if names:
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
