"""マテリアル接続と形状への割り当てを扱う。"""
import maya.cmds as cmds
from .._core.registry import node_wrapper
from .._core.coerce import to_names, to_node, to_plug
from ..decorators.undo import undo_chunk
from .objectSet import ObjectSet


@node_wrapper("shadingEngine")
class ShadingEngine(ObjectSet):
    """Mayaのレンダー用セット。表面・ボリューム・変位シェーダーを保持する。"""

    def get_shader_plug(self, kind="surface"):
        """シェーダー接続元を取得する。

        Args:
            kind (str): surface/volume/displacement。
        Returns:
            Plug | None: 接続元の出力Plug。未接続ならNone。
        """
        return self.plug(self._shader_attribute(kind)).source()

    def get_shader(self, kind="surface"):
        """接続元のシェーダーノードを取得する。

        Args:
            kind (str): surface/volume/displacement。
        Returns:
            Node | None: 型付きノード。未接続ならNone。
        """
        plug = self.get_shader_plug(kind)
        return None if plug is None else plug.node

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

    @undo_chunk("hlibShadingEngineSetShader")
    def set_shader(self, shader, kind="surface", output=None):
        """指定シェーダーの出力へ接続を置き換える。

        Args:
            shader (Node | Plug | str): ノードまたは出力Plug。
            kind (str): surface/volume/displacement。
            output (str | None): ノード指定時の出力名。既定はoutColor、変位はdisplacement。
        Returns:
            ShadingEngine: 自身。
        Raises:
            ValueError: 種別が不正な場合。
            RuntimeError: Mayaが接続を拒否した場合。
        """
        from ..plugs import Plug
        target = self.plug(self._shader_attribute(kind))
        if isinstance(shader, Plug) or isinstance(shader, str) and "." in shader:
            source = to_plug(shader)
        else:
            source = to_node(shader).plug(output or ("displacement" if kind == "displacement" else "outColor"))
        source.connect(target, force=True)
        return self

    @undo_chunk("hlibShadingEngineAssign")
    def assign(self, targets):
        """形状またはフェースへ割り当て、既存の割り当てを置き換える。

        Args:
            targets (Node | Face | Faces | str | Iterable): 対象。選択に依存しない。
        Returns:
            ShadingEngine: 自身。空列では変更しない。
        Raises:
            RuntimeError: Mayaが割り当てを拒否した場合。
        """
        names = to_names(targets)
        if names:
            cmds.sets(names, edit=True, forceElement=self.full_name())
        return self

    def members(self):
        """割り当て先を型付き参照で取得する。

        Returns:
            list[Node | Face]: オブジェクトまたは単体フェース。インスタンスパスを保持する。
        """
        from .node import Node
        names = cmds.sets(self.full_name(), query=True) or []
        result = []
        for name in cmds.ls(names, long=True, flatten=True) or []:
            if ".f[" in name:
                path, index = name.rsplit(".f[", 1)
                mesh = Node(path)
                if not mesh.is_type("mesh"):
                    mesh = mesh.shape()
                result.append(mesh.face(int(index[:-1])))
            else:
                result.append(Node(name))
        return result
