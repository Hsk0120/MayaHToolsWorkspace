"""Maya の標準コンストレイントとターゲット情報を扱う。"""

import maya.cmds as cmds

from ..core.registry import node_wrapper
from .node import Node


class Constraint(Node):
    """標準コンストレイントのターゲットとウェイトを取得する共通ラッパー。"""

    __hlib_public__ = True

    def targets(self):
        """ターゲットを Maya の問い合わせ順に取得する。

        Returns:
            list[Node]: ターゲットのラッパー。登録がなければ空リスト。
        """
        names = getattr(cmds, self.type())(self.full_name, query=True, targetList=True) or []
        return [Node(name) for name in names]

    def weight_aliases(self):
        """各ターゲットのウェイト属性の別名を取得する。

        Returns:
            list[str]: targets() と同じ順序の属性別名。
        """
        return getattr(cmds, self.type())(self.full_name, query=True, weightAliasList=True) or []

    def weight_plugs(self):
        """ターゲットのウェイトプラグを取得する。

        Returns:
            list[Plug]: targets() と同じ順序のプラグ。set() で値を変更できる。
        """
        return [self.plug(alias) for alias in self.weight_aliases()]

    def weights(self):
        """ターゲットの現在のウェイトを取得する。

        Returns:
            list[float]: targets() と同じ順序の値。正規化は行わない。
        """
        return [plug.get() for plug in self.weight_plugs()]


@node_wrapper("parentConstraint")
class ParentConstraint(Constraint):
    """位置と回転を拘束する parentConstraint ラッパー。"""


@node_wrapper("pointConstraint")
class PointConstraint(Constraint):
    """位置を拘束する pointConstraint ラッパー。"""


@node_wrapper("orientConstraint")
class OrientConstraint(Constraint):
    """回転を拘束する orientConstraint ラッパー。"""


@node_wrapper("scaleConstraint")
class ScaleConstraint(Constraint):
    """スケールを拘束する scaleConstraint ラッパー。"""


@node_wrapper("aimConstraint")
class AimConstraint(Constraint):
    """指定ターゲットへ向ける aimConstraint ラッパー。"""


@node_wrapper("poleVectorConstraint")
class PoleVectorConstraint(Constraint):
    """RP IK ハンドルの極ベクトルを拘束するラッパー。"""


@node_wrapper("geometryConstraint")
class GeometryConstraint(Constraint):
    """ターゲット表面上の位置へ拘束するラッパー。"""


@node_wrapper("normalConstraint")
class NormalConstraint(Constraint):
    """ターゲット表面の法線方向へ向けるラッパー。"""


@node_wrapper("tangentConstraint")
class TangentConstraint(Constraint):
    """NURBS カーブの接線方向へ向けるラッパー。"""


@node_wrapper("pointOnPolyConstraint")
class PointOnPolyConstraint(Constraint):
    """ポリゴン表面上の点へ拘束するラッパー。"""
