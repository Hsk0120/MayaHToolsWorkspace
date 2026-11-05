"""膝蓋骨(パテラ)を、長さ一定の膝蓋腱に引かれて大腿骨の溝の円弧に沿って滑らせる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.crossedKneeLinkage import _frame
from mlrig.setups.fourBarLinkage import FourBarLinkage, _position, _translation


class PatellaFollow(FourBarLinkage):
    """膝蓋骨を「大腿骨の溝の円」と「脛骨粗面を中心とする膝蓋腱の長さの円」の交点に置く標準DG。

    大腿骨(femur)の空間で、溝の中心を G、溝の半径を r(G から膝蓋骨までの距離)、膝蓋腱の長さを L、
    脛骨粗面(膝蓋腱の脛骨側の付着点)の現在の位置を T とすると、膝蓋骨の位置 P は「G を中心に半径 r の円」と
    「T を中心に半径 L の円」の交点になる。交点は FourBarLinkage と同じ2円の交点のグラフで求め、枝は生成時の
    配置で固定する。脛骨は入力のtransformのワールド行列をそのまま読むので、膝のIK・FKのどちらで曲げても追従する。
    膝蓋骨の向きは、生成時の向きを G の回りに (P0 - G) から (P - G) への回転だけ回したものにする。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def patellaPose(cls, groove, patella, restTuberosity, tuberosity, normal, grooveRadius=None, tendonLength=None):
        """脛骨粗面が tuberosity にあるときの膝蓋骨の位置・溝の上の角度を計算する(DGと同じ式のPython版)。

        Args:
            groove (Sequence[float]): 溝の中心 G(大腿骨の空間)。
            patella (Sequence[float]): 生成時の膝蓋骨の位置 P0。
            restTuberosity (Sequence[float]): 生成時の脛骨粗面 T0。枝の向きと既定の膝蓋腱の長さに使う。
            tuberosity (Sequence[float]): 現在の脛骨粗面の位置 T。
            normal (Sequence[float]): 曲げの面の法線 n。
            grooveRadius (float | None): 溝の半径 r。None なら |P0 - G|。
            tendonLength (float | None): 膝蓋腱の長さ L。None なら |T0 - P0|。

        Returns:
            tuple: 膝蓋骨の位置 P(tuple[float, float, float])、届かない量 excess(float)、
            n 回りの右ねじを正とした溝の上の角度(度、float)。
        """
        g_point, p_rest, t_rest, t_point = (Vector(*value) for value in (groove, patella, restTuberosity,
                                                                         tuberosity))
        plane = Vector(*normal).normal()
        radial = p_rest - g_point
        radius = radial.length() if grooveRadius is None else float(grooveRadius)
        length = (t_rest - p_rest).length() if tendonLength is None else float(tendonLength)
        branch = 1.0 if radial * (plane ^ (t_rest - g_point).normal()) >= 0.0 else -1.0
        point, excess = cls.jointPosition(g_point, t_point, radius, length, plane, branch)
        second = Vector(*point) - g_point
        angle = math.degrees(math.atan2((radial ^ second) * plane, radial * second))
        return point, excess, angle

    @classmethod
    @undoTransaction("mlrig.PatellaFollow.create")
    def create(cls, femur, tibia, groove, patella, tuberosity, name="patellaFollow", normal=None):
        """大腿骨・脛骨と溝の中心・膝蓋骨・脛骨粗面から、膝蓋骨と膝蓋腱のワールド行列を生成する。

        Args:
            femur (str | Node): 大腿骨のtransform。そのワールド行列を溝の空間にする。
            tibia (str | Node): 脛骨のtransform。そのワールド行列を接続し、脛骨粗面を一緒に動かす。
            groove (str | Node): 溝の中心 G を示すtransform(生成時の位置だけを読む)。
            patella (str | Node): 膝蓋骨のtransform。生成時の位置と向きを基準にする(読むだけで接続しない)。
            tuberosity (str | Node): 脛骨粗面(膝蓋腱の脛骨側の付着点)を示すtransform(生成時の位置だけを読む)。
            name (str): 一意なcontainer名。
            normal (Sequence[float] | None): 曲げの面の法線(大腿骨の空間)。溝の角度はこの軸回りの右ねじが正。
                None なら ``(P0 - G) × (T0 - P0)`` 。

        Returns:
            PatellaFollow: patellaMatrix・tendonMatrix・grooveAngle・excess の所有者。
            containerに grooveRadius・tendonLength(長さ)をkeyableで持つ。

        Raises:
            ValueError: 引数がtransformでない場合、点が重なる場合、3点が一直線で normal が無い場合、
                normal が不正な場合、またはnameが既に存在する場合。

        Note:
            T = T0' * W_tibia * S^-1(T0' は生成時の脛骨のローカルでの脛骨粗面、W_tibia は脛骨の worldMatrix、
            S は大腿骨の worldMatrix)。P = 2円の交点(G, r)・(T, L)。
            patellaMatrix = M0 * T(-P0) * R * T(P) * S。M0 は生成時の膝蓋骨の大腿骨の空間での行列、R は
            ``angleBetween`` が返す (P0 - G) から (P - G) への回転。tendonMatrix は P に置き、X を T へ、Z を n へ
            向けた行列。どちらもワールド行列なので、ワールド直下のtransformの offsetParentMatrix へ接続する。
            P が作れない(|T - G| > r + L または < |r - L|)場合、P は G から T への線の上の最も近い点に止まり、
            excess にその長さを出す。grooveAngle は溝の上で生成時から回った角度(n 回りの右ねじが正)。
        """
        if mlib.objExists(name):
            raise ValueError("PatellaFollow container already exists: " + name)
        nodes = []
        for label, value in (("femur", femur), ("tibia", tibia), ("groove", groove), ("patella", patella),
                             ("tuberosity", tuberosity)):
            node = mlib.Node(value)
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected a transform for the " + label)
            nodes.append(node)
        femur, tibia, groove, patella, tuberosity = nodes
        if femur == tibia:
            raise ValueError("femur and tibia must be different transforms")

        space = Matrix(femur.getPlug("worldMatrix")[0].get())
        inverse = space.inverse()
        g_point, p_rest, t_rest = (_position(Matrix(node.getPlug("worldMatrix")[0].get()) * inverse)
                                   for node in (groove, patella, tuberosity))
        radial = p_rest - g_point
        tendon = t_rest - p_rest
        radius = radial.length()
        length = tendon.length()
        if min(radius, length, (t_rest - g_point).length()) < 1e-6:
            raise ValueError("The groove, patella and tuberosity must be at different positions")
        if normal is None:
            plane = radial ^ tendon
            if plane.length() < 1e-6 * radius * length:
                raise ValueError("The groove, patella and tuberosity are in a line; pass normal")
        else:
            values = [float(value) for value in normal]
            if len(values) != 3 or not all(math.isfinite(value) for value in values):
                raise ValueError("normal must be a finite 3D vector")
            plane = Vector(*values)
            if plane.length() < 1e-9:
                raise ValueError("normal must not be a zero vector")
        plane = plane.normal()
        u = (t_rest - g_point).normal()
        branch = 1.0 if radial * (plane ^ u) >= 0.0 else -1.0
        patella_rest = Matrix(patella.getPlug("worldMatrix")[0].get()) * inverse
        tibia_world = Matrix(tibia.getPlug("worldMatrix")[0].get())
        t_local = _position(_translation(t_rest) * space * tibia_world.inverse())

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="grooveRadius", attributeType="doubleLinear", defaultValue=radius, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="tendonLength", attributeType="doubleLinear", defaultValue=length, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="grooveAngle", attributeType="doubleAngle")
        owner.addAttr(longName="excess", attributeType="doubleLinear")
        for attribute in ("patellaMatrix", "tendonMatrix"):
            owner.addAttr(longName=attribute, dataType="matrix")

        # T = T0' * W_tibia * S^-1。vectorProduct・plusMinusAverage は単位なしなので cm のまま。
        relative = graph._node("multMatrix", "tibiaInFemur")
        tibia.getPlug("worldMatrix")[0].connectTo(relative.getPlug("matrixIn")[0])
        femur.getPlug("worldInverseMatrix")[0].connectTo(relative.getPlug("matrixIn")[1])
        carried = graph._node("vectorProduct", "tuberosityPoint")
        carried.getPlug("operation").set(4)
        carried.getPlug("input1").set(tuple(t_local))
        relative.getPlug("matrixSum").connectTo(carried.getPlug("matrix"))
        toward = graph._node("plusMinusAverage", "towardTuberosity")
        toward.getPlug("operation").set(2)
        carried.getPlug("output").connectTo(toward.getPlug("input3D")[0])
        toward.getPlug("input3D")[1].set(tuple(g_point))
        anchor = graph._node("plusMinusAverage", "grooveCenter")
        anchor.getPlug("input3D")[0].set(tuple(g_point))

        # 溝の半径 r・膝蓋腱の長さ L は係数1の unitConversion で数値にする。
        lengths = []
        for attribute in ("grooveRadius", "tendonLength"):
            plain = graph._node("unitConversion", attribute + "Number")
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug(attribute).connectTo(plain.getPlug("input"))
            lengths.append(plain.getPlug("output"))
        joint, distance, squares = graph._intersectionGraph(anchor.getPlug("output3D"), toward.getPlug("output3D"),
                                                            lengths[0], lengths[1], plane, branch)
        p_point = joint.getPlug("output3D")
        excess = graph._node("unitConversion", "excessLength")
        excess.getPlug("conversionFactor").set(1.0)
        graph._excessGraph(distance, lengths[0], lengths[1], squares).connectTo(excess.getPlug("input"))
        excess.getPlug("output").connectTo(owner.getPlug("excess"))

        # R = (P0 - G) から (P - G) への最短回転。溝の面の中なら n 回りの回転になる。
        radial_now = graph._node("plusMinusAverage", "radial")
        radial_now.getPlug("operation").set(2)
        p_point.connectTo(radial_now.getPlug("input3D")[0])
        radial_now.getPlug("input3D")[1].set(tuple(g_point))
        between = graph._node("angleBetween", "grooveTurn")
        between.getPlug("vector1").set(tuple(radial))
        radial_now.getPlug("output3D").connectTo(between.getPlug("vector2"))
        turn = graph._node("composeMatrix", "grooveRotation")
        between.getPlug("euler").connectTo(turn.getPlug("inputRotate"))

        # grooveAngle = sign(axis・n) * angle。符号は condition、掛け算は角度の単位を保つ animBlendNodeAdditiveDA。
        side = graph._node("vectorProduct", "turnSide")
        side.getPlug("operation").set(1)
        between.getPlug("axis").connectTo(side.getPlug("input1"))
        side.getPlug("input2").set(tuple(plane))
        sign = graph._node("condition", "turnSign")
        sign.getPlug("operation").set(4)
        side.getPlug("outputX").connectTo(sign.getPlug("firstTerm"))
        sign.getPlug("secondTerm").set(0.0)
        sign.getPlug("colorIfTrueR").set(-1.0)
        sign.getPlug("colorIfFalseR").set(1.0)
        signed = graph._node("animBlendNodeAdditiveDA", "grooveAngle")
        between.getPlug("angle").connectTo(signed.getPlug("inputA"))
        sign.getPlug("outColorR").connectTo(signed.getPlug("weightA"))
        signed.getPlug("weightB").set(0.0)
        signed.getPlug("output").connectTo(owner.getPlug("grooveAngle"))

        # patellaMatrix = M0 * T(-P0) * R * T(P) * S。
        translate = graph._node("fourByFourMatrix", "patellaTranslate")
        for index in range(3):
            p_point.getChildren()[index].connectTo(translate.getPlug("in3{}".format(index)))
        chain = graph._node("multMatrix", "patellaMatrix")
        chain.getPlug("matrixIn")[0].set(patella_rest * _translation(-p_rest))
        turn.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[1])
        translate.getPlug("output").connectTo(chain.getPlug("matrixIn")[2])
        femur.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[3])
        chain.getPlug("matrixSum").connectTo(owner.getPlug("patellaMatrix"))

        # 膝蓋腱: P に置いた枠の X を脛骨粗面(ワールド)へ、Z を n へ揃える。
        origin = graph._node("multMatrix", "tendonInput")
        origin.getPlug("matrixIn")[0].set(_frame(Vector(0.0, 0.0, 0.0), tendon, plane))
        translate.getPlug("output").connectTo(origin.getPlug("matrixIn")[1])
        femur.getPlug("worldMatrix")[0].connectTo(origin.getPlug("matrixIn")[2])
        target = graph._node("multMatrix", "tuberosityWorld")
        target.getPlug("matrixIn")[0].set(_translation(t_local))
        tibia.getPlug("worldMatrix")[0].connectTo(target.getPlug("matrixIn")[1])
        aimer = graph._node("aimMatrix", "tendonAim")
        origin.getPlug("matrixSum").connectTo(aimer.getPlug("inputMatrix"))
        aimer.getPlug("primaryMode").set(1)
        aimer.getPlug("primaryInputAxis").set((1.0, 0.0, 0.0))
        aimer.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        target.getPlug("matrixSum").connectTo(aimer.getPlug("primaryTargetMatrix"))
        aimer.getPlug("secondaryMode").set(2)
        aimer.getPlug("secondaryInputAxis").set((0.0, 0.0, 1.0))
        aimer.getPlug("secondaryTargetVector").set(tuple(plane))
        femur.getPlug("worldMatrix")[0].connectTo(aimer.getPlug("secondaryTargetMatrix"))
        aimer.getPlug("outputMatrix").connectTo(owner.getPlug("tendonMatrix"))
        owner.setAttrFlags(["grooveAngle", "excess", "patellaMatrix", "tendonMatrix"], keyable=False)
        return graph
