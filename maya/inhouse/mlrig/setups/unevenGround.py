"""平らな床で付けた足と腰の動きを、凹凸のある地面へ接地させる後処理の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix, Quaternion, Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 地面の法線・足の前に使える局所の軸。
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0),
        "-x": (-1.0, 0.0, 0.0), "-y": (0.0, -1.0, 0.0), "-z": (0.0, 0.0, -1.0)}

#: 法線の上向きの成分の下限。地面が垂直に近づいても割り算が発散しないようにする。
_MIN_UP = 0.05

_SIDES = ("left", "right")


def _number(value, label):
    """有限の数かを確かめて float にする。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("{} must be a finite number: {}".format(label, value))
    return float(value)


def _transform(item, label):
    """既存の transform・joint の Node に解決する。"""
    node = item if isinstance(item, mlib.nodes.Node) else (mlib.nodes.Node(str(item)) if mlib.objExists(str(item)) else None)
    if not isinstance(node, mlib.nodes.Transform):
        raise ValueError("{} must be an existing transform: {}".format(label, item))
    return node


class UnevenGround(TwistDistribution):
    """平らな床の上で付けた左右の足と腰の動きを、足の下の地面の高さと傾きに合わせて後から補正する標準DG。

    歩き・立ちのアニメーションは平らな床(高さ ``floorHeight``)で作り、坂・段差のある場所では
    描画用の結果だけを補正する、という一般的な考え方。アニメーション自体(足のコントロール・腰)は
    書き換えず、補正後のワールド行列を出力するので、IKのハンドル・脚のjoint などの受け側へつなぐ。

    計算(ワールド空間、Y が上、行ベクトルの規約)。左右の足 i ごとに:
        - ``p`` = 足のワールド位置、 ``g`` = 地面の transform の位置、 ``n`` = 地面の ``groundAxis`` の
          ワールドの単位ベクトル(地面の法線)。
        - 足の真下(真上)の地面の高さ ``y_g = p.y + ((g - p)·n) / max(n.y, 0.05)``。
        - 足の持ち上げ ``h = height · (y_g - floorHeight)``。足が床から浮いている分(ジャンプ・振り出し)は
          そのまま残り、地面の高さだけが加わる。
        - 地面の向き: ``A0`` = Y を世界の上、 ``forwardAxis`` を足の前へ揃えた向き、 ``A`` = Y を ``n``、
          ``forwardAxis`` を足の前へ揃えた向き(どちらも ``aimMatrix`` 。前は上の軸に直交させる)。
          ``D = A0^-1 · A`` 、 ``Dt = slerp(単位行列, D, align)`` (``blendMatrix``)。D は世界の上を ``n`` へ、
          足の前の水平の向きを「足の前を ``n`` の方向に地面の面へ投影した向き」へ移す回転で、足の進む向きを
          大きく変えずに足裏を地面の傾きへ合わせる。
        - 足の出力 ``Fi = F · T(-p) · Dt · T(p + h·Y)`` (F は足の現在のワールド行列)。
    腰:
        - ``hipsOffset = hips · min(h_left, h_right)`` 。低い方の足へ脚が届くよう、腰を低い方の
          地面に合わせて下げる(両足が段の上なら上げる)。
        - 腰の出力 ``H · T(0, hipsOffset, 0)`` (H は腰の現在のワールド行列。回転は変えない)。

    地面は、足ごとの平面を表す transform(原点が地面の上の点、 ``groundAxis`` が法線)で与える。
    メッシュの地面に合わせる場合は、その transform を地面へ貼り付けて(follicle・``closestPointOnMesh``
    など)動かす。時刻・前の結果を使わないので、どのフレームでも同じ配置から同じ値になる。
    """

    @staticmethod
    def placement(hips, leftFoot, rightFoot, leftGround, rightGround, floorHeight=0.0, height=1.0, align=1.0,
                  hipsWeight=1.0, groundAxis="y", forwardAxis="z"):
        """DGと同じ式で補正後のワールド行列を求めるPython版(確認用)。

        Args:
            hips (MMatrix | Matrix): 腰のワールド行列。
            leftFoot (MMatrix | Matrix): 左足のワールド行列。
            rightFoot (MMatrix | Matrix): 右足のワールド行列。
            leftGround (MMatrix | Matrix): 左足の下の地面のワールド行列。
            rightGround (MMatrix | Matrix): 右足の下の地面のワールド行列。
            floorHeight (float): アニメーションを付けた平らな床の高さ(cm)。
            height (float): 地面の高さを足へ加える割合。
            align (float): 足を地面の傾きへ合わせる割合(0〜1)。
            hipsWeight (float): 低い方の足の持ち上げを腰へ加える割合。
            groundAxis (str): 地面の法線の局所の軸。
            forwardAxis (str): 足の前の局所の軸。

        Returns:
            dict[str, object]: ``hips``・``left``・``right`` (Matrix)と ``leftOffset``・``rightOffset``・
            ``hipsOffset`` (float)。
        """
        UnevenGround._axes(groundAxis, forwardAxis)
        result = {}
        offsets = []
        for side, foot, ground in (("left", leftFoot, leftGround), ("right", rightFoot, rightGround)):
            foot, ground = Matrix(foot), Matrix(ground)
            point = Vector(foot[12], foot[13], foot[14])
            origin = Vector(ground[12], ground[13], ground[14])
            normal = (Vector(*AXES[groundAxis]) * ground).normal()
            surface = point.y + ((origin - point) * normal) / max(normal.y, _MIN_UP)
            lift = height * (surface - floorHeight)
            offsets.append(lift)
            forward = Vector(*AXES[forwardAxis]) * foot
            rest = UnevenGround._levelFrame(Vector(0.0, 1.0, 0.0), forward)
            tilted = UnevenGround._levelFrame(normal, forward)
            delta = rest.inverse() * tilted
            spin = Quaternion().slerp(delta.quaternion, align).asMatrix()
            back = Matrix.compose(translate=(-point.x, -point.y, -point.z))
            ahead = Matrix.compose(translate=(point.x, point.y + lift, point.z))
            result[side] = Matrix(foot * back * spin * ahead)
            result[side + "Offset"] = lift
        lowered = hipsWeight * min(offsets)
        hips = Matrix(hips)
        result["hips"] = Matrix(hips * Matrix.compose(translate=(0.0, lowered, 0.0)))
        result["hipsOffset"] = lowered
        return result

    @staticmethod
    def _levelFrame(up, forward):
        """Y を up、Z を forward(up に直交させた成分)へ向けた回転行列(aimMatrix と同じ規約)。"""
        up = up.normal()
        side = forward - up * (forward * up)
        if side.length() < 1e-9:
            raise ValueError("The foot forward axis must not be parallel to the ground normal")
        side = side.normal()
        x = up ^ side
        return Matrix([x.x, x.y, x.z, 0.0, up.x, up.y, up.z, 0.0, side.x, side.y, side.z, 0.0, 0.0, 0.0, 0.0, 1.0])

    @staticmethod
    def _axes(groundAxis, forwardAxis):
        """軸の名前を確かめる。"""
        if groundAxis not in AXES or forwardAxis not in AXES:
            raise ValueError("groundAxis and forwardAxis must be one of " + ", ".join(sorted(AXES)))

    @classmethod
    @undoTransaction("mlrig.UnevenGround.create")
    def create(cls, hips, leftFoot, rightFoot, leftGround, rightGround, name="unevenGround", floorHeight=0.0,
               height=1.0, align=1.0, hipsWeight=1.0, groundAxis="y", forwardAxis="z"):
        """左右の足と腰の入力と足ごとの地面から、補正後のワールド行列を出すcontainerを作る。

        Args:
            hips (str | Node): 腰の入力の transform(平らな床で動かした腰のコントロールなど)。
            leftFoot (str | Node): 左足の入力の transform(足首・IKのコントロールなど)。
            rightFoot (str | Node): 右足の入力の transform。
            leftGround (str | Node): 左足の下の地面を表す transform(原点が地面の上、 ``groundAxis`` が法線)。
            rightGround (str | Node): 右足の下の地面を表す transform。左足と同じものでもよい(1枚の坂)。
            name (str): 一意なcontainer名。
            floorHeight (float): アニメーションを付けた平らな床のワールドの高さ(cm)。
            height (float): 地面の高さを足へ加える割合(0 で補正なし、1 で地面の上)。
            align (float): 足を地面の傾きへ合わせる割合(0〜1)。
            hipsWeight (float): 低い方の足の持ち上げを腰へ加える割合。
            groundAxis (str): 地面の transform の法線の局所の軸(``x``・``y``・``z``・``-x``・``-y``・``-z``)。
            forwardAxis (str): 足の前の局所の軸。

        Returns:
            UnevenGround: floorHeight・height・align・hips(keyable)と、出力 ``hipsMatrix``・``leftFootMatrix``・
            ``rightFootMatrix`` (ワールド行列)・ ``leftOffset``・``rightOffset``・``hipsOffset`` (cm)を持つ
            containerの所有者。

        Raises:
            ValueError: 引数が不正な場合、腰・足が重複する場合、地面が腰・足と同じ場合、
                作成時の地面の法線が下向き・水平に近い場合、またはnameが既に存在する場合。

        Note:
            出力は入力のノードへは接続しない(入力を書き換えると循環する)。受け側の offsetParentMatrix へ
            入れる場合は、受け側の親の worldInverseMatrix を掛けてからつなぐ。地面が足ごとの平面なので、
            足の大きさより細かい凹凸(つま先とかかとで高さが違う段の角など)は表さない。
        """
        cls._axes(groundAxis, forwardAxis)
        floorHeight = _number(floorHeight, "floorHeight")
        height, align, hipsWeight = (_number(height, "height"), _number(align, "align"),
                                     _number(hipsWeight, "hipsWeight"))
        if not 0.0 <= align <= 1.0:
            raise ValueError("align must be from 0 to 1: " + str(align))
        hips, leftFoot, rightFoot = (_transform(hips, "hips"), _transform(leftFoot, "leftFoot"),
                                     _transform(rightFoot, "rightFoot"))
        grounds = (_transform(leftGround, "leftGround"), _transform(rightGround, "rightGround"))
        bodies = [hips, leftFoot, rightFoot]
        if len({node.getUuid() for node in bodies}) != 3:
            raise ValueError("hips, leftFoot and rightFoot must be different nodes")
        if {node.getUuid() for node in grounds} & {node.getUuid() for node in bodies}:
            raise ValueError("The grounds must be different from the hips and the feet")
        if mlib.objExists(name):
            raise ValueError("UnevenGround container already exists: " + name)
        with nativeUnits():
            for ground in grounds:
                normal = (Vector(*AXES[groundAxis]) * Matrix(ground.getPlug("worldMatrix")[0].get())).normal()
                if normal.y < _MIN_UP:
                    raise ValueError("The ground normal must point upward: " + str(ground))
            for foot in (leftFoot, rightFoot):
                normal = Vector(0.0, 1.0, 0.0)
                forward = Vector(*AXES[forwardAxis]) * Matrix(foot.getPlug("worldMatrix")[0].get())
                if (forward - normal * (forward * normal)).length() < 1e-4:
                    raise ValueError("The foot forward axis must not be vertical: " + str(foot))
            graph = cls(mlib.createContainer(name=name))
            graph._build(hips, (leftFoot, rightFoot), grounds, floorHeight, height, align, hipsWeight,
                         groundAxis, forwardAxis)
        return graph

    def _vector(self, matrix, vector, operation, role):
        """行列で点(operation=4)・向き(3)を変換する ``vectorProduct`` のノード。"""
        node = self._node("vectorProduct", role)
        node.getPlug("operation").set(operation)
        node.getPlug("input1").set(vector)
        if operation == 3:
            node.getPlug("normalizeOutput").set(True)
        matrix.connectTo(node.getPlug("matrix"))
        return node

    def _frame(self, foot, ground, groundAxis, forwardAxis, role):
        """Y を地面の法線(ground が None なら世界の上)、Z を足の前へ揃えた ``aimMatrix`` の向き。"""
        aim = self._node("aimMatrix", role)
        aim.getPlug("primaryMode").set(2)
        aim.getPlug("primaryInputAxis").set((0.0, 1.0, 0.0))
        if ground is None:
            aim.getPlug("primaryTargetVector").set((0.0, 1.0, 0.0))
        else:
            aim.getPlug("primaryTargetVector").set(AXES[groundAxis])
            ground.getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
        aim.getPlug("secondaryMode").set(2)
        aim.getPlug("secondaryInputAxis").set((0.0, 0.0, 1.0))
        aim.getPlug("secondaryTargetVector").set(AXES[forwardAxis])
        foot.getPlug("worldMatrix")[0].connectTo(aim.getPlug("secondaryTargetMatrix"))
        return aim.getPlug("outputMatrix")

    def _build(self, hips, feet, grounds, floorHeight, height, align, hipsWeight, groundAxis, forwardAxis):
        """createの本体(内部単位の中で呼ぶ)。"""
        owner = self.container
        owner.addAttr(longName="floorHeight", attributeType="doubleLinear", defaultValue=floorHeight, keyable=True)
        owner.addAttr(longName="height", attributeType="double", defaultValue=height, keyable=True)
        owner.addAttr(longName="align", attributeType="double", defaultValue=align, minValue=0.0, maxValue=1.0,
                      keyable=True)
        owner.addAttr(longName="hips", attributeType="double", defaultValue=hipsWeight, keyable=True)
        for attr in ("hipsMatrix", "leftFootMatrix", "rightFootMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")
        for attr in ("leftOffset", "rightOffset", "hipsOffset"):
            owner.addAttr(longName=attr, attributeType="doubleLinear")

        for side, foot, ground in zip(_SIDES, feet, grounds):
            world = foot.getPlug("worldMatrix")[0]
            pointNode = self._vector(world, (0.0, 0.0, 0.0), 4, side + "Point")
            point = pointNode.getPlug("output")
            origin = self._vector(ground.getPlug("worldMatrix")[0], (0.0, 0.0, 0.0), 4, side + "GroundPoint")
            origin = origin.getPlug("output")
            normalNode = self._vector(ground.getPlug("worldMatrix")[0], AXES[groundAxis], 3, side + "Normal")
            normal = normalNode.getPlug("output")

            # y_g = p.y + ((g - p)·n) / max(n.y, 0.05)、h = height · (y_g - floorHeight)。
            diff = self._node("plusMinusAverage", side + "ToGround")
            diff.getPlug("operation").set(2)
            origin.connectTo(diff.getPlug("input3D")[0])
            point.connectTo(diff.getPlug("input3D")[1])
            dot = self._node("vectorProduct", side + "Dot")
            dot.getPlug("operation").set(1)
            diff.getPlug("output3D").connectTo(dot.getPlug("input1"))
            normal.connectTo(dot.getPlug("input2"))
            upward = self._node("clamp", side + "Upward")
            upward.getPlug("minR").set(_MIN_UP)
            upward.getPlug("maxR").set(1.0)
            normalNode.getPlug("outputY").connectTo(upward.getPlug("inputR"))
            ratio = self._node("multiplyDivide", side + "Vertical")
            ratio.getPlug("operation").set(2)
            dot.getPlug("outputX").connectTo(ratio.getPlug("input1X"))
            upward.getPlug("outputR").connectTo(ratio.getPlug("input2X"))
            surface = self._node("plusMinusAverage", side + "Surface")
            surface.getPlug("operation").set(2)
            ratio.getPlug("outputX").connectTo(surface.getPlug("input1D")[0])
            owner.getPlug("floorHeight").connectTo(surface.getPlug("input1D")[1])
            rise = self._node("plusMinusAverage", side + "Rise")
            surface.getPlug("output1D").connectTo(rise.getPlug("input1D")[0])
            pointNode.getPlug("outputY").connectTo(rise.getPlug("input1D")[1])
            lift = self._node("multiplyDivide", side + "Lift")
            rise.getPlug("output1D").connectTo(lift.getPlug("input1X"))
            owner.getPlug("height").connectTo(lift.getPlug("input2X"))
            lift.getPlug("outputX").connectTo(owner.getPlug(side + "Offset"))

            # D = A0^-1 · A、Dt = slerp(単位行列, D, align)。
            rest = self._frame(foot, None, groundAxis, forwardAxis, side + "Level")
            tilted = self._frame(foot, ground, groundAxis, forwardAxis, side + "Tilted")
            # A0 は回転だけなので逆行列は転置。行を vectorProduct で取り出し、fourByFourMatrix へ転置して入れる
            # (inverseMatrix は標準のプラグインのノードなので使わない)。
            inverse = self._node("fourByFourMatrix", side + "LevelInverse")
            for row, unit in enumerate(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))):
                axis = self._vector(rest, unit, 3, "{}LevelAxis{}".format(side, row))
                for column, name in enumerate("XYZ"):
                    axis.getPlug("output" + name).connectTo(inverse.getPlug("in{}{}".format(column, row)))
            delta = self._node("multMatrix", side + "Delta")
            inverse.getPlug("output").connectTo(delta.getPlug("matrixIn")[0])
            tilted.connectTo(delta.getPlug("matrixIn")[1])
            blend = self._node("blendMatrix", side + "Align")
            delta.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
            owner.getPlug("align").connectTo(blend.getPlug("target")[0]["weight"])

            # Fi = F · T(-p) · Dt · T(p + h·Y)。
            negate = self._node("multiplyDivide", side + "Negate")
            negate.getPlug("input2").set((-1.0, -1.0, -1.0))
            point.connectTo(negate.getPlug("input1"))
            back = self._node("composeMatrix", side + "Back")
            negate.getPlug("output").connectTo(back.getPlug("inputTranslate"))
            raised = self._node("plusMinusAverage", side + "Raised")
            point.connectTo(raised.getPlug("input3D")[0])
            owner.getPlug(side + "Offset").connectTo(raised.getPlug("input3D")[1]["input3Dy"])
            ahead = self._node("composeMatrix", side + "Ahead")
            raised.getPlug("output3D").connectTo(ahead.getPlug("inputTranslate"))
            result = self._node("multMatrix", side + "Foot")
            world.connectTo(result.getPlug("matrixIn")[0])
            back.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
            blend.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[2])
            ahead.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[3])
            result.getPlug("matrixSum").connectTo(owner.getPlug(side + "FootMatrix"))

        # hipsOffset = hips · min(h_left, h_right)、腰の出力 = H · T(0, hipsOffset, 0)。
        lower = self._node("condition", "lower")
        lower.getPlug("operation").set(4)
        owner.getPlug("leftOffset").connectTo(lower.getPlug("firstTerm"))
        owner.getPlug("rightOffset").connectTo(lower.getPlug("secondTerm"))
        owner.getPlug("leftOffset").connectTo(lower.getPlug("colorIfTrueR"))
        owner.getPlug("rightOffset").connectTo(lower.getPlug("colorIfFalseR"))
        drop = self._node("multiplyDivide", "hipsDrop")
        lower.getPlug("outColorR").connectTo(drop.getPlug("input1X"))
        owner.getPlug("hips").connectTo(drop.getPlug("input2X"))
        drop.getPlug("outputX").connectTo(owner.getPlug("hipsOffset"))
        shift = self._node("composeMatrix", "hipsShift")
        owner.getPlug("hipsOffset").connectTo(shift.getPlug("inputTranslateY"))
        moved = self._node("multMatrix", "hips")
        hips.getPlug("worldMatrix")[0].connectTo(moved.getPlug("matrixIn")[0])
        shift.getPlug("outputMatrix").connectTo(moved.getPlug("matrixIn")[1])
        moved.getPlug("matrixSum").connectTo(owner.getPlug("hipsMatrix"))
