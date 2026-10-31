"""4本の足の接地点が作る面に合わせて、胴体(腰)を傾け上下させる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


class GroundTilt(TwistDistribution):
    """4足の動物・機械の胴体を、足の接地点の面の傾きと高さに合わせる標準DG。

    前足の中点・後足の中点・左足の中点・右足の中点から足の面の向きを ``aimMatrix`` で求め、
    生成時の向きからの回転を ``tilt`` の割合で胴体へ加える。高さは4点の平均の上下の変化を ``height`` の割合で加える。
    """

    @classmethod
    @undoTransaction("mlrig.GroundTilt.create")
    def create(cls, body, frontLeft, frontRight, backLeft, backRight, name="groundTilt", tilt=1.0, height=1.0):
        """胴体の入力と4本の足の接地点から、補正後の胴体のワールド行列を生成する。

        Args:
            body (str | Node): 胴体(腰)の入力のtransform。アニメーターが動かすコントロールなど。
                出力はこのtransform自身ではなく、別の受け側(駆動される腰のjointなど)へ接続する。
            frontLeft (str | Node): 左前足の接地点のtransform。位置だけを使う。
            frontRight (str | Node): 右前足の接地点のtransform。
            backLeft (str | Node): 左後足の接地点のtransform。
            backRight (str | Node): 右後足の接地点のtransform。
            name (str): 一意なcontainer名。
            tilt (float): 足の面の回転を胴体へ加える割合(0〜1)。
            height (float): 4点の平均の高さの変化を胴体へ加える割合。

        Returns:
            GroundTilt: matrix・pitch・roll・lift の所有者。

        Raises:
            ValueError: 同じtransformを含む場合、前後・左右の中点が重なる場合、前後と左右の向きが平行な場合、
                割合が有限でない場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。前 F・後 B・左 L・右 R は2本ずつの足の位置の平均、中心 C は4本の平均。
            足の面の向き A = aimMatrix(位置C、+XをFへ向け、+ZをLの方向へ揃える)の回転。
            D = A0^-1 * A(A0は生成時のA、Mayaの行ベクトルの規約でワールドの回転差)、
            Dt = slerp(単位行列, D, tilt)(``blendMatrix``)。
            matrix = 胴体の現在のワールド行列を、その位置を中心にDtで回し、ワールドY方向へ lift = height*(C.y - C0.y) 動かしたもの。
            pitch・rollは、Dで回した生成時の前後の向き・左右の向きの、水平面からの角度の変化(度、確認用の出力)。
            足が平らなまま一緒に上下・水平移動しても回転しない(liftだけ変わる)。
        """
        values = [float(value) for value in (tilt, height)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("tilt and height must be finite")
        tilt, height = values
        if mlib.objExists(name):
            raise ValueError("GroundTilt container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in (body, frontLeft, frontRight, backLeft, backRight)]
        if any(not isinstance(node, mlib.nodes.Transform) for node in nodes) or len(
            {node.getUuid() for node in nodes}
        ) != len(nodes):
            raise ValueError("Expected five different transforms")
        body, feet = nodes[0], nodes[1:]
        points = [Vector(Matrix(node.getPlug("worldMatrix")[0].get()).translate) for node in feet]
        front, back = (points[0] + points[1]) * 0.5, (points[2] + points[3]) * 0.5
        left, right = (points[0] + points[2]) * 0.5, (points[1] + points[3]) * 0.5
        forward, side = front - back, left - right
        if forward.length() < 1e-6 or side.length() < 1e-6:
            raise ValueError("The front/back and left/right midpoints must be apart")
        if (forward.normal() ^ side.normal()).length() < 1e-3:
            raise ValueError("The front/back and left/right directions must not be parallel")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        owner.addAttr(longName="tilt", attributeType="double", defaultValue=tilt, minValue=0, maxValue=1,
                      keyable=True)
        owner.addAttr(longName="height", attributeType="double", defaultValue=height, keyable=True)
        outputs = ("pitch", "roll", "lift")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 足の位置(ワールド、cm)。
        positions = []
        for role, node in zip(("frontLeft", "frontRight", "backLeft", "backRight"), feet):
            location = graph._node("decomposeMatrix", role + "Position")
            node.getPlug("worldMatrix")[0].connectTo(location.getPlug("inputMatrix"))
            positions.append(location.getPlug("outputTranslate"))

        def average(role, indices):
            """指定した足の位置の平均(plusMinusAverageの平均)を、位置だけの行列で返す。"""
            mean = graph._node("plusMinusAverage", role + "Mean")
            mean.getPlug("operation").set(3)
            for slot, index in enumerate(indices):
                positions[index].connectTo(mean.getPlug("input3D")[slot])
            matrix = graph._node("composeMatrix", role + "Point")
            mean.getPlug("output3D").connectTo(matrix.getPlug("inputTranslate"))
            return mean, matrix.getPlug("outputMatrix")

        center, center_matrix = average("center", (0, 1, 2, 3))
        _, front_matrix = average("front", (0, 1))
        _, left_matrix = average("left", (0, 2))
        aim = graph._node("aimMatrix", "plane")
        center_matrix.connectTo(aim.getPlug("inputMatrix"))
        front_matrix.connectTo(aim.getPlug("primaryTargetMatrix"))
        aim.getPlug("primaryMode").set(1)
        aim.getPlug("primaryInputAxis").set((1, 0, 0))
        aim.getPlug("primaryTargetVector").set((0, 0, 0))
        left_matrix.connectTo(aim.getPlug("secondaryTargetMatrix"))
        aim.getPlug("secondaryMode").set(1)
        aim.getPlug("secondaryInputAxis").set((0, 0, 1))
        aim.getPlug("secondaryTargetVector").set((0, 0, 0))
        plane = graph._node("pickMatrix", "planeRotation")
        aim.getPlug("outputMatrix").connectTo(plane.getPlug("inputMatrix"))
        for attr in ("useTranslate", "useScale", "useShear"):
            plane.getPlug(attr).set(False)
        rest_plane = Matrix(plane.getPlug("outputMatrix").get())
        rest_center = Vector(center.getPlug("output3D").get())
        delta = graph._node("multMatrix", "planeDelta")
        delta.getPlug("matrixIn")[0].set(rest_plane.inverse())
        plane.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[1])
        blend = graph._node("blendMatrix", "tiltBlend")
        blend.getPlug("inputMatrix").set(Matrix())
        delta.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        owner.getPlug("tilt").connectTo(blend.getPlug("target")[0]["weight"])

        # lift = height * (C.y - C0.y)
        lift = graph._node("plusMinusAverage", "liftRaw")
        lift.getPlug("operation").set(2)
        center.getPlug("output3Dy").connectTo(lift.getPlug("input1D")[0])
        lift.getPlug("input1D")[1].set(rest_center.y)
        lifted = graph._node("multiplyDivide", "lift")
        lift.getPlug("output1D").connectTo(lifted.getPlug("input1X"))
        owner.getPlug("height").connectTo(lifted.getPlug("input2X"))
        lifted.getPlug("outputX").connectTo(owner.getPlug("lift"))

        # 胴体の位置を中心に回す: T(-b) * Dt * T(b) * T(0, lift, 0)
        body_position = graph._node("decomposeMatrix", "bodyPosition")
        body.getPlug("worldMatrix")[0].connectTo(body_position.getPlug("inputMatrix"))
        negative = graph._node("multiplyDivide", "bodyNegative")
        body_position.getPlug("outputTranslate").connectTo(negative.getPlug("input1"))
        negative.getPlug("input2").set((-1, -1, -1))
        to_origin = graph._node("composeMatrix", "toOrigin")
        negative.getPlug("output").connectTo(to_origin.getPlug("inputTranslate"))
        back_to_body = graph._node("plusMinusAverage", "liftedPosition")
        body_position.getPlug("outputTranslate").connectTo(back_to_body.getPlug("input3D")[0])
        lifted.getPlug("outputX").connectTo(back_to_body.getPlug("input3D")[1]["input3Dy"])
        from_origin = graph._node("composeMatrix", "fromOrigin")
        back_to_body.getPlug("output3D").connectTo(from_origin.getPlug("inputTranslate"))
        result = graph._node("multMatrix", "result")
        body.getPlug("worldMatrix")[0].connectTo(result.getPlug("matrixIn")[0])
        to_origin.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
        blend.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[2])
        from_origin.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[3])
        result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))

        # 確認用: 生成時の前後・左右の向きをDで回したときの、水平面からの角度(度)。
        for attr, direction in (("pitch", forward.normal()), ("roll", side.normal())):
            rotated = graph._node("vectorProduct", attr + "Direction")
            rotated.getPlug("operation").set(3)
            rotated.getPlug("input1").set(list(direction))
            rotated.getPlug("normalizeOutput").set(True)
            delta.getPlug("matrixSum").connectTo(rotated.getPlug("matrix"))
            # 角度 = asin(y)。標準ノードにasinは無いので、水平成分との angleBetween で求める。
            horizontal = graph._node("multiplyDivide", attr + "Horizontal")
            rotated.getPlug("output").connectTo(horizontal.getPlug("input1"))
            horizontal.getPlug("input2").set((1, 0, 1))
            angle = graph._node("angleBetween", attr + "Angle")
            horizontal.getPlug("output").connectTo(angle.getPlug("vector1"))
            rotated.getPlug("output").connectTo(angle.getPlug("vector2"))
            sign = graph._node("condition", attr + "Sign")
            sign.getPlug("operation").set(4)
            rotated.getPlug("outputY").connectTo(sign.getPlug("firstTerm"))
            sign.getPlug("colorIfTrueR").set(-180.0 / math.pi)
            sign.getPlug("colorIfFalseR").set(180.0 / math.pi)
            degrees = graph._node("unitConversion", attr + "Radians")
            conversions.add(degrees.getUuid())
            angle.getPlug("angle").connectTo(degrees.getPlug("input"))
            degrees.getPlug("conversionFactor").set(1.0)
            signed = graph._node("multiplyDivide", attr + "Degrees")
            degrees.getPlug("output").connectTo(signed.getPlug("input1X"))
            sign.getPlug("outColorR").connectTo(signed.getPlug("input2X"))
            rest_angle = math.degrees(math.asin(max(-1.0, min(1.0, direction.y))))
            offset = graph._node("plusMinusAverage", attr + "Change")
            offset.getPlug("operation").set(2)
            signed.getPlug("outputX").connectTo(offset.getPlug("input1D")[0])
            offset.getPlug("input1D")[1].set(rest_angle)
            offset.getPlug("output1D").connectTo(owner.getPlug(attr))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
