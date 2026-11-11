# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

from . import logger
from . import util, core, common, decorator, cmds, nodes, plugs, components, maths, json
from .core.registry import NodeRegistry as _NodeRegistry
from .core.reload import reload_package as _reload_package
from .cmds import bakeDeformer, bakeResults, bindSkin, createBlendShape, createCircle, createCluster, createContainer, createCurve, createDagContainer, createDagPose, createGroup, createIkHandle, createJointChain, createLattice, createLocator, createNode, createNurbsPlane, createPolyCube, createPolyCylinder, createPolyPlane, createPolySphere, createWire, delete, duplicate, getNode, getPlug, ls, objExists, select
from .core import extensions as _extensions
from .nodes import AddDL as AddDL, AddDoubleLinear as AddDoubleLinear, AimConstraint as AimConstraint, AimMatrix as AimMatrix, AngleBetween as AngleBetween, AnimCurve as AnimCurve, AnimCurveTA as AnimCurveTA, AnimCurveTL as AnimCurveTL, AnimCurveTT as AnimCurveTT, AnimCurveTU as AnimCurveTU, AnimCurveUA as AnimCurveUA, AnimCurveUL as AnimCurveUL, AnimCurveUT as AnimCurveUT, AnimCurveUU as AnimCurveUU, BlendColors as BlendColors, BlendMatrix as BlendMatrix, BlendShape as BlendShape, BlendWeighted as BlendWeighted, Blinn as Blinn, Camera as Camera, Clamp as Clamp, Cluster as Cluster, ComposeMatrix as ComposeMatrix, Condition as Condition, Constraint as Constraint, Container as Container, CurveInfo as CurveInfo, DagContainer as DagContainer, DagNode as DagNode, DagPose as DagPose, DecomposeMatrix as DecomposeMatrix, DisplayLayer as DisplayLayer, DistanceBetween as DistanceBetween, File as File, FourByFourMatrix as FourByFourMatrix, GeometryConstraint as GeometryConstraint, GeometryFilter as GeometryFilter, IkHandle as IkHandle, InverseMatrix as InverseMatrix, Joint as Joint, Joints as Joints, Lambert as Lambert, Locator as Locator, Mesh as Mesh, MultDL as MultDL, MultDoubleLinear as MultDoubleLinear, MultMatrix as MultMatrix, MultiplyDivide as MultiplyDivide, Node as Node, Nodes as Nodes, NormalConstraint as NormalConstraint, NurbsCurve as NurbsCurve, NurbsSurface as NurbsSurface, ObjectSet as ObjectSet, OrientConstraint as OrientConstraint, PaintableShadingDependNode as PaintableShadingDependNode, PairBlend as PairBlend, ParentConstraint as ParentConstraint, Phong as Phong, PhongE as PhongE, PickMatrix as PickMatrix, Place2dTexture as Place2dTexture, Place3dTexture as Place3dTexture, PlusMinusAverage as PlusMinusAverage, PointConstraint as PointConstraint, PointOnCurveInfo as PointOnCurveInfo, PointOnPolyConstraint as PointOnPolyConstraint, PointOnSurfaceInfo as PointOnSurfaceInfo, PoleVectorConstraint as PoleVectorConstraint, Reference as Reference, Reflect as Reflect, RemapValue as RemapValue, Reverse as Reverse, ScaleConstraint as ScaleConstraint, SetRange as SetRange, ShadingDependNode as ShadingDependNode, ShadingEngine as ShadingEngine, Shape as Shape, SkinCluster as SkinCluster, SkinClusters as SkinClusters, StandardSurface as StandardSurface, SurfaceShader as SurfaceShader, TangentConstraint as TangentConstraint, Texture2d as Texture2d, Transform as Transform, UnitConversion as UnitConversion, VectorProduct as VectorProduct
from .plugs import BoolPlug as BoolPlug, CompoundPlug as CompoundPlug, Double3Plug as Double3Plug, DoubleAnglePlug as DoubleAnglePlug, DoubleLinearPlug as DoubleLinearPlug, DoublePlug as DoublePlug, EnumPlug as EnumPlug, FloatPlug as FloatPlug, LongPlug as LongPlug, MatrixPlug as MatrixPlug, MessagePlug as MessagePlug, MultiPlug as MultiPlug, Plug as Plug, Plugs as Plugs, RampPlug as RampPlug, ShortPlug as ShortPlug, StringPlug as StringPlug, TimePlug as TimePlug
from .components import Component as Component, Components as Components, PointComponent as PointComponent, PointComponents as PointComponents, Vertex as Vertex, Vertices as Vertices, CV as CV, CVs as CVs, Edge as Edge, Edges as Edges, Face as Face, Faces as Faces, UV as UV, UVs as UVs, VertexFace as VertexFace, VertexFaces as VertexFaces, SurfaceCV as SurfaceCV, SurfaceCVs as SurfaceCVs, LatticePoint as LatticePoint, LatticePoints as LatticePoints
from .maths import MSpace as MSpace, EulerRotate as EulerRotate, Matrix as Matrix, Quaternion as Quaternion, Scale as Scale, Shear as Shear, Translate as Translate, Vector as Vector
from .common import Callbacks as Callbacks, CurveFit as CurveFit, DampedSpring as DampedSpring, Deferred as Deferred, DrivenKey as DrivenKey, Environment as Environment, Keyframe as Keyframe, Keyframes as Keyframes, Module as Module, Namespace as Namespace, Plugin as Plugin, PluginPackage as PluginPackage, ProgressCancelled as ProgressCancelled, ScalarGraph as ScalarGraph, ScriptJob as ScriptJob, ScriptJobs as ScriptJobs, Selection as Selection, Time as Time, Version as Version
from typing import Any
from types import ModuleType

_node_registry: Any
_plug_registry: Any
_CLASS_PACKAGES: tuple
_EXCLUDED_CLASSES: frozenset
_names: list

def _class_sources() -> dict[str, str]:
    """ルートから取得できるクラス名と、その所属パッケージの対応を作る。

    各パッケージの ``__all__`` のうちクラスだけを対象にし、ルートの名前と ``_CLASS_PACKAGES`` の
    先にあるパッケージを優先する。commonは遅延公開のためimportせず、大文字だけの名前(定数)を除く。

    Returns:
        dict[str, str]: クラス名から所属パッケージ名への対応。
    """
    ...
_classes: Any
__all__ = ['bakeDeformer', 'bakeResults', 'bindSkin', 'cmds', 'common', 'components', 'core', 'createBlendShape', 'createCircle', 'createCluster', 'createContainer', 'createCurve', 'createDagContainer', 'createDagPose', 'createGroup', 'createIkHandle', 'createJointChain', 'createLattice', 'createLocator', 'createNode', 'createNurbsPlane', 'createPolyCube', 'createPolyCylinder', 'createPolyPlane', 'createPolySphere', 'createWire', 'decorator', 'delete', 'duplicate', 'getNode', 'getPlug', 'json', 'logger', 'ls', 'maths', 'nodes', 'objExists', 'plugs', 'reload', 'select', 'util', 'AddDL', 'AddDoubleLinear', 'AimConstraint', 'AimMatrix', 'AngleBetween', 'AnimCurve', 'AnimCurveTA', 'AnimCurveTL', 'AnimCurveTT', 'AnimCurveTU', 'AnimCurveUA', 'AnimCurveUL', 'AnimCurveUT', 'AnimCurveUU', 'BlendColors', 'BlendMatrix', 'BlendShape', 'BlendWeighted', 'Blinn', 'BoolPlug', 'CV', 'CVs', 'Callbacks', 'Camera', 'Clamp', 'Cluster', 'Component', 'Components', 'ComposeMatrix', 'CompoundPlug', 'Condition', 'Constraint', 'Container', 'CurveFit', 'CurveInfo', 'DagContainer', 'DagNode', 'DagPose', 'DampedSpring', 'DecomposeMatrix', 'Deferred', 'DisplayLayer', 'DistanceBetween', 'Double3Plug', 'DoubleAnglePlug', 'DoubleLinearPlug', 'DoublePlug', 'DrivenKey', 'Edge', 'Edges', 'EnumPlug', 'Environment', 'EulerRotate', 'Face', 'Faces', 'File', 'FloatPlug', 'FourByFourMatrix', 'GeometryConstraint', 'GeometryFilter', 'IkHandle', 'InverseMatrix', 'Joint', 'Joints', 'Keyframe', 'Keyframes', 'Lambert', 'LatticePoint', 'LatticePoints', 'Locator', 'LongPlug', 'MSpace', 'Matrix', 'MatrixPlug', 'Mesh', 'MessagePlug', 'Module', 'MultDL', 'MultDoubleLinear', 'MultMatrix', 'MultiPlug', 'MultiplyDivide', 'Namespace', 'Node', 'Nodes', 'NormalConstraint', 'NurbsCurve', 'NurbsSurface', 'ObjectSet', 'OrientConstraint', 'PaintableShadingDependNode', 'PairBlend', 'ParentConstraint', 'Phong', 'PhongE', 'PickMatrix', 'Place2dTexture', 'Place3dTexture', 'Plug', 'Plugin', 'PluginPackage', 'Plugs', 'PlusMinusAverage', 'PointComponent', 'PointComponents', 'PointConstraint', 'PointOnCurveInfo', 'PointOnPolyConstraint', 'PointOnSurfaceInfo', 'PoleVectorConstraint', 'ProgressCancelled', 'Quaternion', 'RampPlug', 'Reference', 'Reflect', 'RemapValue', 'Reverse', 'ScalarGraph', 'Scale', 'ScaleConstraint', 'ScriptJob', 'ScriptJobs', 'Selection', 'SetRange', 'ShadingDependNode', 'ShadingEngine', 'Shape', 'Shear', 'ShortPlug', 'SkinCluster', 'SkinClusters', 'StandardSurface', 'StringPlug', 'SurfaceCV', 'SurfaceCVs', 'SurfaceShader', 'TangentConstraint', 'Texture2d', 'Time', 'TimePlug', 'Transform', 'Translate', 'UV', 'UVs', 'UnitConversion', 'Vector', 'VectorProduct', 'Version', 'Vertex', 'VertexFace', 'VertexFaces', 'Vertices']
__version__: str

def reload() -> tuple[ModuleType]:
    """本体を再読み込みし、拡張を再探索して型登録を作り直す。

    宣言済み・読込み失敗の拡張モジュールを先に解除し、本体の再読込み中に拡張を再初期化する。
    外部SDKやMayaプラグイン自体は解除対象にしない。保持済みのクラス・関数・ラッパーは取り直す。
    拡張単位の読込み/登録失敗はcore.extensions.status()で確認する。途中状態の自動復元は保証しない。

    Returns:
        tuple[module]: 本体側で再読み込みしたモジュール群。拡張モジュールの一覧ではない。

    Raises:
        RuntimeError: 拡張初期化中の再入で、再読み込みを開始できない場合。
    """
    ...

def __getattr__(name: str) -> type:
    """各パッケージのクラスを ``mlib.<クラス名>`` で取得する。

    ``mlib.Joint`` は ``mlib.nodes.Joint`` と同じクラスを返す。値は保持せず毎回所属パッケージから
    取得するため、再読み込み後も現在のクラスを返す。どのパッケージにも無い先頭が大文字の名前は、
    ``mlib.nodes`` と同じく登録の無いMayaのnodeTypeの生成クラスとして解決する(例: ``mlib.PointLight``)。

    Args:
        name (str): クラス名。

    Returns:
        type: 所属パッケージのクラス、または生成クラス。

    Raises:
        AttributeError: 対象のクラスが無い場合。
    """
    ...

def __dir__() -> list[str]:
    """モジュール内の名前と、ルートから取得できるクラス名を列挙する。

    Returns:
        list[str]: 補完・探索に使用する名前の一覧。
    """
    ...
