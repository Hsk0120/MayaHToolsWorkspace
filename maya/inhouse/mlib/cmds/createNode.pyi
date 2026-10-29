# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaノードを作成し、実際のノード型に対応するラッパーを返す。

mlibでノードを作成する唯一の入口。``cmds.createNode`` に相当し、``Node.create`` や
``Node(name, create=True)`` のような作成経路は無い。戻り値は作成したノードの実際のnodeTypeに
対応するラッパー(登録済みクラス、未登録型は登録表の規則で選ぶクラス)で、``getType()`` は
MayaのnodeType名を返す。

通常はMayaのUndoに対応し、1回のUndoで作成(shapeの自動生成transformを含む)を戻せる。
``fast=True`` は対応する作成条件をOpenMayaで直接処理し、Undo履歴を追加しない。
未対応の条件はノードを作る前に拒否する。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    child = mlib.createNode("joint", n="child", p=node, ss=True)
"""

from ..decorator import _edit_context, _merge_flags
from ..util import _UNSET
from typing import Literal
from mlib.nodes.addDL import AddDL
from mlib.nodes.addDoubleLinear import AddDoubleLinear
from mlib.nodes.aimConstraint import AimConstraint
from mlib.nodes.animCurve import AnimCurve
from mlib.nodes.animCurveTA import AnimCurveTA
from mlib.nodes.animCurveTL import AnimCurveTL
from mlib.nodes.animCurveTT import AnimCurveTT
from mlib.nodes.animCurveTU import AnimCurveTU
from mlib.nodes.animCurveUA import AnimCurveUA
from mlib.nodes.animCurveUL import AnimCurveUL
from mlib.nodes.animCurveUT import AnimCurveUT
from mlib.nodes.animCurveUU import AnimCurveUU
from mlib.nodes.blendColors import BlendColors
from mlib.nodes.blendShape import BlendShape
from mlib.nodes.blendWeighted import BlendWeighted
from mlib.nodes.blinn import Blinn
from mlib.nodes.camera import Camera
from mlib.nodes.clamp import Clamp
from mlib.nodes.cluster import Cluster
from mlib.nodes.condition import Condition
from mlib.nodes.constraint import Constraint
from mlib.nodes.container import Container
from mlib.nodes.dagContainer import DagContainer
from mlib.nodes.dagNode import DagNode
from mlib.nodes.dagPose import DagPose
from mlib.nodes.displayLayer import DisplayLayer
from mlib.nodes.file import File
from mlib.nodes.geometryConstraint import GeometryConstraint
from mlib.nodes.ikHandle import IkHandle
from mlib.nodes.joint import Joint
from mlib.nodes.lambert import Lambert
from mlib.nodes.locator import Locator
from mlib.nodes.mesh import Mesh
from mlib.nodes.multDL import MultDL
from mlib.nodes.multDoubleLinear import MultDoubleLinear
from mlib.nodes.multiplyDivide import MultiplyDivide
from mlib.nodes.node import Node
from mlib.nodes.normalConstraint import NormalConstraint
from mlib.nodes.nurbsCurve import NurbsCurve
from mlib.nodes.nurbsSurface import NurbsSurface
from mlib.nodes.objectSet import ObjectSet
from mlib.nodes.orientConstraint import OrientConstraint
from mlib.nodes.paintableShadingDependNode import PaintableShadingDependNode
from mlib.nodes.parentConstraint import ParentConstraint
from mlib.nodes.phong import Phong
from mlib.nodes.phongE import PhongE
from mlib.nodes.place2dTexture import Place2dTexture
from mlib.nodes.place3dTexture import Place3dTexture
from mlib.nodes.plusMinusAverage import PlusMinusAverage
from mlib.nodes.pointConstraint import PointConstraint
from mlib.nodes.pointOnPolyConstraint import PointOnPolyConstraint
from mlib.nodes.poleVectorConstraint import PoleVectorConstraint
from mlib.nodes.reference import Reference
from mlib.nodes.reflect import Reflect
from mlib.nodes.remapValue import RemapValue
from mlib.nodes.reverse import Reverse
from mlib.nodes.scaleConstraint import ScaleConstraint
from mlib.nodes.setRange import SetRange
from mlib.nodes.shadingDependNode import ShadingDependNode
from mlib.nodes.shadingEngine import ShadingEngine
from mlib.nodes.shape import Shape
from mlib.nodes.skinCluster import SkinCluster
from mlib.nodes.standardSurface import StandardSurface
from mlib.nodes.surfaceShader import SurfaceShader
from mlib.nodes.tangentConstraint import TangentConstraint
from mlib.nodes.texture2d import Texture2d
from mlib.nodes.transform import Transform
from mlib.nodes.unitConversion import UnitConversion
from typing import overload


@overload
def createNode(type: Literal["addDL"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AddDL: ...
@overload
def createNode(type: Literal["addDoubleLinear"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AddDoubleLinear: ...
@overload
def createNode(type: Literal["aimConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AimConstraint: ...
@overload
def createNode(type: Literal["animCurve"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurve: ...
@overload
def createNode(type: Literal["animCurveTA"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveTA: ...
@overload
def createNode(type: Literal["animCurveTL"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveTL: ...
@overload
def createNode(type: Literal["animCurveTT"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveTT: ...
@overload
def createNode(type: Literal["animCurveTU"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveTU: ...
@overload
def createNode(type: Literal["animCurveUA"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveUA: ...
@overload
def createNode(type: Literal["animCurveUL"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveUL: ...
@overload
def createNode(type: Literal["animCurveUT"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveUT: ...
@overload
def createNode(type: Literal["animCurveUU"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> AnimCurveUU: ...
@overload
def createNode(type: Literal["blendColors"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> BlendColors: ...
@overload
def createNode(type: Literal["blendShape"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> BlendShape: ...
@overload
def createNode(type: Literal["blendWeighted"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> BlendWeighted: ...
@overload
def createNode(type: Literal["blinn"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Blinn: ...
@overload
def createNode(type: Literal["camera"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Camera: ...
@overload
def createNode(type: Literal["clamp"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Clamp: ...
@overload
def createNode(type: Literal["cluster"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Cluster: ...
@overload
def createNode(type: Literal["condition"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Condition: ...
@overload
def createNode(type: Literal["constraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Constraint: ...
@overload
def createNode(type: Literal["container"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Container: ...
@overload
def createNode(type: Literal["dagContainer"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> DagContainer: ...
@overload
def createNode(type: Literal["dagNode"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> DagNode: ...
@overload
def createNode(type: Literal["dagPose"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> DagPose: ...
@overload
def createNode(type: Literal["displayLayer"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> DisplayLayer: ...
@overload
def createNode(type: Literal["file"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> File: ...
@overload
def createNode(type: Literal["geometryConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> GeometryConstraint: ...
@overload
def createNode(type: Literal["ikHandle"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> IkHandle: ...
@overload
def createNode(type: Literal["joint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Joint: ...
@overload
def createNode(type: Literal["lambert"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Lambert: ...
@overload
def createNode(type: Literal["locator"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Locator: ...
@overload
def createNode(type: Literal["mesh"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Mesh: ...
@overload
def createNode(type: Literal["multDL"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> MultDL: ...
@overload
def createNode(type: Literal["multDoubleLinear"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> MultDoubleLinear: ...
@overload
def createNode(type: Literal["multiplyDivide"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> MultiplyDivide: ...
@overload
def createNode(type: Literal["normalConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> NormalConstraint: ...
@overload
def createNode(type: Literal["nurbsCurve"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> NurbsCurve: ...
@overload
def createNode(type: Literal["nurbsSurface"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> NurbsSurface: ...
@overload
def createNode(type: Literal["objectSet"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> ObjectSet: ...
@overload
def createNode(type: Literal["orientConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> OrientConstraint: ...
@overload
def createNode(type: Literal["paintableShadingDependNode"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PaintableShadingDependNode: ...
@overload
def createNode(type: Literal["parentConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> ParentConstraint: ...
@overload
def createNode(type: Literal["phong"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Phong: ...
@overload
def createNode(type: Literal["phongE"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PhongE: ...
@overload
def createNode(type: Literal["place2dTexture"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Place2dTexture: ...
@overload
def createNode(type: Literal["place3dTexture"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Place3dTexture: ...
@overload
def createNode(type: Literal["plusMinusAverage"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PlusMinusAverage: ...
@overload
def createNode(type: Literal["pointConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PointConstraint: ...
@overload
def createNode(type: Literal["pointOnPolyConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PointOnPolyConstraint: ...
@overload
def createNode(type: Literal["poleVectorConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> PoleVectorConstraint: ...
@overload
def createNode(type: Literal["reference"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Reference: ...
@overload
def createNode(type: Literal["reflect"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Reflect: ...
@overload
def createNode(type: Literal["remapValue"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> RemapValue: ...
@overload
def createNode(type: Literal["reverse"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Reverse: ...
@overload
def createNode(type: Literal["scaleConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> ScaleConstraint: ...
@overload
def createNode(type: Literal["setRange"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> SetRange: ...
@overload
def createNode(type: Literal["shadingDependNode"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> ShadingDependNode: ...
@overload
def createNode(type: Literal["shadingEngine"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> ShadingEngine: ...
@overload
def createNode(type: Literal["shape"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Shape: ...
@overload
def createNode(type: Literal["skinCluster"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> SkinCluster: ...
@overload
def createNode(type: Literal["standardSurface"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> StandardSurface: ...
@overload
def createNode(type: Literal["surfaceShader"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> SurfaceShader: ...
@overload
def createNode(type: Literal["tangentConstraint"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> TangentConstraint: ...
@overload
def createNode(type: Literal["texture2d"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Texture2d: ...
@overload
def createNode(type: Literal["transform"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Transform: ...
@overload
def createNode(type: Literal["unitConversion"], *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> UnitConversion: ...
@overload
def createNode(type: str, *, fast: bool = ..., name: str = ..., n: str = ..., parent: object = ..., p: object = ..., shared: bool = ..., s: bool = ..., skipSelect: bool = ..., ss: bool = ..., **kwargs: object) -> Node:
    """Mayaノードを作成し、実際の型に対応するラッパーを返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。
    ``cmds.createNode`` に無い ``query``/``edit`` は受け付けない(他のフラグと同様にMayaがTypeErrorにする)。

    親を省略したshape型はshapeを返し、``getParent()`` がMayaの自動生成したtransformになる。
    ``shared=True`` で同名・同型のノードが既にある場合は作成せずそのノードを返す(cmds.createNodeが
    作成せずNoneを返す場合。cmdsはルート名前空間の名前だけ再利用し、名前空間付きの名前は連番名で作る)。
    fast=Trueは名前で既存の同型ノードを探す近似で、名前空間付きでも既存ノードを返し、同名ノードの型が
    違う場合は新しい連番名で作らず RuntimeError にする。

    Args:
        type (str): Mayaノード型名。
        fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parent (object): 親ノード。Node・Plug・Component・API参照は所有ノードの完全パスへ変換する。
        p (object): parentの短縮名。同時指定はできない。
        shared (bool): 同名の共有ノードがある場合のMaya標準の共有指定。
        s (bool): sharedの短縮名。同時指定はできない。
        skipSelect (bool): 作成したノードを選択しない指定。
        ss (bool): skipSelectの短縮名。同時指定はできない。
        **kwargs (object): 通常処理では追加のMayaフラグをそのまま渡す。
            fast=Trueでは対応しないフラグを作成前に拒否する。

    Returns:
        Node: 作成したノードの実際のnodeTypeに対応するラッパー。

    Raises:
        TypeError: 長名・短名の同時指定、fastがbool以外、parentが対応しない型、
            またはcmds.createNodeに無いフラグ(query/edit等)を指定した場合。
        ValueError: typeが空文字列・文字列以外、parent が空文字列、または削除済みの対象の場合。
        RuntimeError: Mayaが認識しないノード型名の場合(unknownノードを残さない。版の互換名は作成できる)、
            parent を解決できない場合、fast=Trueでロック・参照された親を指定した場合、
            またはMayaが作成を拒否した場合。
        NotImplementedError: fast=Trueで未対応のフラグを指定した場合。
    """
    ...
