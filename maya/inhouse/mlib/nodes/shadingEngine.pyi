# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""マテリアル接続と形状への割り当てを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import Object
from ..decorator import _edit_context, undoChunk
from .node import Node
from .objectSet import ObjectSet
from typing import Iterable
from mlib.components.face import Face
from mlib.components.face import Faces
from mlib.plugs.plug import Plug



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
    def getShaderPlug(self, kind: str = ...) -> Plug | None:
        """シェーダー接続元を取得する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            Plug | None: 接続元の出力Plug。未接続ならNone。
        """
        ...
    def getShader(self, kind: str = ...) -> Node | None:
        """接続元のシェーダーノードを取得する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            Node | None: 型付きノード。未接続ならNone。
        """
        ...
    def setShader(self, shader: Node | Plug | str, kind: str = ..., output: str | None = ..., *, fast: bool = ...) -> ShadingEngine:
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
        ...
    def assign(self, targets: Node | Face | Faces | str | Iterable) -> ShadingEngine:
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
        ...
    def getMembers(self) -> list[Node | Face]:
        """割り当て先を型付き参照で取得する。

        Returns:
            list[Node | Face]: オブジェクトまたは単体フェース。インスタンスパスを保持する。
        """
        ...
    @staticmethod
    def _shader_attribute(kind: str) -> str:
        """接続種別をMayaのアトリビュート名へ変換する。

        Args:
            kind (str): surface/volume/displacement。

        Returns:
            str: 対応する接続先名。

        Raises:
            ValueError: 未対応の種別の場合。
        """
        ...
