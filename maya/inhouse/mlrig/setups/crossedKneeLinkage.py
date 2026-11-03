"""十字に交差する2本の靭帯(四節リンク)で、膝の曲げに転がりと滑りを伴わせる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Quaternion, Vector

from mlrig.setups.fourBarLinkage import FourBarLinkage, _position, _translation

# 2本の靭帯の向きの外積がこれより小さければ平行とみなし、瞬間回転中心の分母をこの値にする。
_PARALLEL_EPSILON = 1e-9


def _frame(origin, aim, normal):
    """X を aim、Z を normal へ向けた、origin に置く正規直交の行列。"""
    x = aim.normal()
    z = normal.normal()
    y = z ^ x
    return Matrix.fromAxes(x, y, z, position=origin)


def _rotation(normal, degrees):
    """normal 回りに degrees だけ右ねじの向きへ回す行列(om2と同じ行ベクトルの規約)。"""
    return Matrix(Quaternion(math.radians(degrees), Vector(*normal).normal()).asMatrix())


class CrossedKneeLinkage(FourBarLinkage):
    """大腿骨側の2点と脛骨側の2点を、交差する2本の靭帯(前十字・後十字)で繋いだ四節リンクの標準DG。

    大腿骨(femur)の空間で、前の靭帯を A(大腿骨側)→ B(脛骨側)、後ろの靭帯を D(大腿骨側)→ C(脛骨側)とする。
    膝の曲げ角 θ を脛骨の大腿骨に対する回転として与え、脛骨上のベクトル v = (C0 - B0) R(θ) を回すと、
    B は「A を中心に半径 a の円」と「D - v を中心に半径 p の円」の交点になる(C = B + v が D から p の距離にあるため)。
    交点は FourBarLinkage と同じ2円の交点のグラフで求め、枝は生成時の配置で固定する。脛骨は B を基準に回転 R(θ) で
    動かすので、曲げると回転の中心(2本の靭帯の線の交点、瞬間回転中心)が後ろへ移り、転がりと滑りが同時に起こる。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def tibiaPose(cls, aclFemur, aclTibia, pclFemur, pclTibia, flexion, normal, branch=1.0, aclLength=None,
                  pclLength=None):
        """曲げ角 flexion での脛骨側の2点と瞬間回転中心を計算する(DGと同じ式のPython版)。

        Args:
            aclFemur (Sequence[float]): 前の靭帯の大腿骨側の点 A(大腿骨の空間)。
            aclTibia (Sequence[float]): 前の靭帯の脛骨側の点 B の生成時の位置。
            pclFemur (Sequence[float]): 後ろの靭帯の大腿骨側の点 D。
            pclTibia (Sequence[float]): 後ろの靭帯の脛骨側の点 C の生成時の位置。
            flexion (float): 曲げ角 θ(度)。normal 回りの右ねじの向きが正。
            normal (Sequence[float]): 曲げの面の法線 n。
            branch (float): 枝の向き s。+1 または -1。
            aclLength (float | None): 前の靭帯の長さ a。None なら |B0 - A|。
            pclLength (float | None): 後ろの靭帯の長さ p。None なら |C0 - D|。

        Returns:
            tuple: 脛骨側の点 B・C(各 tuple[float, float, float])、届かない量 excess(float)、
            瞬間回転中心(tuple[float, float, float])。
        """
        a_point, b_rest, d_point, c_rest = (Vector(*value) for value in (aclFemur, aclTibia, pclFemur, pclTibia))
        acl = (b_rest - a_point).length() if aclLength is None else float(aclLength)
        pcl = (c_rest - d_point).length() if pclLength is None else float(pclLength)
        v = (c_rest - b_rest) * _rotation(normal, flexion)
        other = d_point - v
        b_point, excess = cls.jointPosition(a_point, other, acl, pcl, normal, branch)
        b_point = Vector(*b_point)
        c_point = b_point + v
        center = cls._crossing(a_point, b_point, d_point, c_point, Vector(*normal).normal())
        return tuple(b_point), tuple(c_point), excess, tuple(center)

    @staticmethod
    def _crossing(a_point, b_point, d_point, c_point, normal):
        """線 A + t(B - A) と線 D + u(C - D) の交点(瞬間回転中心)。平行なら分母を下限にする。"""
        first = b_point - a_point
        second = c_point - d_point
        denominator = (first ^ second) * normal
        if abs(denominator) < _PARALLEL_EPSILON:
            denominator = _PARALLEL_EPSILON
        t = (((d_point - a_point) ^ second) * normal) / denominator
        return a_point + first * t

    @classmethod
    @undoTransaction("mlrig.CrossedKneeLinkage.create")
    def create(cls, femur, tibia, aclFemur, aclTibia, pclFemur, pclTibia, name="crossedKneeLinkage", normal=None):
        """大腿骨・脛骨と靭帯の4つの付着点から、曲げ角 flexion で動く脛骨と2本の靭帯のワールド行列を生成する。

        Args:
            femur (str | Node): 大腿骨のtransform。そのワールド行列を機構の空間にする。
            tibia (str | Node): 脛骨のtransform。生成時の姿勢を曲げ角0の基準にする。位置だけを読み、接続しない。
            aclFemur (str | Node): 前の靭帯の大腿骨側の付着点 A を示すtransform(生成時の位置だけを読む)。
            aclTibia (str | Node): 前の靭帯の脛骨側の付着点 B を示すtransform(同上)。
            pclFemur (str | Node): 後ろの靭帯の大腿骨側の付着点 D を示すtransform(同上)。
            pclTibia (str | Node): 後ろの靭帯の脛骨側の付着点 C を示すtransform(同上)。
            name (str): 一意なcontainer名。
            normal (Sequence[float] | None): 曲げの面の法線(大腿骨の空間)。曲げ角はこの軸回りの右ねじが正。
                None なら ``(B - A) × (C - D)`` (2本の靭帯の向きの外積)。

        Returns:
            CrossedKneeLinkage: tibiaMatrix・aclMatrix・pclMatrix・instantCenterMatrix・excess の所有者。
            containerに flexion(角度)・aclLength・pclLength(長さ)をkeyableで持つ。

        Raises:
            ValueError: 引数がtransformでない場合、付着点が重なる場合、靭帯が平行で normal が無い場合、
                normal が不正な場合、またはnameが既に存在する場合。

        Note:
            v = (C0 - B0) R(θ)、B = 2円の交点(A, a)・(D - v, p)、C = B + v。
            tibiaMatrix = T0 * T(-B0) * R(θ) * T(B) * S。T0 は生成時の脛骨の大腿骨の空間での行列、S は大腿骨の
            worldMatrix。aclMatrix・pclMatrix は A・D に置き、X を B・C へ、Z を n へ向けた行列。
            instantCenterMatrix は2本の靭帯の線の交点の平行移動に S を掛けた行列。どれもワールド行列なので、
            ワールド直下のtransformの offsetParentMatrix へ接続する。B が作れない(|D - v - A| > a + p または
            < |a - p|)場合、B は A から D - v への線の上の最も近い点に止まり、excess にその長さを出す。
        """
        if mlib.objExists(name):
            raise ValueError("CrossedKneeLinkage container already exists: " + name)
        nodes = []
        for label, value in (("femur", femur), ("tibia", tibia), ("aclFemur", aclFemur), ("aclTibia", aclTibia),
                             ("pclFemur", pclFemur), ("pclTibia", pclTibia)):
            node = mlib.nodes.Node(value)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected a transform for the " + label)
            nodes.append(node)
        femur, tibia = nodes[0], nodes[1]

        space = Matrix(femur.getPlug("worldMatrix")[0].get())
        inverse = space.inverse()
        a_point, b_rest, d_point, c_rest = (_position(Matrix(node.getPlug("worldMatrix")[0].get()) * inverse)
                                            for node in nodes[2:])
        acl_vector = b_rest - a_point
        pcl_vector = c_rest - d_point
        tibia_vector = c_rest - b_rest
        acl_length = acl_vector.length()
        pcl_length = pcl_vector.length()
        if min(acl_length, pcl_length, tibia_vector.length(), (d_point - a_point).length()) < 1e-6:
            raise ValueError("The four attachment points must be at different positions")
        if normal is None:
            plane = acl_vector ^ pcl_vector
            if plane.length() < 1e-6 * acl_length * pcl_length:
                raise ValueError("The two ligaments are parallel; pass normal")
        else:
            values = [float(value) for value in normal]
            if len(values) != 3 or not all(math.isfinite(value) for value in values):
                raise ValueError("normal must be a finite 3D vector")
            plane = Vector(*values)
            if plane.length() < 1e-9:
                raise ValueError("normal must not be a zero vector")
        plane = plane.normal()
        u = (d_point - tibia_vector - a_point).normal()
        branch = 1.0 if acl_vector * (plane ^ u) >= 0.0 else -1.0
        tibia_rest = Matrix(tibia.getPlug("worldMatrix")[0].get()) * inverse

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="flexion", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="aclLength", attributeType="doubleLinear", defaultValue=acl_length, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="pclLength", attributeType="doubleLinear", defaultValue=pcl_length, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="excess", attributeType="doubleLinear")
        for attribute in ("tibiaMatrix", "aclMatrix", "pclMatrix", "instantCenterMatrix"):
            owner.addAttr(longName=attribute, dataType="matrix")

        # R(θ) = F^T * Rz(θ) * F。F は Z を n にした正規直交の枠で、composeMatrix の Z 回りの回転を n 回りへ移す。
        across = tibia_vector - plane * (tibia_vector * plane)
        if across.length() < 1e-6 * tibia_vector.length():
            across = Vector(1.0, 0.0, 0.0) if abs(plane[0]) < 0.9 else Vector(0.0, 1.0, 0.0)
            across = across - plane * (across * plane)
        basis = _frame(Vector(0.0, 0.0, 0.0), across, plane)
        turn = graph._node("composeMatrix", "flexionTurn")
        owner.getPlug("flexion").connectTo(turn.getPlug("inputRotateZ"))
        rotation = graph._node("multMatrix", "flexionRotation")
        rotation.getPlug("matrixIn")[0].set(basis.transpose())
        turn.getPlug("outputMatrix").connectTo(rotation.getPlug("matrixIn")[1])
        rotation.getPlug("matrixIn")[2].set(basis)
        rotated = rotation.getPlug("matrixSum")

        # v = (C0 - B0) R、w = (D - v) - A = (D - A) - v。vectorProduct・plusMinusAverage は単位なしなので cm のまま。
        vector = graph._node("vectorProduct", "tibiaVector")
        vector.getPlug("operation").set(3)
        vector.getPlug("input1").set(tuple(tibia_vector))
        rotated.connectTo(vector.getPlug("matrix"))
        toward = graph._node("plusMinusAverage", "towardCenter")
        toward.getPlug("operation").set(2)
        toward.getPlug("input3D")[0].set(tuple(d_point - a_point))
        vector.getPlug("output").connectTo(toward.getPlug("input3D")[1])
        anchor = graph._node("plusMinusAverage", "aclFemurPoint")
        anchor.getPlug("input3D")[0].set(tuple(a_point))

        # 靭帯の長さ a・p は係数1の unitConversion で数値にする。
        lengths = []
        for attribute in ("aclLength", "pclLength"):
            plain = graph._node("unitConversion", attribute + "Number")
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug(attribute).connectTo(plain.getPlug("input"))
            lengths.append(plain.getPlug("output"))
        acl, pcl = lengths
        joint, distance, squares = graph._intersectionGraph(anchor.getPlug("output3D"), toward.getPlug("output3D"),
                                                            acl, pcl, plane, branch)
        b_point = joint.getPlug("output3D")
        c_sum = graph._node("plusMinusAverage", "pclTibiaPoint")
        b_point.connectTo(c_sum.getPlug("input3D")[0])
        vector.getPlug("output").connectTo(c_sum.getPlug("input3D")[1])
        c_point = c_sum.getPlug("output3D")

        excess = graph._node("unitConversion", "excessLength")
        excess.getPlug("conversionFactor").set(1.0)
        graph._excessGraph(distance, acl, pcl, squares).connectTo(excess.getPlug("input"))
        excess.getPlug("output").connectTo(owner.getPlug("excess"))

        def carry(point, suffix):
            """大腿骨の空間の点を T(point) * S のワールド行列にする。"""
            translate = graph._node("fourByFourMatrix", suffix + "Translate")
            for index, letter in enumerate("xyz"):
                point.getChildren()[index].connectTo(translate.getPlug("in3{}".format(index)))
            chain = graph._node("multMatrix", suffix + "World")
            translate.getPlug("output").connectTo(chain.getPlug("matrixIn")[0])
            femur.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[1])
            return translate, chain.getPlug("matrixSum")

        # tibiaMatrix = T0 * T(-B0) * R * T(B) * S。
        b_translate, b_world = carry(b_point, "aclTibia")
        tibiaChain = graph._node("multMatrix", "tibiaMatrix")
        tibiaChain.getPlug("matrixIn")[0].set(tibia_rest * _translation(-b_rest))
        rotated.connectTo(tibiaChain.getPlug("matrixIn")[1])
        b_translate.getPlug("output").connectTo(tibiaChain.getPlug("matrixIn")[2])
        femur.getPlug("worldMatrix")[0].connectTo(tibiaChain.getPlug("matrixIn")[3])
        tibiaChain.getPlug("matrixSum").connectTo(owner.getPlug("tibiaMatrix"))
        _, c_world = carry(c_point, "pclTibia")

        # 靭帯: 大腿骨側の点に置いた枠の X を脛骨側の点へ、Z を n へ揃える。
        for suffix, origin, aim, target, output in (("aclAim", a_point, acl_vector, b_world, "aclMatrix"),
                                                    ("pclAim", d_point, pcl_vector, c_world, "pclMatrix")):
            chain = graph._node("multMatrix", suffix + "Input")
            chain.getPlug("matrixIn")[0].set(_frame(origin, aim, plane))
            femur.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[1])
            aimer = graph._node("aimMatrix", suffix)
            chain.getPlug("matrixSum").connectTo(aimer.getPlug("inputMatrix"))
            aimer.getPlug("primaryMode").set(1)
            aimer.getPlug("primaryInputAxis").set((1.0, 0.0, 0.0))
            aimer.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
            target.connectTo(aimer.getPlug("primaryTargetMatrix"))
            aimer.getPlug("secondaryMode").set(2)
            aimer.getPlug("secondaryInputAxis").set((0.0, 0.0, 1.0))
            aimer.getPlug("secondaryTargetVector").set(tuple(plane))
            femur.getPlug("worldMatrix")[0].connectTo(aimer.getPlug("secondaryTargetMatrix"))
            aimer.getPlug("outputMatrix").connectTo(owner.getPlug(output))

        # 瞬間回転中心 = A + t e1、t = ((D - A) × e2)・n / ((e1 × e2)・n)、e1 = B - A、e2 = C - D。
        first = graph._node("plusMinusAverage", "aclDirection")
        first.getPlug("operation").set(2)
        b_point.connectTo(first.getPlug("input3D")[0])
        first.getPlug("input3D")[1].set(tuple(a_point))
        second = graph._node("plusMinusAverage", "pclDirection")
        second.getPlug("operation").set(2)
        c_point.connectTo(second.getPlug("input3D")[0])
        second.getPlug("input3D")[1].set(tuple(d_point))
        terms = []
        for suffix, left in (("crossNumerator", None), ("crossDenominator", first.getPlug("output3D"))):
            cross = graph._node("vectorProduct", suffix + "Cross")
            cross.getPlug("operation").set(2)
            if left is None:
                cross.getPlug("input1").set(tuple(d_point - a_point))
            else:
                left.connectTo(cross.getPlug("input1"))
            second.getPlug("output3D").connectTo(cross.getPlug("input2"))
            dot = graph._node("vectorProduct", suffix)
            dot.getPlug("operation").set(1)
            cross.getPlug("output").connectTo(dot.getPlug("input1"))
            dot.getPlug("input2").set(tuple(plane))
            terms.append(dot.getPlug("outputX"))
        numerator, denominator = terms
        # 平行(|分母| < 1e-9)なら分母を 1e-9 にする。
        magnitude = graph._node("multiplyDivide", "denominatorSquared")
        denominator.connectTo(magnitude.getPlug("input1X"))
        denominator.connectTo(magnitude.getPlug("input2X"))
        guard = graph._node("condition", "parallelGuard")
        guard.getPlug("operation").set(4)
        magnitude.getPlug("outputX").connectTo(guard.getPlug("firstTerm"))
        guard.getPlug("secondTerm").set(_PARALLEL_EPSILON * _PARALLEL_EPSILON)
        guard.getPlug("colorIfTrueR").set(_PARALLEL_EPSILON)
        denominator.connectTo(guard.getPlug("colorIfFalseR"))
        ratio = graph._node("multiplyDivide", "crossingRatio")
        ratio.getPlug("operation").set(2)
        numerator.connectTo(ratio.getPlug("input1X"))
        guard.getPlug("outColorR").connectTo(ratio.getPlug("input2X"))
        along = graph._node("multiplyDivide", "crossingOffset")
        first.getPlug("output3D").connectTo(along.getPlug("input1"))
        for letter in "XYZ":
            ratio.getPlug("outputX").connectTo(along.getPlug("input2" + letter))
        crossing = graph._node("plusMinusAverage", "instantCenter")
        crossing.getPlug("input3D")[0].set(tuple(a_point))
        along.getPlug("output").connectTo(crossing.getPlug("input3D")[1])
        _, center_world = carry(crossing.getPlug("output3D"), "instantCenter")
        center_world.connectTo(owner.getPlug("instantCenterMatrix"))
        owner.setAttrFlags(["excess", "tibiaMatrix", "aclMatrix", "pclMatrix", "instantCenterMatrix"],
                           keyable=False)
        return graph
