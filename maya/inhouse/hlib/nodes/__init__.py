"""ノードラッパーを検出して公開する。"""

from typing import TYPE_CHECKING

from .._core.discovery import discover_node_package
from .node import Node
from .shape import Shape
from .transform import Transform

# Node/Shape/Transform は他モジュールからの型参照（isinstance 判定や基底クラスと
# しての利用）が多いため明示 import する。joint/mesh/camera/skinCluster などの
# 具象 wrapper は明示 import せず、discover_node_package の pkgutil スキャンだけで
# 検出・公開する（新規ファイル追加時に __init__.py の編集が不要という設計のため）。
for _export_name in globals().get("_discovered_exports", {}):
    globals().pop(_export_name, None)
_discovered_wrappers, _discovered_exports = discover_node_package(__name__)
globals().update(_discovered_exports)

# 静的解析(Pylance/pyright)向けの宣言。実行時には評価されず、上記の動的公開が実体。
# 公開名の一覧との一致は test_typing_exports.py が検証する。
if TYPE_CHECKING:
    from .multiplyDivide import MultiplyDivide
    from .vectorProduct import VectorProduct
    from .angleBetween import AngleBetween
    from .addDoubleLinear import AddDoubleLinear
    from .multDoubleLinear import MultDoubleLinear
    from .addDL import AddDL
    from .multDL import MultDL
    from .reverse import Reverse
    from .clamp import Clamp
    from .setRange import SetRange
    from .condition import Condition
    from .unitConversion import UnitConversion
    from .THdependNode import THDependNode
    from .abstractBaseCreate import AbstractBaseCreate
    from .inverseMatrix import InverseMatrix
    from .pickMatrix import PickMatrix
    from .composeMatrix import ComposeMatrix
    from .fourByFourMatrix import FourByFourMatrix
    from .plusMinusAverage import PlusMinusAverage
    from .remapValue import RemapValue
    from .blendMatrix import BlendMatrix
    from .aimMatrix import AimMatrix
    from .pairBlend import PairBlend
    from .curveInfo import CurveInfo
    from .pointOnCurveInfo import PointOnCurveInfo
    from .pointOnSurfaceInfo import PointOnSurfaceInfo
    from .shadingDependNode import ShadingDependNode
    from .paintableShadingDependNode import PaintableShadingDependNode
    from .lambert import Lambert
    from .reflect import Reflect
    from .blinn import Blinn
    from .phong import Phong
    from .phongE import PhongE
    from .standardSurface import StandardSurface
    from .surfaceShader import SurfaceShader
    from .texture2d import Texture2d
    from .file import File
    from .place2dTexture import Place2dTexture
    from .place3dTexture import Place3dTexture
    from .shadingEngine import ShadingEngine
    from .dagNode import DagNode, DagNodes
    from .node import Nodes
    from .transform import Transforms
    from .HIKCharacterNode import HIKCharacterNode
    from .HIKSolverNode import HIKSolverNode
    from .HIKRetargeterNode import HIKRetargeterNode
    from .HIKControlSetNode import HIKControlSetNode
    from .HIKSkeletonGeneratorNode import HIKSkeletonGeneratorNode
    from .aimConstraint import AimConstraint
    from .animCurve import AnimCurve
    from .animCurveTA import AnimCurveTA
    from .animCurveTL import AnimCurveTL
    from .animCurveTT import AnimCurveTT
    from .animCurveTU import AnimCurveTU
    from .animCurveUA import AnimCurveUA
    from .animCurveUL import AnimCurveUL
    from .animCurveUT import AnimCurveUT
    from .animCurveUU import AnimCurveUU
    from .blendColors import BlendColors
    from .blendShape import BlendShape
    from .blendWeighted import BlendWeighted
    from .camera import Camera
    from .cluster import Cluster
    from .constraint import Constraint
    from .container import Container
    from .dagContainer import DagContainer
    from .dagPose import DagPose
    from .decomposeMatrix import DecomposeMatrix
    from .displayLayer import DisplayLayer
    from .distanceBetween import DistanceBetween
    from .geometryConstraint import GeometryConstraint
    from .ikHandle import IkHandle
    from .joint import Joint
    from .joint import Joints
    from .locator import Locator
    from .mesh import Mesh
    from .multMatrix import MultMatrix
    from .normalConstraint import NormalConstraint
    from .nurbsCurve import NurbsCurve
    from .nurbsSurface import NurbsSurface
    from .objectSet import ObjectSet
    from .orientConstraint import OrientConstraint
    from .parentConstraint import ParentConstraint
    from .pointConstraint import PointConstraint
    from .pointOnPolyConstraint import PointOnPolyConstraint
    from .poleVectorConstraint import PoleVectorConstraint
    from .reference import Reference
    from .scaleConstraint import ScaleConstraint
    from .skinCluster import SkinCluster
    from .skinCluster import SkinClusters
    from .tangentConstraint import TangentConstraint

__all__ = [
    "Node",
    "Shape",
    "Transform",
    *sorted(_discovered_exports),
]
