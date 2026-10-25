"""目のハイライト(キャッチライト)を、カメラと光の方向に合わせて眼球の表面の上で動かす標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 眼球の前・上に使える局所の軸。
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0),
        "-x": (-1.0, 0.0, 0.0), "-y": (0.0, -1.0, 0.0), "-z": (0.0, 0.0, -1.0)}

#: 長さ・距離の下限(cm)。
_EPSILON = 1e-4


def _number(value, label):
    """有限の数かを確かめて float にする。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("{} must be a finite number: {}".format(label, value))
    return float(value)


def _transform(item, label):
    """既存の transform・joint の Node に解決する(cameraのシェイプなら親の transform)。"""
    node = item if isinstance(item, mlib.nodes.Node) else (mlib.getNode(str(item)) if mlib.ls(str(item)) else None)
    if node is not None and not isinstance(node, mlib.nodes.Transform) and node.getType() == "camera":
        node = node.getParent()
    if not isinstance(node, mlib.nodes.Transform):
        raise ValueError("{} must be an existing transform: {}".format(label, item))
    return node


class EyeHighlight(TwistDistribution):
    """目のハイライト(瞳の上の光の映り込み)を、カメラの方向に合わせて眼球の表面の上で動かす標準DG。

    鏡のような球に写る光の点は、球の中心から見て「カメラへの向き」と「光への向き」のちょうど中間
    (Blinn-Phong の half vector)の方向の表面に現れる。テクスチャやシェーダーに描き込んだハイライトでは
    カメラを回り込むと目の中の位置が変わらず不自然になるため、ハイライトの板(または補助骨)を
    その点へ置き、眼球の表面に沿って移るようにする。光を指定しない場合はカメラ自身を光とみなし、
    ハイライトは眼球のうちカメラに正対する点に来る(カメラに付けた照明の写り込み)。

    計算(ワールド空間、行ベクトルの規約):
        - ``E`` = eye の位置、 ``v = normalize(C - E)`` (C はカメラの位置)、
          ``l = normalize(Lp - E)`` (Lp は light の位置。light が無ければ ``l = v``)。
        - ``h = normalize(v + l)`` (light が無ければ ``h = v``)。 ``F`` = eye の ``aimAxis`` のワールドの向き。
        - ``m = follow · h + (1 - follow) · F`` 。 ``follow = 0`` ならハイライトは目の前(瞳の中心)に
          留まって眼球の回転だけに付いていき、1 ならカメラ・光の方向へ完全に移る。
        - 向き ``R``: ``E`` から ``E + m`` へ ``aimAxis`` を向け、 ``upAxis`` を eye の ``upAxis`` へ揃える(``aimMatrix``)。
        - ハイライトのワールド行列 ``M = T(radius · aimAxis) · R · T(E)`` (位置 ``E + radius · normalize(m)``)。
        - ハイライトの offsetParentMatrix = ``L0^-1 · M · Pw^-1`` (L0 は作成時のハイライトのローカル行列、
          Pw は親のワールド行列)を、作成時の値から ``weight`` で補間する(``blendMatrix``)。

    光・カメラの位置は眼球の中心から見た向きだけを使う(眼球の大きさに比べて十分遠いとみなす近似)。
    時刻・前の結果を使わないので、どのフレームでも同じ配置から同じ値になる。
    """

    @staticmethod
    def placement(eye, camera, light=None, radius=1.0, follow=1.0, aimAxis="z", upAxis="y"):
        """DGと同じ式でハイライトのワールド行列を求めるPython版(確認用)。

        Args:
            eye (MMatrix | Matrix): 眼球のワールド行列。
            camera (Sequence[float]): カメラのワールド位置。
            light (Sequence[float] | None): 光のワールド位置。Noneならカメラを光とみなす。
            radius (float): 眼球の中心からハイライトまでの距離(cm)。
            follow (float): 目の前の向き(0)からカメラ・光の中間の向き(1)への補間。
            aimAxis (str): 眼球の前の局所の軸。
            upAxis (str): 眼球の上の局所の軸。

        Returns:
            Matrix: ハイライトのワールド行列(scale 1、shearなし)。

        Raises:
            ValueError: 軸が不正な場合、または向きが決まらない場合。
        """
        aim, up = EyeHighlight._axes(aimAxis, upAxis)
        eye = Matrix(eye)
        center = Vector(eye[12], eye[13], eye[14])
        view = Vector(*camera) - center
        if view.length() < _EPSILON:
            raise ValueError("The camera must be apart from the eye center")
        half = view.normal()
        if light is not None:
            towards = Vector(*light) - center
            if towards.length() < _EPSILON:
                raise ValueError("The light must be apart from the eye center")
            half = half + towards.normal()
            if half.length() < _EPSILON:
                raise ValueError("The light must not be exactly opposite to the camera")
            half = half.normal()
        forward = (Vector(*aim) * eye).normal()
        mixed = half * follow + forward * (1.0 - follow)
        if mixed.length() < _EPSILON:
            raise ValueError("The highlight direction is undefined")
        primary = mixed.normal()
        eye_up = (Vector(*up) * eye).normal()
        # aimMatrix と同じく、上の軸は primary に直交する成分へ揃える。
        secondary = eye_up - primary * (eye_up * primary)
        if secondary.length() < _EPSILON:
            raise ValueError("The up axis must not be parallel to the highlight direction")
        aim_index, up_index = EyeHighlight._index(aimAxis), EyeHighlight._index(upAxis)
        rows = {aim_index: primary * (-1.0 if aimAxis.startswith("-") else 1.0),
                up_index: secondary.normal() * (-1.0 if upAxis.startswith("-") else 1.0)}
        # 残りの軸は右手系にする(x = y × z、y = z × x、z = x × y)。
        other = 3 - aim_index - up_index
        rows[other] = rows[(other + 1) % 3] ^ rows[(other + 2) % 3]
        position = center + primary * radius
        values = []
        for index in range(3):
            values += [rows[index].x, rows[index].y, rows[index].z, 0.0]
        return Matrix(values + [position.x, position.y, position.z, 1.0])

    @staticmethod
    def _index(axis):
        """軸の名前から 0〜2 の番号。"""
        return "xyz".index(axis[-1])

    @staticmethod
    def _axes(aimAxis, upAxis):
        """前・上の軸を確かめ、ベクトルを返す。"""
        if aimAxis not in AXES or upAxis not in AXES:
            raise ValueError("aimAxis and upAxis must be one of " + ", ".join(sorted(AXES)))
        if aimAxis[-1] == upAxis[-1]:
            raise ValueError("aimAxis and upAxis must be different axes")
        return AXES[aimAxis], AXES[upAxis]

    @classmethod
    @undoTransaction("mlrig.EyeHighlight.create")
    def create(cls, eye, camera, highlight, name="eyeHighlight", light=None, radius=None, follow=1.0,
               weight=0.0, aimAxis="z", upAxis="y", connect=True):
        """カメラ・光の方向から、眼球の表面の上のハイライトの位置と向きを求めるcontainerを作る。

        Args:
            eye (str | Node): 眼球の中心にある transform・joint(前が ``aimAxis``、上が ``upAxis``)。
            camera (str | Node): カメラの transform(またはcameraのシェイプ)。位置だけを使う。
            highlight (str | Node): 動かすハイライトの板・補助骨の transform・joint。offsetParentMatrix が
                未接続であること。eye の子でもよい。
            name (str): 一意なcontainer名。
            light (str | Node | None): 光の transform。位置だけを使う。Noneならカメラを光とみなす。
            radius (float | None): 眼球の中心からハイライトまでの距離(cm、角膜の半径)。Noneなら作成時の
                eye と highlight の距離。
            follow (float): 目の前の向き(0)からカメラ・光の中間の向き(1)への補間。
            weight (float): 作成時のハイライトの姿勢(0)から計算した配置(1)への補間。既定の0では作成時に
                ハイライトが動かない。
            aimAxis (str): 眼球の前の局所の軸(``x``・``y``・``z``・``-x``・``-y``・``-z``)。ハイライトの
                同じ軸が眼球の外向きになる。
            upAxis (str): 眼球の上の局所の軸。ハイライトの同じ軸を眼球の上へ揃える。
            connect (bool): Trueなら出力 ``matrix`` をハイライトの offsetParentMatrix へ接続する。

        Returns:
            EyeHighlight: radius・follow・weight(keyable)と、出力 ``highlightMatrix``(ワールド行列)・
            ``matrix``(offsetParentMatrix へ入れる値)を持つcontainerの所有者。

        Raises:
            ValueError: 引数が不正な場合、ノードが重複する場合、eye・camera・light が highlight 自身か
                その子の場合、カメラ・光が眼球の中心に重なる場合、highlight の offsetParentMatrix が
                接続済み・ロック済みの場合、またはnameが既に存在する場合。

        Note:
            ハイライトの translate・rotate・scale は空いたままで、計算した配置の上に作成時からの差が
            上乗せされる(板の大きさ・向きの微調整に使う)。光がカメラのちょうど反対側にある場合と、
            ``follow`` の途中の値で ``h`` と ``F`` がちょうど逆向きの場合は向きが決まらない。
        """
        cls._axes(aimAxis, upAxis)
        follow, weight = _number(follow, "follow"), _number(weight, "weight")
        for label, value in (("follow", follow), ("weight", weight)):
            if not 0.0 <= value <= 1.0:
                raise ValueError("{} must be from 0 to 1: {}".format(label, value))
        eye = _transform(eye, "eye")
        camera = _transform(camera, "camera")
        highlight = _transform(highlight, "highlight")
        sources = [eye, camera] + ([] if light is None else [_transform(light, "light")])
        if len({node.getUuid() for node in sources + [highlight]}) != len(sources) + 1:
            raise ValueError("eye, camera, light and highlight must be different nodes")
        for node in sources:
            if highlight.isAncestorOf(node):
                raise ValueError("The eye, camera and light must not be children of the highlight: " + str(node))
        opm = highlight.getPlug("offsetParentMatrix")
        if opm.getSource(skipConversionNodes=False) is not None:
            raise ValueError("Highlight offsetParentMatrix is already connected")
        if opm.isLocked():
            raise ValueError("Highlight offsetParentMatrix must be writable")
        if mlib.ls(name):
            raise ValueError("EyeHighlight container already exists: " + name)

        with nativeUnits():
            worlds = [Matrix(node.getPlug("worldMatrix")[0].get()) for node in sources]
            center = Vector(worlds[0][12], worlds[0][13], worlds[0][14])
            for node, world in zip(sources[1:], worlds[1:]):
                if (Vector(world[12], world[13], world[14]) - center).length() < _EPSILON:
                    raise ValueError("The camera and the light must be apart from the eye center: " + str(node))
            if radius is None:
                world = Matrix(highlight.getPlug("worldMatrix")[0].get())
                radius = (Vector(world[12], world[13], world[14]) - center).length()
                if radius < _EPSILON:
                    raise ValueError("Specify radius: the highlight is at the eye center")
            radius = _number(radius, "radius")
            if radius < _EPSILON:
                raise ValueError("radius must be greater than 0: " + str(radius))
            local = Matrix(highlight.getPlug("matrix").get())
            if local.isSingular():
                raise ValueError("Highlight local matrix must be invertible")
            rest = Matrix(opm.get())

            graph = cls(mlib.nodes.Container.create(name=name))
            graph._build(sources, highlight, local, rest, radius, follow, weight, aimAxis, upAxis)
            if connect:
                graph.container.getPlug("matrix").connectTo(opm)
        return graph

    def _point(self, node, role):
        """transformのワールド位置(3要素)を出す ``vectorProduct``。"""
        point = self._node("vectorProduct", role)
        point.getPlug("operation").set(4)
        point.getPlug("input1").set((0.0, 0.0, 0.0))
        node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrix"))
        return point.getPlug("output")

    def _towards(self, origin, target, role):
        """``origin`` の位置から ``target`` の位置への単位ベクトルを出す。

        ``aimMatrix`` で +Z を向けてから軸を取り出すので、2点が重なっても(作成・削除の途中など)
        ``vectorProduct`` の正規化のように長さ0のエラーにならない。

        Args:
            origin (Plug): 始点の行列(位置だけを使う)。
            target (Plug): 終点の行列(位置だけを使う)。
            role (str): 用途名。

        Returns:
            Plug: 単位ベクトル(3要素)。
        """
        aim = self._node("aimMatrix", role + "Aim")
        origin.connectTo(aim.getPlug("inputMatrix"))
        target.connectTo(aim.getPlug("primaryTargetMatrix"))
        aim.getPlug("primaryMode").set(1)
        aim.getPlug("primaryInputAxis").set((0.0, 0.0, 1.0))
        aim.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        aim.getPlug("secondaryMode").set(0)
        axis = self._node("vectorProduct", role)
        axis.getPlug("operation").set(3)
        axis.getPlug("normalizeOutput").set(True)
        axis.getPlug("input1").set((0.0, 0.0, 1.0))
        aim.getPlug("outputMatrix").connectTo(axis.getPlug("matrix"))
        return axis.getPlug("output")

    def _offsetMatrix(self, center, vector, role):
        """``T(center + vector)`` の行列を出す。"""
        total = self._node("plusMinusAverage", role + "Point")
        center.connectTo(total.getPlug("input3D")[0])
        vector.connectTo(total.getPlug("input3D")[1])
        matrix = self._node("composeMatrix", role + "Matrix")
        total.getPlug("output3D").connectTo(matrix.getPlug("inputTranslate"))
        return matrix.getPlug("outputMatrix")

    def _build(self, sources, highlight, local, rest, radius, follow, weight, aimAxis, upAxis):
        """createの本体(内部単位の中で呼ぶ)。

        Args:
            sources (list[Transform]): [eye, camera] または [eye, camera, light]。
            highlight (Transform): ハイライト。
            local (Matrix): 作成時のハイライトのローカル行列 L0。
            rest (Matrix): 作成時のハイライトの offsetParentMatrix。
            radius (float): 距離の初期値(cm)。
            follow (float): follow の初期値。
            weight (float): weight の初期値。
            aimAxis (str): 前の軸。
            upAxis (str): 上の軸。
        """
        owner = self.container
        owner.addAttr(longName="radius", attributeType="doubleLinear", defaultValue=radius, minValue=_EPSILON,
                      keyable=True)
        for attr, value in (("follow", follow), ("weight", weight)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, minValue=0.0, maxValue=1.0,
                          keyable=True)
        for attr in ("highlightMatrix", "matrix"):
            owner.addAttr(longName=attr, dataType="matrix")
        eye = sources[0]
        aim, up = AXES[aimAxis], AXES[upAxis]

        # v = normalize(C - E)、l = normalize(Lp - E)、h = normalize(v + l)(E から E + v + l への向き)。
        center = self._point(eye, "eyePoint")
        origin = self._node("composeMatrix", "eyeOrigin")
        center.connectTo(origin.getPlug("inputTranslate"))
        origin = origin.getPlug("outputMatrix")
        half = self._towards(origin, sources[1].getPlug("worldMatrix")[0], "view")
        if len(sources) == 3:
            light = self._towards(origin, sources[2].getPlug("worldMatrix")[0], "light")
            total = self._node("plusMinusAverage", "halfSum")
            half.connectTo(total.getPlug("input3D")[0])
            light.connectTo(total.getPlug("input3D")[1])
            half = self._towards(origin, self._offsetMatrix(center, total.getPlug("output3D"), "half"), "half")

        # F = eye の aimAxis のワールドの向き、m = follow · h + (1 - follow) · F。
        forward = self._node("vectorProduct", "forward")
        forward.getPlug("operation").set(3)
        forward.getPlug("normalizeOutput").set(True)
        forward.getPlug("input1").set(aim)
        eye.getPlug("worldMatrix")[0].connectTo(forward.getPlug("matrix"))
        mix = self._node("blendColors", "followBlend")
        half.connectTo(mix.getPlug("color1"))
        forward.getPlug("output").connectTo(mix.getPlug("color2"))
        owner.getPlug("follow").connectTo(mix.getPlug("blender"))

        # R: E から E + m へ aimAxis を向け、upAxis を eye の upAxis へ揃える。m は正規化せずに aimMatrix に
        # 渡すので、m が短くても長さ0のエラーにならない。
        target = self._offsetMatrix(center, mix.getPlug("output"), "ahead")
        frame = self._node("aimMatrix", "frame")
        origin.connectTo(frame.getPlug("inputMatrix"))
        target.connectTo(frame.getPlug("primaryTargetMatrix"))
        frame.getPlug("primaryMode").set(1)
        frame.getPlug("primaryInputAxis").set(aim)
        frame.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        frame.getPlug("secondaryMode").set(2)
        frame.getPlug("secondaryInputAxis").set(up)
        frame.getPlug("secondaryTargetVector").set(up)
        eye.getPlug("worldMatrix")[0].connectTo(frame.getPlug("secondaryTargetMatrix"))

        # M = T(radius · aimAxis) · R · T(E)。
        reach = self._node("multiplyDivide", "reach")
        reach.getPlug("input1").set(aim)
        for axis in "XYZ":
            owner.getPlug("radius").connectTo(reach.getPlug("input2" + axis))
        offset = self._node("composeMatrix", "surfaceOffset")
        reach.getPlug("output").connectTo(offset.getPlug("inputTranslate"))
        world = self._node("multMatrix", "highlightWorld")
        offset.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
        frame.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("highlightMatrix"))

        # offsetParentMatrix = L0^-1 · M · Pw^-1。ハイライト自身の parentInverseMatrix は offsetParentMatrix
        # を含み、ここで駆動する値と循環するので、親の worldInverseMatrix を使う(親が無ければ単位行列)。
        space = self._node("multMatrix", "parentSpace")
        space.getPlug("matrixIn")[0].set(local.inverse())
        owner.getPlug("highlightMatrix").connectTo(space.getPlug("matrixIn")[1])
        parent = highlight.getParent()
        if parent is not None:
            parent.getPlug("worldInverseMatrix")[0].connectTo(space.getPlug("matrixIn")[2])
        blend = self._node("blendMatrix", "weightBlend")
        blend.getPlug("inputMatrix").set(rest)
        space.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        owner.getPlug("weight").connectTo(blend.getPlug("target")[0]["weight"])
        blend.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
