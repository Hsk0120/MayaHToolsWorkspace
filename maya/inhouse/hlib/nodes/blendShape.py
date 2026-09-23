"""Maya の blendShape を扱う。"""

import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from .._core.coerce import to_name
from .._core.registry import node_wrapper
from ..decorators.undo import undoable
from .node import Node


@node_wrapper("blendShape")
class BlendShape(Node):
    """Maya の blendShape ラッパー。ターゲットの追加とウェイト操作を提供する。"""

    def targets(self):
        """ターゲット名を weight 配列の並び順で取得する。

        Returns:
            list[str]: ターゲットのエイリアス名(既定ではターゲット shape の
                トランスフォーム名)。
        """
        return [alias for alias, _ in self.aliases()]

    def weight_plugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: targets() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [plug for _, plug in self.aliases()]

    def weights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: targets() と同じ順序の値。
        """
        return [plug.get() for plug in self.weight_plugs()]

    def geometry(self):
        """変形対象の base geometry shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mobject()).getOutputGeometry()]

    @undoable("hlibBlendShapeAddTarget")
    def add_target(self, target, base=None, weight_index=None, full_weight=1.0):
        """ターゲットを追加する。

        Args:
            target (Node | str): 追加するターゲット shape またはその transform。
            base (Node | str | None): 変形対象の base geometry。省略時は
                geometry() の先頭を使う。
            weight_index (int | None): 使用する weight 配列インデックス。省略時は
                空いている最小のインデックス(``plug("weight").next_available()``)
                を自動で使う。
            full_weight (float): このターゲットが完全に効いた状態(既定 1.0)の
                weight 値。

        Returns:
            Plug: 追加したターゲットの weight 要素プラグ。

        Raises:
            RuntimeError: base を省略し、かつ base geometry を特定できない場合。
        """
        target_name = to_name(target)
        if base is None:
            geometries = self.geometry()
            if not geometries:
                raise RuntimeError("Cannot determine the base geometry for this blendShape")
            base_name = geometries[0].full_name
        else:
            base_name = to_name(base)
        if weight_index is None:
            weight_index = self.plug("weight").next_available()
        cmds.blendShape(
            self.name(), edit=True,
            target=(base_name, weight_index, target_name, full_weight),
        )
        return self.plug("weight").element(weight_index)
