"""向きがコーンの中心にどれだけ一致しているかを0〜1で出力する。"""

import math

import mlib
from mlib.decorator import undoTransaction

# 矢印・コーンのローカル軸。+X をドライバーの向き・コーンの軸とする。
_AXES = {
    "x": (0, 0, 0), "-x": (0, 180, 0),
    "y": (0, 0, 90), "-y": (0, 0, -90),
    "z": (0, -90, 0), "-z": (0, 90, 0),
}
_DRIVER_COLOR = 17
_CONE_COLOR = 18


class ConeReader:
    """ドライバーの矢印とコーンのなす角から、一致度を標準DGで求める。

    ドライバー(矢印)とコーンは、それぞれ GRP の下の transform として作る。
    GRP を任意のジョイントへコンストレイントし、中の transform を回して
    向きを合わせる。出力 ``weight`` は、矢印がコーンの軸と完全に一致すると1、
    なす角がコーンの半角 ``coneAngle`` に達すると0になる。
    """

    def __init__(self, container):
        """計算ノードの所有者を保持する。

        Args:
            container (str | Node): createで生成したcontainer。
        """
        self.container = mlib.nodes.Container(container)

    @staticmethod
    def weight(angle, coneAngle, falloff="linear"):
        """なす角とコーンの半角から一致度を計算する。

        Args:
            angle (float): 矢印とコーンの軸のなす角。度。
            coneAngle (float): コーンの半角。度。0より大きい。
            falloff (str): "linear" は直線、"smooth" は両端をなめらかにする。

        Returns:
            float: 0〜1。中心で1、半角で0。
        """
        if not math.isfinite(angle) or not math.isfinite(coneAngle) or coneAngle <= 0:
            raise ValueError("angle must be finite and coneAngle positive")
        if falloff not in ("linear", "smooth"):
            raise ValueError("falloff must be linear or smooth")
        value = min(1.0, max(0.0, 1-angle/min(coneAngle, 180.0)))
        return value*value*(3-2*value) if falloff == "smooth" else value

    @classmethod
    @undoTransaction("mlrig.ConeReader.create")
    def create(cls, driverJoint=None, coneJoint=None, name="coneReader", coneAngle=45.0,
               driverAxis="x", size=1.0, falloff="linear"):
        """矢印とコーンのtransformと、一致度の計算を作る。

        Args:
            driverJoint (str | None): 矢印を追従させるジョイント。指定すると矢印の GRP を
                重ねてコンストレイントする。
            coneJoint (str | None): コーンを追従させるジョイント。指定すると、コーンの GRP を
                driverJoint の位置(なければ coneJoint の位置)に置き、coneJoint へ
                コンストレイントする。
            name (str): 一意な名前。container と transform の接頭辞。
            coneAngle (float): コーンの半角。度。0より大きく180以下。
            driverAxis (str): driverJoint のどの軸を矢印にするか。x/y/z/-x/-y/-z。
            size (float): 矢印とコーンの表示の長さ。後から container の size で変更できる。
            falloff (str): "linear" か "smooth"。後から container の falloff で変更できる。

        Returns:
            ConeReader: weight・angle を出力するcontainerの所有者。

        Note:
            作成直後はコーンの軸を矢印の向きに合わせるので、weight は1になる。
            ``<name>_cone`` を回して、weight を1にしたい向きへコーンを向ける。
            角度は向きだけで比べ、位置や距離は使わない。
        """
        if any(mlib.objExists(name) for name in [name, name + "_driver_GRP", name + "_cone_GRP"]):
            raise ValueError("Name already exists: " + name)
        if driverAxis not in _AXES:
            raise ValueError("driverAxis must be one of " + ", ".join(_AXES))
        if not math.isfinite(coneAngle) or not 0 < coneAngle <= 180:
            raise ValueError("coneAngle must be in (0, 180]")
        if not math.isfinite(size) or size <= 0:
            raise ValueError("size must be positive")
        if falloff not in ("linear", "smooth"):
            raise ValueError("falloff must be linear or smooth")
        for joint in (driverJoint, coneJoint):
            if joint is not None and not mlib.objExists(joint):
                raise ValueError("Node not found: " + str(joint))

        # 矢印。GRP をドライバーのジョイントへ重ね、中の transform で軸を選ぶ。
        driver_group = mlib.createNode("transform", name=name+"_driver_GRP", skipSelect=True)
        driver = mlib.createNode("transform", name=name+"_driver", parent=driver_group, skipSelect=True)
        driver_display = mlib.createNode("transform", name=name+"_driverDisplay", parent=driver, skipSelect=True)
        cls._arrow(driver_display)
        for attr in ("translate", "rotate"):
            driver_display.getPlug(attr).setLocked(True)
        driver.getPlug("rotate").set(_AXES[driverAxis], uiUnits=True)
        if driverJoint is not None:
            cls._attach(driver_group, driverJoint)

        # コーン。作成時は矢印と同じ位置・向きにして、weight=1 から始める。
        cone_group = mlib.createNode("transform", name=name+"_cone_GRP", skipSelect=True)
        cone = mlib.createNode("transform", name=name+"_cone", parent=cone_group, skipSelect=True)
        cone_display = mlib.createNode("transform", name=name+"_coneDisplay", parent=cone, skipSelect=True)
        cls._coneShape(cone_display)
        for attr in ("translate", "rotate"):
            cone_display.getPlug(attr).setLocked(True)
        if coneJoint is not None:
            cls._attach(cone_group, coneJoint)
        cls._setMatrix(cone, driver.getMatrix(worldSpace=True))
        cone.getPlug("scale").set((1, 1, 1))

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="coneAngle", attributeType="double", defaultValue=coneAngle,
                      minValue=0.01, maxValue=180, keyable=True)
        owner.addAttr(longName="falloff", attributeType="enum", enumName="linear:smooth",
                      defaultValue=1 if falloff == "smooth" else 0, keyable=True)
        owner.addAttr(longName="size", attributeType="double", defaultValue=size, minValue=0.001, keyable=True)
        for attr in ("weight", "angle"):
            owner.addAttr(longName=attr, attributeType="double")
            owner.setAttrFlags([attr], keyable=False, channelBox=True)
        for attr, node in (("driver", driver), ("cone", cone)):
            owner.addAttr(longName=attr, attributeType="message")
            node.getPlug("message").connectTo(owner.getPlug(attr))

        # 矢印とコーンの +X をワールドへ移し、なす角を求める。
        directions = []
        for label, node in (("driverDirection", driver), ("coneDirection", cone)):
            direction = graph._node("vectorProduct", label)
            direction.getPlug("operation").set(3)
            direction.getPlug("input1").set((1, 0, 0))
            direction.getPlug("normalizeOutput").set(True)
            node.getPlug("worldMatrix")[0].connectTo(direction.getPlug("matrix"))
            directions.append(direction)
        between = graph._node("angleBetween", "between")
        directions[0].getPlug("output").connectTo(between.getPlug("vector1"))
        directions[1].getPlug("output").connectTo(between.getPlug("vector2"))
        degrees = graph._node("unitConversion", "degrees")
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        between.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("output").connectTo(owner.getPlug("angle"))

        # 直線: clamp(1 - angle/coneAngle, 0, 1)。接続入力でも半角を正の範囲へ保つ。
        limit = graph._node("clamp", "coneAngleLimit")
        limit.getPlug("minR").set(0.01)
        limit.getPlug("maxR").set(180)
        owner.getPlug("coneAngle").connectTo(limit.getPlug("inputR"))
        ratio = graph._node("multiplyDivide", "ratio")
        ratio.getPlug("operation").set(2)
        degrees.getPlug("output").connectTo(ratio.getPlug("input1X"))
        limit.getPlug("outputR").connectTo(ratio.getPlug("input2X"))
        linear = graph._node("plusMinusAverage", "oneMinusRatio")
        linear.getPlug("operation").set(2)
        linear.getPlug("input1D")[0].set(1)
        ratio.getPlug("outputX").connectTo(linear.getPlug("input1D")[1])
        clamped = graph._node("clamp", "linear")
        clamped.getPlug("maxR").set(1)
        linear.getPlug("output1D").connectTo(clamped.getPlug("inputR"))
        # なめらか: t²(3-2t)。
        square = graph._node("multiplyDivide", "square")
        clamped.getPlug("outputR").connectTo(square.getPlug("input1X"))
        clamped.getPlug("outputR").connectTo(square.getPlug("input2X"))
        threeMinus = graph._node("plusMinusAverage", "threeMinusTwoT")
        threeMinus.getPlug("operation").set(2)
        threeMinus.getPlug("input1D")[0].set(3)
        twice = graph._node("multiplyDivide", "twoT")
        clamped.getPlug("outputR").connectTo(twice.getPlug("input1X"))
        twice.getPlug("input2X").set(2)
        twice.getPlug("outputX").connectTo(threeMinus.getPlug("input1D")[1])
        smooth = graph._node("multiplyDivide", "smooth")
        square.getPlug("outputX").connectTo(smooth.getPlug("input1X"))
        threeMinus.getPlug("output1D").connectTo(smooth.getPlug("input2X"))
        select = graph._node("condition", "falloffSelect")
        select.getPlug("secondTerm").set(1)
        owner.getPlug("falloff").connectTo(select.getPlug("firstTerm"))
        smooth.getPlug("outputX").connectTo(select.getPlug("colorIfTrueR"))
        clamped.getPlug("outputR").connectTo(select.getPlug("colorIfFalseR"))
        select.getPlug("outColorR").connectTo(owner.getPlug("weight"))

        # コーンの表示。単位コーンを x 方向 cosγ·size、yz 方向 sinγ·size に伸縮する。
        # 標準ノードに cos/sin がないので、Z軸まわりに γ 回した行列で X軸を変換して得る。
        rotation = graph._node("composeMatrix", "displayRotation")
        degreesToAngle = graph._node("unitConversion", "displayAngle")
        degreesToAngle.getPlug("conversionFactor").set(math.pi / 180)
        limit.getPlug("outputR").connectTo(degreesToAngle.getPlug("input"))
        degreesToAngle.getPlug("output").connectTo(rotation.getPlug("inputRotateZ"))
        unit = graph._node("vectorProduct", "displayCosSin")
        unit.getPlug("operation").set(3)
        unit.getPlug("input1").set((1, 0, 0))
        rotation.getPlug("outputMatrix").connectTo(unit.getPlug("matrix"))
        scaled = graph._node("multiplyDivide", "displayScale")
        for source, target in (("X", "X"), ("Y", "Y"), ("Y", "Z")):
            unit.getPlug("output"+source).connectTo(scaled.getPlug("input1"+target))
            owner.getPlug("size").connectTo(scaled.getPlug("input2"+target))
        for axis in "XYZ":
            scaled.getPlug("output"+axis).connectTo(cone_display.getPlug("scale"+axis))
            owner.getPlug("size").connectTo(driver_display.getPlug("scale"+axis))
        return graph

    @property
    def driver(self):
        """ドライバーの矢印transform名。"""
        source = self.container.getPlug("driver").getSource()
        return None if source is None else source.getNode().getName()

    @property
    def cone(self):
        """コーンのtransform名。"""
        source = self.container.getPlug("cone").getSource()
        return None if source is None else source.getNode().getName()

    def _node(self, kind, suffix):
        """内部ノードを所有containerへ登録する。

        Args:
            kind (str): 標準ノード型。
            suffix (str): 名前の用途部分。

        Returns:
            Node: 新規ノード。
        """
        node = mlib.createNode(
            kind, name=self.container.getName() + "_" + suffix, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @staticmethod
    def _curve(parent, name, points, color):
        """一次カーブのシェイプを parent へ追加する。"""
        # 点は現在の距離単位で決めているため、作成関数の内部単位(cm)へ換算して渡す。
        ui = mlib.common.units.distanceFromUi
        shape = mlib.createCurve([tuple(ui(v) for v in point) for point in points], degree=1, name=name+"__tmp")
        temporary = shape.getParent()
        shape.setParent(parent)
        temporary.delete()
        shape.rename(name)
        shape.getPlug("lineWidth").set(2)
        parent.getPlug("overrideEnabled").set(True)
        parent.getPlug("overrideColor").set(color)

    @classmethod
    def _arrow(cls, parent):
        """+X 向き・長さ1の矢印シェイプを作る。"""
        base = parent.getName().split("|")[-1]
        cls._curve(parent, base+"Shaft", [(0, 0, 0), (1, 0, 0)], _DRIVER_COLOR)
        cls._curve(parent, base+"HeadY", [(0.82, 0.09, 0), (1, 0, 0), (0.82, -0.09, 0)], _DRIVER_COLOR)
        cls._curve(parent, base+"HeadZ", [(0.82, 0, 0.09), (1, 0, 0), (0.82, 0, -0.09)], _DRIVER_COLOR)

    @classmethod
    def _coneShape(cls, parent):
        """頂点が原点、軸が +X、底面が x=1・半径1 の単位コーンのシェイプを作る。"""
        circle = [(1, math.cos(math.tau*i/24), math.sin(math.tau*i/24)) for i in range(25)]
        base = parent.getName().split("|")[-1]
        cls._curve(parent, base+"Rim", circle, _CONE_COLOR)
        for i, (y, z) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
            cls._curve(parent, base+"Side{}".format(i), [(0, 0, 0), (1, y, z)], _CONE_COLOR)
        cls._curve(parent, base+"Axis", [(0, 0, 0), (1, 0, 0)], _CONE_COLOR)

    @staticmethod
    def _setMatrix(target, matrix):
        """新規TransformへMaya標準の分解値でワールド行列を適用する。

        Args:
            target (Transform): ピボット・補助回転が既定の新規Transform。
            matrix (Matrix): 適用するワールド行列。内部距離単位cm。
        """
        # setMatrixの現在値に近いEuler解への補正を使わず、従来のxformと同じ
        # 分解規約で初期チャンネル値を保つ。数学処理と書込みはmlibへ委譲する。
        local = matrix * target.getMatrix(worldSpace=True, p=True, inv=True)
        parts = local.decompose()
        for attr, value in (("translate", parts["translate"]), ("rotate", parts["euler"]),
                            ("scale", parts["scale"]), ("shear", parts["shear"])):
            target.getPlug(attr).set(value)

    @staticmethod
    def _attach(group, joint):
        """GRP をジョイントへ重ねてから、位置と回転をコンストレイントする。"""
        ConeReader._setMatrix(group, mlib.nodes.Node(joint).getMatrix(worldSpace=True))
        group.getPlug("scale").set((1, 1, 1))
        group.addConstraint(joint, maintainOffset=True)
