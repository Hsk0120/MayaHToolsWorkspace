"""コントロールの並びから帯状のNURBSサーフェス(リボン)を作り、その上の中心線に複数の行列を出す標準DGを構築する。"""

import math


import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.controlShape import ControlShape
from mlrig.setups.twistDistribution import TwistDistribution


class Ribbon(TwistDistribution):
    """コントロールの並びを断面にした帯(リボン)と、その上を滑る行列を出す標準DG。

    各コントロールのローカルの幅方向(sideAxis)へ ±width/2 ずらした2点を結ぶ短いカーブ(断面)を作り、
    標準の ``loft`` で全ての断面を通る帯のサーフェスにする。帯の中心線(V=0.5)の上に、標準の ``uvPin`` で
    ``count`` 個の行列を置く。コントロールを回すと断面が回るので、帯のねじれもコントロールで決まる。
    スキンやfollicleを使わず、コントロールの行列から直接サーフェスを作る。
    """

    @classmethod
    @undoTransaction("mlrig.Ribbon.create")
    def create(cls, controls, count=5, name="ribbon", width=1.0, sideAxis="z"):
        """コントロールの並びからリボンと、その上の行列を生成する。

        Args:
            controls (list[str | Node]): リボンの断面にする2つ以上の異なるtransform(根元から先端の順)。
            count (int): 出力する行列の数。2以上。
            name (str): 一意なcontainer名。``<name>_grp`` もこの名前から作る。
            width (float): リボンの幅(cm)。正。containerの ``width`` で後から変えられる。
            sideAxis (str): 各コントロールのローカルで、幅の向きにする軸x/y/z。

        Returns:
            Ribbon: matrix0〜matrix<count-1>・position0〜position<count-1>・widthの所有者。
            ``group`` に、断面のカーブ(非表示)とリボンのサーフェス(テンプレート表示)をまとめたtransformを持つ。

        Raises:
            ValueError: 引数が不正な場合、またはnameが既に使われている場合。

        Note:
            断面 i = コントロール i のワールド行列で移した (+width/2・-width/2) * sideAxis の2点を結ぶ1次のカーブ。
            loftは3次(断面が2つなら1次)・uniformで、全ての断面(=全てのコントロールの位置)を通る。
            出力 i の行列 = uvPin(U=position_i, V=0.5) のワールド行列。position_i の既定値は i/(count-1)。
            Uは断面の番号を正規化した値で、弧長に比例した等間隔ではない(コントロールの間隔が偏ると出力も偏る)。
            出力の軸は X=リボンに沿う根元から先端の接線、Y=面の法線、Z=X×Y(幅のsideAxisの+側に近い向き)。
            位置はリボン上のワールド座標(cm)。scaleは1で、コントロールのscaleは帯の形にだけ効く。
            受けるtransformのoffsetParentMatrixへ直接つなぐ場合、その親はワールド(またはinheritsTransform=False)にする。
            作成直後の出力は帯の形そのもので、既存のjointの姿勢は変えない。
        """
        axes = ("x", "y", "z")
        if sideAxis not in axes:
            raise ValueError("sideAxis must be one of x, y and z")
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise ValueError("count must be an integer of 2 or more")
        width = float(width)
        if not math.isfinite(width) or width <= 0:
            raise ValueError("width must be a positive finite value")
        if any(mlib.objExists(name) for name in [name, name + "_grp"]):
            raise ValueError("Ribbon container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in controls]
        if len(nodes) < 2 or len({node.getUuid() for node in nodes}) != len(nodes) or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected two or more different transforms for the controls")
        side = Vector([float(axis == sideAxis) for axis in axes])

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="width", attributeType="double", defaultValue=width, minValue=1e-6,
                      keyable=True)
        for index in range(count):
            owner.addAttr(longName="position" + str(index), attributeType="double",
                          defaultValue=index / (count - 1.0), minValue=0.0, maxValue=1.0, keyable=True)
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        group = mlib.createNode("transform", name=name + "_grp", skipSelect=True)
        # カーブとサーフェスはワールド座標の制御点で作るので、親の移動を受け取らない。
        group.getPlug("inheritsTransform").set(False)
        owner.addMembers(group)

        # 幅の半分だけ幅の向きへずらす行列(-側と+側)。width はcontainerから受ける。
        offsets = []
        for role, sign in (("minus", -0.5), ("plus", 0.5)):
            half = graph._node("multiplyDivide", role + "HalfWidth")
            owner.getPlug("width").connectTo(half.getPlug("input1X"))
            half.getPlug("input2X").set(sign)
            compose = graph._node("composeMatrix", role + "Offset")
            # widthはcmの値として扱う。Mayaが距離単位の変換を自動で挟まないよう、係数1の変換を明示する。
            centimeters = graph._node("unitConversion", role + "HalfWidthCentimeters")
            centimeters.getPlug("conversionFactor").set(1.0)
            half.getPlug("outputX").connectTo(centimeters.getPlug("input"))
            centimeters.getPlug("output").connectTo(compose.getPlug("inputTranslate" + sideAxis.upper()))
            offsets.append((role, sign, compose.getPlug("outputMatrix")))

        # コントロールごとに、幅の+側から-側へ向かう1次の短いカーブ(断面)を作る。
        # この向きにすると、出力のZ(=X×法線Y)が幅のsideAxisの+側を向く。
        offsets = offsets[::-1]
        loft = graph._node("loft", "loft")
        loft.getPlug("degree").set(1 if len(nodes) == 2 else 3)
        loft.getPlug("uniform").set(True)
        # 既定の自動反転は、断面が90度を超えてねじれると断面の向きを裏返し、面の法線が反転するので切る。
        loft.getPlug("autoReverse").set(False)
        for index, node in enumerate(nodes):
            world = Matrix(node.getPlug("worldMatrix")[0].get())
            points = []
            for _, sign, _ in offsets:
                # 生成時の制御点(接続後はDGの値で置き換わる)。v*m は方向の変換なので位置を足す。
                point = Vector(world.translate) + Vector(side * (sign * width)) * world
                points.append((point.x, point.y, point.z))
            curve_name = "{}_section{}".format(name, index)
            curve = mlib.createNode("transform", name=curve_name, parent=group, skipSelect=True)
            ControlShape.replaceCurves(curve, points, [0.0, 1.0], degree=1, name=curve_name)
            shape = curve.getShapes()[0]
            curve.getPlug("visibility").set(False)
            owner.addMembers(curve, shape)
            for cv, (role, _, offset) in enumerate(offsets):
                point = graph._node("multMatrix", "{}Point{}".format(role, index))
                offset.connectTo(point.getPlug("matrixIn")[0])
                node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrixIn")[1])
                position = graph._node("decomposeMatrix", "{}Position{}".format(role, index))
                point.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
                position.getPlug("outputTranslate").connectTo(shape.getPlug("controlPoints")[cv])
            shape.getPlug("local").connectTo(loft.getPlug("inputCurve")[index])
        surface = mlib.createNode("transform", name=name + "_surface", parent=group, skipSelect=True)
        surface_shape = mlib.createNode("nurbsSurface", name=name + "_surfaceShape", parent=surface,
                                        skipSelect=True)
        loft.getPlug("outputSurface").connectTo(surface_shape.getPlug("create"))
        # 形の確認用。レンダリング・選択の対象にしない。
        surface.getPlug("overrideEnabled").set(True)
        surface.getPlug("overrideDisplayType").set(1)
        owner.addMembers(surface, surface_shape)

        pin = graph._node("uvPin", "pin")
        loft.getPlug("outputSurface").connectTo(pin.getPlug("deformedGeometry"))
        pin.getPlug("normalizedIsoParms").set(True)
        # 出力のX = U方向の接線(リボンに沿う向き)、Y = 面の法線、Z = X×Y(幅の+側)。
        pin.getPlug("normalAxis").set(1)
        pin.getPlug("tangentAxis").set(0)
        for index in range(count):
            owner.getPlug("position" + str(index)).connectTo(
                mlib.getPlug("{}.coordinate[{}].coordinateU".format(pin, index)))
            mlib.getPlug("{}.coordinate[{}].coordinateV".format(pin, index)).set(0.5)
            pin.getPlug("outputMatrix")[index].connectTo(owner.getPlug("matrix" + str(index)))
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        graph.group = group.getFullName()
        return graph

    @property
    def group(self):
        """カーブとサーフェスをまとめたtransformのフルパス。

        Returns:
            str | None: ``<container名>_grp`` のフルパス。無ければNone。
        """
        value = getattr(self, "_group", None)
        if value is None:
            found = mlib.ls(self.container.getName() + "_grp")
            value = found[0].getFullName() if found else None
        return value

    @group.setter
    def group(self, value):
        """生成時にまとめのtransformを記録する。

        Args:
            value (str): フルパス。
        """
        self._group = value
