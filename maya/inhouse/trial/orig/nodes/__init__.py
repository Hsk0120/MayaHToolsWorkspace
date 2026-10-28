"""ラッパークラスを明示公開し、Mayaの型との対応を宣言する。

手書きクラスは通常の import と ``__all__`` で公開し、``_WRAPPER_CLASSES`` で Maya の
nodeType 名との対応を明示する。登録の無い Maya の nodeType は、取得時(``mlib.ls``・
``mlib.getNode``・``Node(name)``)に Maya の継承チェーン上で最も近い登録クラスを親とする
クラスを自動生成して包む(クラス名は型名の先頭を大文字にしたもの。例: ``pointLight`` →
``PointLight``)。生成クラスはこのモジュールの属性 ``mlib.nodes.<TypeName>`` でも取得でき、
Maya が認識しない型名(プラグイン未ロード等)は ``AttributeError`` になる。

生成クラスは ``__all__`` に入れず、Sphinx にも載らない。登録クラスと生成対象の間にある
抽象型(geometryFilter・containerBase・entity など)のクラスは生成しないため、
``isinstance`` は Maya の継承を表さない。継承の判定は ``Node.isType()`` を使う。
生成クラスは登録表の変更・プラグインのロード/アンロード(``mlib.common.Plugin`` 経由)・
``mlib.reload()`` で作り直されるため、保持したクラス参照は取り直す。
"""

# reloadはモジュール辞書を保持するため、前回の公開名を取り除く。
for _name in globals().get("__all__", ()):
    globals().pop(_name, None)

# 旧初期化状態を、読み込み済みセッションに残さない。
for _name in ("_discovered_wrappers", "_discovered_exports",
              "discover_node_package", "discover_plug_package", "TYPE_CHECKING"):
    globals().pop(_name, None)

from ..core.registry import _node_type_exists
from .node import Node, Nodes
from .shape import Shape
from .transform import Transform, Transforms
from .HIKCharacterNode import HIKCharacterNode
from .HIKControlSetNode import HIKControlSetNode
from .HIKRetargeterNode import HIKRetargeterNode
from .HIKSkeletonGeneratorNode import HIKSkeletonGeneratorNode
from .HIKSolverNode import HIKSolverNode
from .THdependNode import THDependNode
from .abstractBaseCreate import AbstractBaseCreate
from .addDL import AddDL
from .addDoubleLinear import AddDoubleLinear
from .aimConstraint import AimConstraint
from .aimMatrix import AimMatrix
from .angleBetween import AngleBetween
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
from .blendMatrix import BlendMatrix
from .blendShape import BlendShape
from .blendWeighted import BlendWeighted
from .blinn import Blinn
from .camera import Camera
from .clamp import Clamp
from .cluster import Cluster
from .composeMatrix import ComposeMatrix
from .condition import Condition
from .constraint import Constraint
from .container import Container
from .curveInfo import CurveInfo
from .dagContainer import DagContainer
from .dagNode import DagNode, DagNodes
from .dagPose import DagPose
from .decomposeMatrix import DecomposeMatrix
from .displayLayer import DisplayLayer
from .distanceBetween import DistanceBetween
from .file import File
from .fourByFourMatrix import FourByFourMatrix
from .geometryConstraint import GeometryConstraint
from .ikHandle import IkHandle
from .inverseMatrix import InverseMatrix
from .joint import Joint, Joints
from .lambert import Lambert
from .locator import Locator
from .mesh import Mesh
from .multDL import MultDL
from .multDoubleLinear import MultDoubleLinear
from .multMatrix import MultMatrix
from .multiplyDivide import MultiplyDivide
from .normalConstraint import NormalConstraint
from .nurbsCurve import NurbsCurve
from .nurbsSurface import NurbsSurface
from .objectSet import ObjectSet
from .orientConstraint import OrientConstraint
from .paintableShadingDependNode import PaintableShadingDependNode
from .pairBlend import PairBlend
from .parentConstraint import ParentConstraint
from .phong import Phong
from .phongE import PhongE
from .pickMatrix import PickMatrix
from .place2dTexture import Place2dTexture
from .place3dTexture import Place3dTexture
from .plusMinusAverage import PlusMinusAverage
from .pointConstraint import PointConstraint
from .pointOnCurveInfo import PointOnCurveInfo
from .pointOnPolyConstraint import PointOnPolyConstraint
from .pointOnSurfaceInfo import PointOnSurfaceInfo
from .poleVectorConstraint import PoleVectorConstraint
from .reference import Reference
from .reflect import Reflect
from .remapValue import RemapValue
from .reverse import Reverse
from .scaleConstraint import ScaleConstraint
from .setRange import SetRange
from .shadingDependNode import ShadingDependNode
from .shadingEngine import ShadingEngine
from .skinCluster import SkinCluster, SkinClusters
from .standardSurface import StandardSurface
from .surfaceShader import SurfaceShader
from .tangentConstraint import TangentConstraint
from .texture2d import Texture2d
from .unitConversion import UnitConversion
from .vectorProduct import VectorProduct

# 公開名と型対応は別の責務として明示する。
__all__ = [
    "AbstractBaseCreate",
    "AddDL",
    "AddDoubleLinear",
    "AimConstraint",
    "AimMatrix",
    "AngleBetween",
    "AnimCurve",
    "AnimCurveTA",
    "AnimCurveTL",
    "AnimCurveTT",
    "AnimCurveTU",
    "AnimCurveUA",
    "AnimCurveUL",
    "AnimCurveUT",
    "AnimCurveUU",
    "BlendColors",
    "BlendMatrix",
    "BlendShape",
    "BlendWeighted",
    "Blinn",
    "Camera",
    "Clamp",
    "Cluster",
    "ComposeMatrix",
    "Condition",
    "Constraint",
    "Container",
    "CurveInfo",
    "DagContainer",
    "DagNode",
    "DagNodes",
    "DagPose",
    "DecomposeMatrix",
    "DisplayLayer",
    "DistanceBetween",
    "File",
    "FourByFourMatrix",
    "GeometryConstraint",
    "HIKCharacterNode",
    "HIKControlSetNode",
    "HIKRetargeterNode",
    "HIKSkeletonGeneratorNode",
    "HIKSolverNode",
    "IkHandle",
    "InverseMatrix",
    "Joint",
    "Joints",
    "Lambert",
    "Locator",
    "Mesh",
    "MultDL",
    "MultDoubleLinear",
    "MultMatrix",
    "MultiplyDivide",
    "Node",
    "Nodes",
    "NormalConstraint",
    "NurbsCurve",
    "NurbsSurface",
    "ObjectSet",
    "OrientConstraint",
    "PaintableShadingDependNode",
    "PairBlend",
    "ParentConstraint",
    "Phong",
    "PhongE",
    "PickMatrix",
    "Place2dTexture",
    "Place3dTexture",
    "PlusMinusAverage",
    "PointConstraint",
    "PointOnCurveInfo",
    "PointOnPolyConstraint",
    "PointOnSurfaceInfo",
    "PoleVectorConstraint",
    "Reference",
    "Reflect",
    "RemapValue",
    "Reverse",
    "ScaleConstraint",
    "SetRange",
    "ShadingDependNode",
    "ShadingEngine",
    "Shape",
    "SkinCluster",
    "SkinClusters",
    "StandardSurface",
    "SurfaceShader",
    "THDependNode",
    "TangentConstraint",
    "Texture2d",
    "Transform",
    "Transforms",
    "UnitConversion",
    "VectorProduct",
]

_WRAPPER_CLASSES = {
    "HIKCharacterNode": HIKCharacterNode,
    "HIKControlSetNode": HIKControlSetNode,
    "HIKRetargeterNode": HIKRetargeterNode,
    "HIKSkeletonGeneratorNode": HIKSkeletonGeneratorNode,
    "HIKSolverNode": HIKSolverNode,
    "THdependNode": THDependNode,
    "abstractBaseCreate": AbstractBaseCreate,
    "addDL": AddDL,
    "addDoubleLinear": AddDoubleLinear,
    "aimConstraint": AimConstraint,
    "aimMatrix": AimMatrix,
    "angleBetween": AngleBetween,
    "animCurve": AnimCurve,
    "animCurveTA": AnimCurveTA,
    "animCurveTL": AnimCurveTL,
    "animCurveTT": AnimCurveTT,
    "animCurveTU": AnimCurveTU,
    "animCurveUA": AnimCurveUA,
    "animCurveUL": AnimCurveUL,
    "animCurveUT": AnimCurveUT,
    "animCurveUU": AnimCurveUU,
    "blendColors": BlendColors,
    "blendMatrix": BlendMatrix,
    "blendShape": BlendShape,
    "blendWeighted": BlendWeighted,
    "blinn": Blinn,
    "camera": Camera,
    "clamp": Clamp,
    "cluster": Cluster,
    "composeMatrix": ComposeMatrix,
    "condition": Condition,
    "constraint": Constraint,
    "container": Container,
    "curveInfo": CurveInfo,
    "dagContainer": DagContainer,
    "dagNode": DagNode,
    "dagPose": DagPose,
    "decomposeMatrix": DecomposeMatrix,
    "displayLayer": DisplayLayer,
    "distanceBetween": DistanceBetween,
    "file": File,
    "fourByFourMatrix": FourByFourMatrix,
    "geometryConstraint": GeometryConstraint,
    "ikHandle": IkHandle,
    "inverseMatrix": InverseMatrix,
    "joint": Joint,
    "lambert": Lambert,
    "locator": Locator,
    "mesh": Mesh,
    "multDL": MultDL,
    "multDoubleLinear": MultDoubleLinear,
    "multMatrix": MultMatrix,
    "multiplyDivide": MultiplyDivide,
    "normalConstraint": NormalConstraint,
    "nurbsCurve": NurbsCurve,
    "nurbsSurface": NurbsSurface,
    "objectSet": ObjectSet,
    "orientConstraint": OrientConstraint,
    "paintableShadingDependNode": PaintableShadingDependNode,
    "pairBlend": PairBlend,
    "parentConstraint": ParentConstraint,
    "phong": Phong,
    "phongE": PhongE,
    "pickMatrix": PickMatrix,
    "place2dTexture": Place2dTexture,
    "place3dTexture": Place3dTexture,
    "plusMinusAverage": PlusMinusAverage,
    "pointConstraint": PointConstraint,
    "pointOnCurveInfo": PointOnCurveInfo,
    "pointOnPolyConstraint": PointOnPolyConstraint,
    "pointOnSurfaceInfo": PointOnSurfaceInfo,
    "poleVectorConstraint": PoleVectorConstraint,
    "reference": Reference,
    "reflect": Reflect,
    "remapValue": RemapValue,
    "reverse": Reverse,
    "scaleConstraint": ScaleConstraint,
    "setRange": SetRange,
    "shadingDependNode": ShadingDependNode,
    "shadingEngine": ShadingEngine,
    "shape": Shape,
    "skinCluster": SkinCluster,
    "standardSurface": StandardSurface,
    "surfaceShader": SurfaceShader,
    "tangentConstraint": TangentConstraint,
    "texture2d": Texture2d,
    "transform": Transform,
    "unitConversion": UnitConversion,
    "vectorProduct": VectorProduct,
}


def __getattr__(name):
    """未登録の Maya nodeType に対応する自動生成クラスを ``mlib.nodes.<TypeName>`` で取得する。

    通常の属性(登録クラス・サブモジュール)に無い名前だけが対象になる。名前の先頭を小文字に
    した型名(``PointLight`` → ``pointLight``)と名前そのまま(``AISEnvFacade``)の順に、
    登録表の完全一致・Maya の認識を調べる。

    Args:
        name (str): クラス名。先頭は大文字。

    Returns:
        type: 登録クラス、または Maya の継承に沿って生成したクラス。

    Raises:
        AttributeError: 先頭が大文字でない、または Maya が認識しない型名の場合
            (プラグイン未ロードを含む)。
    """
    registry = Node._registry
    if not name or not name[0].isupper() or registry is None or not registry._generate_classes:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    candidates = [name[0].lower() + name[1:]]
    if name not in candidates:
        candidates.append(name)
    for node_type in candidates:
        if registry.lookup(node_type) is not None or _node_type_exists(node_type):
            return registry.wrapper_class(node_type)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}: "
                         f"unknown Maya node type {candidates[0]!r} (plug-in not loaded?)")
