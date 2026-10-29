# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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

from ..core.registry import _node_type_exists
from .node import Node, Nodes
from .shape import Shape
from .transform import Transform
from .addDoubleLinear import AddDL, AddDoubleLinear
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
from .blinn import Blinn
from .camera import Camera
from .clamp import Clamp
from .cluster import Cluster
from .condition import Condition
from .constraint import Constraint
from .container import Container
from .dagContainer import DagContainer
from .dagNode import DagNode
from .dagPose import DagPose
from .displayLayer import DisplayLayer
from .file import File
from .geometryConstraint import GeometryConstraint
from .ikHandle import IkHandle
from .joint import Joint, Joints
from .lambert import Lambert
from .locator import Locator
from .mesh import Mesh
from .multDoubleLinear import MultDL, MultDoubleLinear
from .multiplyDivide import MultiplyDivide
from .normalConstraint import NormalConstraint
from .nurbsCurve import NurbsCurve
from .nurbsSurface import NurbsSurface
from .objectSet import ObjectSet
from .orientConstraint import OrientConstraint
from .paintableShadingDependNode import PaintableShadingDependNode
from .parentConstraint import ParentConstraint
from .phong import Phong
from .phongE import PhongE
from .place2dTexture import Place2dTexture
from .place3dTexture import Place3dTexture
from .plusMinusAverage import PlusMinusAverage
from .pointConstraint import PointConstraint
from .pointOnPolyConstraint import PointOnPolyConstraint
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

__all__ = ['AddDL', 'AddDoubleLinear', 'AimConstraint', 'AnimCurve', 'AnimCurveTA', 'AnimCurveTL', 'AnimCurveTT', 'AnimCurveTU', 'AnimCurveUA', 'AnimCurveUL', 'AnimCurveUT', 'AnimCurveUU', 'BlendColors', 'BlendShape', 'BlendWeighted', 'Blinn', 'Camera', 'Clamp', 'Cluster', 'Condition', 'Constraint', 'Container', 'DagContainer', 'DagNode', 'DagPose', 'DisplayLayer', 'File', 'GeometryConstraint', 'IkHandle', 'Joint', 'Joints', 'Lambert', 'Locator', 'Mesh', 'MultDL', 'MultDoubleLinear', 'MultiplyDivide', 'Node', 'Nodes', 'NormalConstraint', 'NurbsCurve', 'NurbsSurface', 'ObjectSet', 'OrientConstraint', 'PaintableShadingDependNode', 'ParentConstraint', 'Phong', 'PhongE', 'Place2dTexture', 'Place3dTexture', 'PlusMinusAverage', 'PointConstraint', 'PointOnPolyConstraint', 'PoleVectorConstraint', 'Reference', 'Reflect', 'RemapValue', 'Reverse', 'ScaleConstraint', 'SetRange', 'ShadingDependNode', 'ShadingEngine', 'Shape', 'SkinCluster', 'SkinClusters', 'StandardSurface', 'SurfaceShader', 'TangentConstraint', 'Texture2d', 'Transform', 'UnitConversion']
_WRAPPER_CLASSES: dict

def __getattr__(name: str) -> type:
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
    ...
