"""コントロールの前の向きから、膝・肘が反転しないポールの位置を求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 指定できる前の向きの軸。符号付き。
_AXES = {
    "x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0),
    "-x": (-1.0, 0.0, 0.0), "-y": (0.0, -1.0, 0.0), "-z": (0.0, 0.0, -1.0),
}

#: 前の向きが脚の軸とほぼ平行(この正弦未満)なら、膝の向きが決まらないので作成を拒否する。
_PARALLEL_SINE = 1e-3


class NoFlipPole(TwistDistribution):
    """付け根から先端への軸と、コントロールの前の向きで決まる枠から、ポールの位置を出力する標準DG。

    ワールドに固定したポールのコントロールは、足が付け根の前・横・後ろを大きく回り込むと
    膝の向きが反転する(フリップ)。この部品はポールを足のコントロールの前の向きに付け、
    脚の軸に垂直な面へ射影して置くので、足がどこへ動いても膝は足の前の向きを向き続ける。
    ``kneeTwist`` で脚の軸まわりに回すと、膝のコントロールを動かすのと同じように膝の向きを変えられる。
    """

    @classmethod
    def polePosition(cls, start, end, forward, distance, position=0.5, angle=0.0):
        """ポールの位置を計算する(DGと同じ式のPython版)。

        Args:
            start (Sequence[float]): 付け根の位置(cm)。
            end (Sequence[float]): 先端(足首・手首のコントロール)の位置(cm)。
            forward (Sequence[float]): コントロールの前の向き(ワールド)。
            distance (float): 脚の軸からポールまでの距離(cm)。
            position (float): 付け根から先端までのどの割合の高さに置くか。
            angle (float): 前の向きから脚の軸まわりに回す角度(ラジアン、offset + kneeTwist)。

        Returns:
            tuple[float, float, float]: ポールの位置(cm)。

        Raises:
            ValueError: 付け根と先端が重なる場合、または前の向きが脚の軸と平行な場合。
        """
        frame = cls._frame(start, end, forward)
        axis, side, cross = frame
        length = (Vector(*end) - Vector(*start)).length()
        direction = side * math.cos(angle) - cross * math.sin(angle)
        point = Vector(*start) + axis * (length * position) + direction * distance
        return (point.x, point.y, point.z)

    @classmethod
    def _frame(cls, start, end, forward):
        """脚の軸(Y)・前の向きを軸に垂直へ射影した向き(X)・X×Y(Z)を返す(aimMatrixと同じ枠)。"""
        axis = Vector(*end) - Vector(*start)
        if axis.length() < 1e-6:
            raise ValueError("start and end must not overlap")
        axis.normalize()
        forward = Vector(*forward)
        if forward.length() < 1e-9 or (axis ^ forward.normal()).length() < _PARALLEL_SINE:
            raise ValueError("The forward axis of the control must not be parallel to the leg")
        side = (forward - axis * (forward * axis)).normal()
        return axis, side, side ^ axis

    @classmethod
    def restAngle(cls, start, mid, end, forward):
        """生成時の膝の向きを、前の向きから脚の軸まわりに測った角度を返す。

        Args:
            start (Sequence[float]): 付け根の位置(cm)。
            mid (Sequence[float]): 中間関節(膝・肘)の位置(cm)。
            end (Sequence[float]): 先端の位置(cm)。
            forward (Sequence[float]): コントロールの前の向き(ワールド)。

        Returns:
            float: 角度(ラジアン)。膝が一直線上にあり向きが決まらない場合は0。
        """
        axis, side, cross = cls._frame(start, end, forward)
        knee = Vector(*mid) - Vector(*start)
        knee -= axis * (knee * axis)
        if knee.length() < 1e-6:
            return 0.0
        return math.atan2(-(knee * cross), knee * side)

    @classmethod
    @undoTransaction("mlrig.NoFlipPole.create")
    def create(cls, start, end, control=None, mid=None, name="noFlipPole", forwardAxis="z",
               distance=None, position=0.5):
        """ポールの位置を表すワールド行列を生成する。

        Args:
            start (str | Node): 付け根(股関節・肩)のtransform/joint。
            end (str | Node): 先端の位置を表すtransform(足首のIKコントロールやikHandle)。
            control (str | Node | None): 前の向きを読むtransform。Noneならend。
            mid (str | Node | None): 中間関節(膝・肘)。指定すると、生成時の膝の向きを ``offset`` に入れ、
                作成直後のポールが今の膝の曲がる面の上(膝の側)に来る(ポールを付けても膝が跳ねない)。
                Noneなら ``offset`` =0で、ポールはコントロールの前の向きに置く。
            name (str): 一意なcontainer名。
            forwardAxis (str): controlのローカルで前を表す軸 x/y/z/-x/-y/-z。
            distance (float | None): 脚の軸からポールまでの距離(cm、0より大きい)。Noneなら生成時の
                付け根から先端までの距離。
            position (float): 付け根から先端までのどの割合の高さに置くか(0〜1が目安)。

        Returns:
            NoFlipPole: matrix・legLength の所有者。containerに kneeTwist・offset・distance・position を持つ。

        Raises:
            ValueError: 軸・値が不正な場合、transformでない・同じノードの場合、生成時に前の向きが
                脚の軸と平行な場合、またはnameが既に存在する場合。

        Note:
            aimMatrix で、付け根の位置を原点に Y を先端へ向け、X をコントロールの前の向き(ワールド)へ
            合わせた枠 A を作る(X は前の向きを脚の軸に垂直な面へ射影したもの)。L = 付け根から先端の距離として
            matrix = T(distance, 0, 0) · R_Y(offset) · R_Y(kneeTwist) · T(0, L * position, 0) · A
            (行ベクトル規約)。位置は 付け根 + 軸 * L * position + (X cosθ - Z sinθ) * distance、θ = offset + kneeTwist。
            前の向きが脚の軸と平行になる姿勢(足先を脚の延長へ向ける)だけは向きが決まらない。
        """
        if forwardAxis not in _AXES:
            raise ValueError("forwardAxis must be one of x, y, z, -x, -y, -z")
        position = float(position)
        if not math.isfinite(position):
            raise ValueError("position must be finite")
        if distance is not None:
            distance = float(distance)
            if not math.isfinite(distance) or distance <= 0.0:
                raise ValueError("distance must be a finite value greater than 0")
        if mlib.ls(name):
            raise ValueError("NoFlipPole container already exists: " + name)
        start, end = mlib.nodes.Node(start), mlib.nodes.Node(end)
        control = end if control is None else mlib.nodes.Node(control)
        nodes = [start, end, control]
        if mid is not None:
            mid = mlib.nodes.Node(mid)
            nodes.append(mid)
        for node in nodes:
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for start, end, control and mid")
        if start.getFullName() == end.getFullName() or (
                mid is not None and mid.getFullName() in (start.getFullName(), end.getFullName())):
            raise ValueError("start, mid and end must be different nodes")

        def world(node):
            return Matrix(node.getPlug("worldMatrix")[0].get())

        start_point = list(world(start))[12:15]
        end_point = list(world(end))[12:15]
        forward = Vector(*_AXES[forwardAxis]) * world(control)
        cls._frame(start_point, end_point, forward)
        offset = 0.0 if mid is None else cls.restAngle(start_point, list(world(mid))[12:15], end_point, forward)
        if distance is None:
            distance = (Vector(*end_point) - Vector(*start_point)).length()

        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="kneeTwist", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="offset", attributeType="doubleAngle", defaultValue=offset, keyable=True,
                      unit="rad")
        owner.addAttr(longName="distance", attributeType="doubleLinear", defaultValue=distance, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="position", attributeType="double", defaultValue=position, keyable=True)
        owner.addAttr(longName="legLength", attributeType="doubleLinear")
        # 既定値の単位の解釈に頼らず、内部単位(ラジアン・cm)で入れ直す。
        owner.getPlug("offset").set(offset, unit="rad")
        owner.getPlug("distance").set(distance)
        owner.addAttr(longName="matrix", dataType="matrix")

        # 枠 A: 付け根の位置を原点に、Yを先端へ、Xをコントロールの前の向きへ。
        origin = graph._node("pickMatrix", "origin")
        for flag in ("useScale", "useShear", "useRotate"):
            origin.getPlug(flag).set(False)
        start.getPlug("worldMatrix")[0].connectTo(origin.getPlug("inputMatrix"))
        front = graph._node("vectorProduct", "forward")
        front.getPlug("operation").set(3)
        front.getPlug("normalizeOutput").set(True)
        front.getPlug("input1").set(_AXES[forwardAxis])
        control.getPlug("worldMatrix")[0].connectTo(front.getPlug("matrix"))
        aim = graph._node("aimMatrix", "frame")
        origin.getPlug("outputMatrix").connectTo(aim.getPlug("inputMatrix"))
        aim.getPlug("primaryInputAxis").set((0.0, 1.0, 0.0))
        aim.getPlug("primaryMode").set(1)
        end.getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
        aim.getPlug("secondaryInputAxis").set((1.0, 0.0, 0.0))
        aim.getPlug("secondaryMode").set(2)
        front.getPlug("output").connectTo(aim.getPlug("secondaryTargetVector"))

        # 高さ L * position(cm)。
        length = graph._node("distanceBetween", "legLength")
        start.getPlug("worldMatrix")[0].connectTo(length.getPlug("inMatrix1"))
        end.getPlug("worldMatrix")[0].connectTo(length.getPlug("inMatrix2"))
        length.getPlug("distance").connectTo(owner.getPlug("legLength"))
        height = graph._node("multiplyDivide", "height")
        owner.getPlug("legLength").connectTo(height.getPlug("input1X"))
        owner.getPlug("position").connectTo(height.getPlug("input2X"))

        # T(distance) · R(offset) · R(kneeTwist) · T(0, h, 0) · A
        reach = graph._node("composeMatrix", "reach")
        owner.getPlug("distance").connectTo(reach.getPlug("inputTranslateX"))
        rest = graph._node("composeMatrix", "offsetRotation")
        owner.getPlug("offset").connectTo(rest.getPlug("inputRotateY"))
        twist = graph._node("composeMatrix", "twist")
        owner.getPlug("kneeTwist").connectTo(twist.getPlug("inputRotateY"))
        height.getPlug("outputX").connectTo(twist.getPlug("inputTranslateY"))
        result = graph._node("multMatrix", "result")
        for index, source in enumerate((reach, rest, twist)):
            source.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[index])
        aim.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[3])
        result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["legLength"], keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
