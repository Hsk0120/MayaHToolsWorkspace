"""既存transformへ非破壊で操作用シェイプを追加する。"""

from maya import cmds

import math
import hlib
from hlib.decorator import undoTransaction


class ControlShape:
    """リグ構造に依存しない表示形状の作成。"""

    @staticmethod
    @undoTransaction("hrig.ControlShape.circle")
    def circle(target, radius=0.45, normal=(0, 0, 1), color=17, name=None):
        """ローカル原点へ円シェイプを追加し、既存TRS・形状を維持する。

        Args:
            target (str | Node): transformまたはjoint。
            radius (float): 現在の距離単位での半径。
            normal (Sequence[float]): ローカル法線。
            color (int): Mayaインデックス色、0〜31。
            name (str | None): シェイプ名。省略時はtarget名+Shape。

        Returns:
            tuple[Node]: 追加したNURBSシェイプ。
        """
        target = hlib.nodes.Node(target)
        if not isinstance(target, hlib.nodes.Transform):
            raise TypeError("Expected a transform")
        if (
            not math.isfinite(radius)
            or radius <= 0
            or type(color) is not int
            or not 0 <= color <= 31
        ):
            raise ValueError("Expected positive radius and color 0..31")
        if (
            len(normal) != 3
            or not all(math.isfinite(v) for v in normal)
            or sum(v * v for v in normal) <= 0
        ):
            raise ValueError("Expected nonzero finite normal")
        temporary = hlib.createNurbs(
            type="circle", normal=normal, radius=radius, constructionHistory=False
        ).getTransform()
        shapes = []
        try:
            for shape in [
                hlib.getNode(value)
                for value in (cmds.listRelatives(temporary, shapes=True, fullPath=True) or [])
            ] or []:
                shape = hlib.nodes.Node(
                    [
                        hlib.getNode(value)
                        for value in (
                            cmds.parent(shape, target.getFullName(), shape=True, relative=True) or []
                        )
                    ][0]
                )
                shape.rename(name or target.getName() + "Shape")
                shapes.append(shape)
        finally:
            hlib.delete(temporary)
        target.getPlug("overrideEnabled").set(True)
        target.getPlug("overrideColor").set(color)
        return tuple(shapes)

    @staticmethod
    @undoTransaction("hrig.ControlShape.replaceCurves")
    def replaceCurves(target, points, knots, degree=1, name="ctrlCurve"):
        """transformを保持し、その配下のNURBSカーブを指定点列へ差し替える。

        Args:
            target (str | Transform): 差し替えるtransform。
            points (Sequence[Sequence[float]]): 現在の距離単位によるCV座標。
            knots (Sequence[float]): Maya標準のノット列。
            degree (int): カーブ次数。
            name (str): 一時カーブの名前の接頭辞。

        Returns:
            Transform: 形状を差し替えた既存transform。他種のシェイプは保持する。
        """
        target = hlib.nodes.Transform(target)
        old_shapes = [hlib.nodes.Node(shape) for shape in
                      (cmds.listRelatives(target.getFullName(), shapes=True, fullPath=True) or [])]
        old_shapes = [shape for shape in old_shapes if shape.getType() == "nurbsCurve"]
        temporary = hlib.createCurve(degree=degree, point=points, knot=knots, name=name + "__tmp")
        new_shapes = [hlib.nodes.Node(shape) for shape in
                      (cmds.listRelatives(temporary.getFullName(), shapes=True, fullPath=True) or [])]
        for shape in old_shapes:
            shape.delete()
        for shape in new_shapes:
            cmds.parent(shape.getFullName(), target.getFullName(), shape=True, relative=True)
        temporary.delete()
        return target
