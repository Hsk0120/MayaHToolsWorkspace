"""弓の弦を、両端(弓の上下の先端)から引き手の点へ向け、引き量を出力する標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


class BowString(TwistDistribution):
    """弓の上下の先端から、弦を引く点(ノック位置)へ向かう2本の弦の向き・長さと引き量を出す標準DG。

    弦の各半分の向きは標準の ``aimMatrix`` で求め、生成時の姿勢との差を保つため跳ねない。
    上方向は弓の面の法線(生成時の3点から求め、上の先端の親空間へ固定)に揃えるので、弦はねじれない。
    引き量 ``drawWeight`` (0〜1)は、弓の曲がり(リムの回転)や補正シェイプのドライバーに使う。
    """

    @classmethod
    def drawWeight(cls, draw, maxDraw):
        """引き量を0〜1の重みにする。

        Args:
            draw (float): 生成時からの引き量(cm)。弓から離れる向きが正。
            maxDraw (float): 重みが1になる引き量(cm)。正。

        Returns:
            float: clamp(draw / maxDraw, 0, 1)。
        """
        return min(max(draw / maxDraw, 0.0), 1.0)

    @classmethod
    @undoTransaction("mlrig.BowString.create")
    def create(cls, top, bottom, nock, name="bowString", aimAxis="x", upAxis="y", maxDraw=None):
        """弦の上半分・下半分の親空間行列と、長さ・引き量を生成する。

        Args:
            top (str | Node): 弦を掛ける上の先端のtransform。
            bottom (str | Node): 弦を掛ける下の先端のtransform。
            nock (str | Node): 弦を引く点(矢をつがえる位置・引き手のコントロール)のtransform。
            name (str): 一意なcontainer名。
            aimAxis (str): 弦の向き(先端からnockへ)にする軸x/y/z。
            upAxis (str): 弓の面の法線へ揃える軸x/y/z。aimAxisと異なる。
            maxDraw (float | None): drawWeightが1になる引き量(cm)。Noneなら上下の先端の距離の0.5倍。

        Returns:
            BowString: topMatrix・bottomMatrix・topLength・bottomLength・restDraw・draw・drawWeightの所有者。

        Raises:
            ValueError: 軸・maxDrawが不正な場合、3点が一直線で弓の面を決められない場合、
                またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢(弦を張っただけの状態。nockは上下の先端を結ぶ線から離れていること)。
            弓の面の法線 n = (top - nock) × (bottom - nock) を生成時に求め、topの親空間のベクトルとして固定する。
            各先端の出力 = (生成時のワールド行列 * 生成時のaimMatrix出力^-1) * 現在のaimMatrix出力 を、
            その先端の親の空間へ戻したもの。aimMatrixはaimAxisをnockの位置へ、upAxisをnへ揃える。
            位置は先端の現在位置のまま。topLength・bottomLength = 各先端からnockまでの距離(cm)。
            draw = |nock - (top+bottom)/2| - restDraw(cm)、restDrawは生成時の値(弦を張ったときの距離)。
            drawWeight = clamp(draw / maxDraw, 0, 1)。弦の長さ・引き量は出力するだけで、nockの位置は制限しない。
            弦がnと平行になると向きが不定、負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if aimAxis not in axes or upAxis not in axes or aimAxis == upAxis:
            raise ValueError("aimAxis and upAxis must be two different axes of x, y and z")
        if mlib.ls(name):
            raise ValueError("BowString container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in (top, bottom, nock)]
        if len({node.getUuid() for node in nodes}) != 3 or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected three different transforms for the top, the bottom and the nock")
        top, bottom, nock = nodes
        worlds = [Matrix(node.getPlug("worldMatrix")[0].get()) for node in nodes]
        top_p, bottom_p, nock_p = (Vector(world.translate) for world in worlds)
        normal = (top_p - nock_p) ^ (bottom_p - nock_p)
        span = (top_p - bottom_p).length()
        if span < 1e-6 or normal.length() < 1e-6 * max(span * span, 1e-6):
            raise ValueError("The top, the bottom and the nock must not be on one line")
        rest_draw = (nock_p - (top_p + bottom_p) * 0.5).length()
        maxDraw = span * 0.5 if maxDraw is None else float(maxDraw)
        if not math.isfinite(maxDraw) or maxDraw <= 0:
            raise ValueError("maxDraw must be a positive finite value")
        # 弓の面の法線を、topの親空間(OPMを含む)のベクトルとして固定する。
        parent_world = Matrix(top.getPlug("parentMatrix")[0].get())
        up = Vector(normal.normal() * parent_world.inverse())
        aim_axis = [float(axis == aimAxis) for axis in axes]
        up_axis = [float(axis == upAxis) for axis in axes]

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="restDraw", attributeType="double", defaultValue=rest_draw)
        owner.addAttr(longName="maxDraw", attributeType="double", defaultValue=maxDraw, minValue=1e-6,
                      keyable=True)
        outputs = ("topLength", "bottomLength", "draw", "drawWeight")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("topMatrix", "bottomMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        def centimeters(plug, role):
            """距離のplugを、UIの長さ単位によらずcmの値で返す。"""
            conversion = graph._node("unitConversion", role + "Centimeters")
            plug.connectTo(conversion.getPlug("input"))
            conversion.getPlug("conversionFactor").set(1.0)
            return conversion.getPlug("output")

        for role, node, rest_world in (("top", top, worlds[0]), ("bottom", bottom, worlds[1])):
            aim = graph._node("aimMatrix", role + "Aim")
            node.getPlug("worldMatrix")[0].connectTo(aim.getPlug("inputMatrix"))
            nock.getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
            aim.getPlug("primaryMode").set(1)
            aim.getPlug("primaryInputAxis").set(aim_axis)
            aim.getPlug("primaryTargetVector").set((0, 0, 0))
            aim.getPlug("secondaryMode").set(2)
            aim.getPlug("secondaryInputAxis").set(up_axis)
            aim.getPlug("secondaryTargetVector").set(up)
            top.getPlug("parentMatrix")[0].connectTo(aim.getPlug("secondaryTargetMatrix"))
            frame = aim.getPlug("outputMatrix")
            # 生成時の姿勢でのaimMatrix出力との差を定数で保ち、作成時に姿勢が跳ねないようにする。
            offset = rest_world * Matrix(frame.get()).inverse()
            world = graph._node("multMatrix", role + "World")
            world.getPlug("matrixIn")[0].set(offset)
            frame.connectTo(world.getPlug("matrixIn")[1])
            parent = node.getParent()
            if parent is not None:
                parent.getPlug("worldInverseMatrix")[0].connectTo(world.getPlug("matrixIn")[2])
            world.getPlug("matrixSum").connectTo(owner.getPlug(role + "Matrix"))
            distance = graph._node("distanceBetween", role + "Distance")
            node.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix1"))
            nock.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix2"))
            centimeters(distance.getPlug("distance"), role + "Length").connectTo(owner.getPlug(role + "Length"))

        # draw = |nock - (top + bottom) / 2| - restDraw
        positions = []
        for role, node in (("top", top), ("bottom", bottom)):
            decompose = graph._node("decomposeMatrix", role + "Position")
            node.getPlug("worldMatrix")[0].connectTo(decompose.getPlug("inputMatrix"))
            positions.append(decompose.getPlug("outputTranslate"))
        middle = graph._node("plusMinusAverage", "middle")
        middle.getPlug("operation").set(3)
        for index, plug in enumerate(positions):
            plug.connectTo(middle.getPlug("input3D")[index])
        reach = graph._node("distanceBetween", "drawDistance")
        middle.getPlug("output3D").connectTo(reach.getPlug("point1"))
        nock.getPlug("worldMatrix")[0].connectTo(reach.getPlug("inMatrix2"))
        delta = graph._node("plusMinusAverage", "drawRaw")
        delta.getPlug("operation").set(2)
        centimeters(reach.getPlug("distance"), "draw").connectTo(delta.getPlug("input1D")[0])
        owner.getPlug("restDraw").connectTo(delta.getPlug("input1D")[1])
        delta.getPlug("output1D").connectTo(owner.getPlug("draw"))
        ratio = graph._node("multiplyDivide", "drawRatio")
        ratio.getPlug("operation").set(2)
        owner.getPlug("draw").connectTo(ratio.getPlug("input1X"))
        owner.getPlug("maxDraw").connectTo(ratio.getPlug("input2X"))
        weight = graph._node("clamp", "drawWeightClamp")
        weight.getPlug("maxR").set(1.0)
        ratio.getPlug("outputX").connectTo(weight.getPlug("inputR"))
        weight.getPlug("outputR").connectTo(owner.getPlug("drawWeight"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
