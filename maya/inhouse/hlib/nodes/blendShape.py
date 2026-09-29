"""Maya の blendShape を扱う。"""

import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from .._core.coerce import to_node_name
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from .node import Node


@node_wrapper("blendShape")
class BlendShape(Node):
    """Maya の blendShape ラッパー。ターゲットの追加とウェイト操作を提供する。"""

    def target_aliases(self):
        """ターゲット名を weight 配列の並び順で取得する。

        Returns:
            list[str]: ターゲットのエイリアス名(既定ではターゲット shape の
                トランスフォーム名)。
        """
        return [alias for alias, _ in self.aliases()]

    def weight_plugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: target_aliases() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [plug for _, plug in self.aliases()]

    def get_weights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: target_aliases() と同じ順序の値。
        """
        return [plug.get() for plug in self.weight_plugs()]

    def geometry(self):
        """変形対象の base geometry shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mobject()).getOutputGeometry()]

    @undo_chunk("hlibBlendShapeAddTarget")
    def add_target(self, target, base=None, weight_index=None, full_weight=1.0):
        """ターゲットを追加する。

        Args:
            target (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                追加するターゲット shape またはその transform。Plug・MPlug・
                ``"node.attribute"`` は所有ノード、Component は所有シェイプとして扱う。
            base (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug | None):
                変形対象の base geometry(target と同じ規則で所有ノードへ解決する)。
                省略時は geometry() の先頭を使う。
            weight_index (int | None): 使用する weight 配列インデックス。省略時は
                空いている最小のインデックス(``plug("weight").next_available_index()``)
                を自動で使う。
            full_weight (float): このターゲットが完全に効いた状態(既定 1.0)の
                weight 値。

        Returns:
            Plug: 追加したターゲットの weight 要素プラグ。

        Raises:
            RuntimeError: base を省略し、かつ base geometry を特定できない場合。
                target・base の名前を解決できない場合。
            TypeError: target・base が対応しない型の場合。
            ValueError: target・base が空文字列、または削除済みの対象の場合。
        """
        target_name = to_node_name(target)
        if base is None:
            geometries = self.geometry()
            if not geometries:
                raise RuntimeError("Cannot determine the base geometry for this blendShape")
            base_name = geometries[0].full_name()
        else:
            base_name = to_node_name(base)
        if weight_index is None:
            weight_index = self.plug("weight").next_available_index()
        cmds.blendShape(
            self.name(), edit=True,
            target=(base_name, weight_index, target_name, full_weight),
        )
        return self.plug("weight").element(weight_index)
