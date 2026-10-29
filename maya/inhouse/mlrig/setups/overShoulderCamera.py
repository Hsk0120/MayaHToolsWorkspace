"""会話する2人の頭の位置から、肩越しのカメラの位置と向きを決める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: フィルムバックの単位(インチ)を焦点距離の単位(mm)へ直す係数。
_INCH = 25.4

#: 2人の水平の距離の下限(向きが決まらない配置を避ける)。
_EPSILON = 1e-4


class OverShoulderCamera(TwistDistribution):
    """手前の人物(partner)の肩越しに、奥の人物(focus)の頭を画面の決まった位置へ写すカメラの標準DG。

    会話の場面の肩越しの構図を、2人の頭の位置からの相対で決める一般的な方法を、毎フレームの計算に
    置き換えたもの。2人を結ぶ線(イマジナリーライン)の片側(``side``)にカメラを置くので、人物が
    動いても線を越えず、2人とカメラの三角形の位置関係が保たれる。

    計算(ワールド空間、上はY):
        - ``a`` = focus の位置、 ``b`` = partner の位置、 ``u = normalize((b - a) の水平成分)``。
        - ``θ = side · angle``、 ``d = Ry(θ) · u`` (``u`` をY軸まわりに回した水平の向き。
          ``side > 0`` で ``(u × d).y > 0``)。
        - 基準の位置 ``c0 = a + distance · d + (0, height, 0)``。 ``c0`` から ``a`` へカメラの -Z を
          向け、+Y をワールドの上へ揃えた向き ``R`` (``aimMatrix``)。
        - ``D = |a - c0|``、被写体の面での画面(フィルムゲート)の半分の幅・高さ
          ``halfWidth = D · horizontalFilmAperture · 25.4 / (2f)``、
          ``halfHeight = D · verticalFilmAperture · 25.4 / (2f)``。
        - カメラの位置 ``c = c0 - screenX · halfWidth · X - screenY · halfHeight · Y``
          (``X``・``Y`` は ``R`` の右・上の軸)。向きは ``R`` のまま平行に動かすので、 ``a`` は
          画面のフィルムゲートの座標 (``screenX``, ``screenY``) (左右・上下の端が ±1)に写る。
          三分割法の交点は (±1/3, ±1/3)。
        - 出力 ``matrix`` = ``blendMatrix`` (作成時のカメラのワールド行列 → ``R`` と ``c`` の行列, ``weight``)。

    時刻・前の結果を使わないので、どのフレームでも同じ配置から同じ値になる。 ``vectorProduct``・
    ``multiplyDivide`` は単精度で計算するため、位置には1e-5cm程度の丸めの誤差が入る。
    """

    @staticmethod
    def placement(focus, partner, distance, angle, height=0.0, side=1.0, screenX=0.0, screenY=0.0,
                  focalLength=35.0, horizontalAperture=1.417, verticalAperture=0.945):
        """DGと同じ式でカメラのワールド行列を求めるPython版(確認用)。

        Args:
            focus (Sequence[float]): 写す人物の頭のワールド位置。
            partner (Sequence[float]): 肩越しになる人物の頭のワールド位置。
            distance (float): focus からカメラの基準の位置までの水平の距離(cm)。
            angle (float): 2人を結ぶ線からカメラを回す角度(度)。
            height (float): focus の頭からのカメラの高さ(cm)。
            side (float): 線のどちら側か(+1 または -1。途中の値は角度を縮める)。
            screenX (float): focus の頭を写す画面の横の位置(-1〜1)。
            screenY (float): focus の頭を写す画面の縦の位置(-1〜1)。
            focalLength (float): 焦点距離(mm)。
            horizontalAperture (float): 横のフィルムバック(インチ)。
            verticalAperture (float): 縦のフィルムバック(インチ)。

        Returns:
            Matrix: カメラのワールド行列(scaleは1)。
        """
        ax, ay, az = (float(value) for value in focus)
        bx, _, bz = (float(value) for value in partner)
        length = math.hypot(bx - ax, bz - az)
        ux, uz = (bx - ax) / length, (bz - az) / length
        theta = math.radians(angle * side)
        dx = ux * math.cos(theta) + uz * math.sin(theta)
        dz = -ux * math.sin(theta) + uz * math.cos(theta)
        base = (ax + distance * dx, ay + height, az + distance * dz)
        back = [base[0] - ax, base[1] - ay, base[2] - az]
        depth = math.sqrt(sum(value * value for value in back))
        back = [value / depth for value in back]
        right = [back[2], 0.0, -back[0]]
        size = math.hypot(right[0], right[2])
        right = [value / size for value in right]
        up = [back[1] * right[2] - back[2] * right[1], back[2] * right[0] - back[0] * right[2],
              back[0] * right[1] - back[1] * right[0]]
        halfWidth = depth * horizontalAperture * _INCH / (2.0 * focalLength)
        halfHeight = depth * verticalAperture * _INCH / (2.0 * focalLength)
        position = [base[index] - screenX * halfWidth * right[index] - screenY * halfHeight * up[index]
                    for index in range(3)]
        return Matrix(right + [0.0] + up + [0.0] + back + [0.0] + position + [1.0])

    @classmethod
    @undoTransaction("mlrig.OverShoulderCamera.create")
    def create(cls, camera, focus, partner, name="overShoulderCamera", distance=None, angle=15.0, height=0.0,
               side=1.0, screenX=0.0, screenY=0.0, weight=0.0, connect=True):
        """2人の頭の位置からカメラのワールド行列を求めるcontainerを作る。

        Args:
            camera (str | Node): cameraのシェイプを持つtransform、またはcameraのシェイプ。
            focus (str | Node): 画面に写す人物の頭のtransform。
            partner (str | Node): 手前で肩越しになる人物の頭のtransform。
            name (str): 一意なcontainer名。
            distance (float | None): focus からの水平の距離(cm)。Noneなら作成時の2人の水平の距離の1.5倍。
            angle (float): 2人を結ぶ線からカメラを回す角度(度、0〜90)。
            height (float): focus の頭からのカメラの高さ(cm)。
            side (float): 線のどちら側にカメラを置くか(-1〜1、通常は +1 か -1)。
            screenX (float): focus の頭を写す画面の横の位置(-1〜1)。
            screenY (float): focus の頭を写す画面の縦の位置(-1〜1)。
            weight (float): 作成時のカメラの姿勢(0)から肩越しの配置(1)への補間。既定の0では作成時に
                カメラが動かない。
            connect (bool): Trueなら出力をカメラの translate・rotate へ接続する(カメラの親の空間へ戻す)。

        Returns:
            OverShoulderCamera: distance・angle・height・side・screenX・screenY・weight(keyable)と、
            matrix・focusDistance の所有者。

        Raises:
            ValueError: 引数が不正な場合、2人の水平の距離が0に近い場合、 ``connect=True`` でカメラの
                translate・rotate が既に接続されている場合、またはnameが既に存在する場合。

        Note:
            画面の位置はフィルムゲート(横・縦のフィルムバック)を基準にする。カメラの rotatePivot・
            rotateAxis・フィルムのオフセットは考慮しない。2人が真上・真下に重なる配置では向きが決まらない。
        """
        transform, shape = cls._camera(camera)
        heads = []
        for item in (focus, partner):
            node = item if isinstance(item, mlib.nodes.Node) else (
                mlib.getNode(str(item)) if mlib.ls(str(item)) else None)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected an existing transform: " + str(item))
            heads.append(node)
        if len({node.getUuid() for node in heads + [transform]}) != 3:
            raise ValueError("camera, focus and partner must be three different nodes")
        values = {"angle": angle, "height": height, "side": side, "screenX": screenX, "screenY": screenY,
                  "weight": weight}
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("{} must be a finite number: {}".format(key, value))
        if not 0.0 <= angle <= 90.0:
            raise ValueError("angle must be from 0 to 90: " + str(angle))
        for key in ("side", "screenX", "screenY"):
            if not -1.0 <= values[key] <= 1.0:
                raise ValueError("{} must be from -1 to 1: {}".format(key, values[key]))
        if not 0.0 <= weight <= 1.0:
            raise ValueError("weight must be from 0 to 1: " + str(weight))
        a, b = (Matrix(node.getPlug("worldMatrix")[0].get()) for node in heads)
        length = math.hypot(b[12] - a[12], b[14] - a[14])
        if length < _EPSILON:
            raise ValueError("focus and partner must be apart horizontally")
        if distance is None:
            distance = 1.5 * length
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(
                distance) or distance <= 0.0:
            raise ValueError("distance must be greater than 0: " + str(distance))
        if connect:
            for attr in ("translate", "rotate"):
                for axis in ("", "X", "Y", "Z"):
                    if transform.getPlug(attr + axis).getSource() is not None:
                        raise ValueError("The camera {} is already connected: {}".format(attr, transform))
        if mlib.ls(name):
            raise ValueError("OverShoulderCamera container already exists: " + name)
        rest = Matrix(transform.getPlug("worldMatrix")[0].get())
        with nativeUnits():
            graph = cls(mlib.nodes.Container.create(name=name))
            graph._build(transform, shape, heads, rest, float(distance), dict(values))
            if connect:
                graph._connect(transform)
        return graph

    @staticmethod
    def _camera(item):
        """入力をcameraのtransformとシェイプへ解決する。

        Args:
            item (str | Node): cameraのtransformまたはシェイプ。

        Returns:
            tuple[Transform, Node]: (transform, cameraのシェイプ)。

        Raises:
            ValueError: cameraでない場合。
        """
        node = item if isinstance(item, mlib.nodes.Node) else (mlib.getNode(str(item)) if mlib.ls(str(item)) else None)
        if node is None:
            raise ValueError("Expected an existing camera: " + str(item))
        if node.getType() == "camera":
            return node.getParent(), node
        if isinstance(node, mlib.nodes.Transform):
            shapes = [child for child in node.getShapes() if child.getType() == "camera"]
            if len(shapes) == 1:
                return node, shapes[0]
        raise ValueError("Expected a camera transform or camera shape: " + str(item))

    def _point(self, node, role):
        """transformのワールド位置を出す ``vectorProduct`` を作る。

        Args:
            node (Transform): 対象。
            role (str): 用途名。

        Returns:
            Plug: ワールド位置(3要素)。
        """
        point = self._node("vectorProduct", role)
        point.getPlug("operation").set(4)
        point.getPlug("input1").set((0.0, 0.0, 0.0))
        node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrix"))
        return point.getPlug("output")

    def _axis(self, matrix, vector, role):
        """行列で回した単位の軸を出す ``vectorProduct`` を作る。

        Args:
            matrix (Plug): 行列。
            vector (tuple[float, float, float]): 回す軸。
            role (str): 用途名。

        Returns:
            Plug: 正規化した軸(3要素)。
        """
        axis = self._node("vectorProduct", role)
        axis.getPlug("operation").set(3)
        axis.getPlug("normalizeOutput").set(True)
        axis.getPlug("input1").set(vector)
        matrix.connectTo(axis.getPlug("matrix"))
        return axis.getPlug("output")

    def _scaled(self, vector, scalar, role):
        """3要素のベクトルにスカラーを掛ける ``multiplyDivide`` を作る。

        Args:
            vector (Plug): ベクトル。
            scalar (Plug): スカラー。
            role (str): 用途名。

        Returns:
            Plug: 積(3要素)。
        """
        product = self._node("multiplyDivide", role)
        vector.connectTo(product.getPlug("input1"))
        for axis in "XYZ":
            scalar.connectTo(product.getPlug("input2" + axis))
        return product.getPlug("output")

    def _build(self, camera, shape, heads, rest, distance, values):
        """createの本体(内部単位の中で呼ぶ)。

        Args:
            camera (Transform): カメラのtransform。
            shape (Node): cameraのシェイプ。
            heads (list[Transform]): [focus, partner]。
            rest (Matrix): 作成時のカメラのワールド行列。
            distance (float): 水平の距離の初期値(cm)。
            values (dict): angle(度)・height・side・screenX・screenY・weight の初期値。
        """
        owner = self.container
        owner.addAttr(longName="distance", attributeType="doubleLinear", defaultValue=distance, minValue=1e-4,
                      keyable=True)
        owner.addAttr(longName="angle", attributeType="doubleAngle", defaultValue=values["angle"],
                      minValue=0.0, maxValue=90.0, keyable=True)
        owner.addAttr(longName="height", attributeType="doubleLinear", defaultValue=values["height"], keyable=True)
        for key in ("side", "screenX", "screenY"):
            owner.addAttr(longName=key, attributeType="double", defaultValue=values[key], minValue=-1.0,
                          maxValue=1.0, keyable=True)
        owner.addAttr(longName="weight", attributeType="double", defaultValue=values["weight"], minValue=0.0,
                      maxValue=1.0, keyable=True)
        owner.addAttr(longName="matrix", dataType="matrix")
        owner.addAttr(longName="focusDistance", attributeType="doubleLinear")

        # 2人を結ぶ水平の向き u: 2人の位置を床(y=0)へ落とした行列の間で +Z を partner へ向ける(aimMatrix)。
        # ベクトルの正規化を使わないので、作成・削除の途中で2点が重なっても長さ0の警告が出ない。
        focus = self._point(heads[0], "focusPoint")
        partner = self._point(heads[1], "partnerPoint")
        floors = []
        for point, role in ((focus, "focus"), (partner, "partner")):
            flat = self._node("multiplyDivide", role + "Flat")
            point.connectTo(flat.getPlug("input1"))
            flat.getPlug("input2").set((1.0, 0.0, 1.0))
            floor = self._node("composeMatrix", role + "Floor")
            flat.getPlug("output").connectTo(floor.getPlug("inputTranslate"))
            floors.append(floor.getPlug("outputMatrix"))
        line = self._node("aimMatrix", "line")
        floors[0].connectTo(line.getPlug("inputMatrix"))
        floors[1].connectTo(line.getPlug("primaryTargetMatrix"))
        line.getPlug("primaryMode").set(1)
        line.getPlug("primaryInputAxis").set((0.0, 0.0, 1.0))
        line.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        line.getPlug("secondaryMode").set(2)
        line.getPlug("secondaryInputAxis").set((0.0, 1.0, 0.0))
        line.getPlug("secondaryTargetVector").set((0.0, 1.0, 0.0))

        # d = Ry(side · angle) · u。lineの回転はY軸まわりだけなので、Ry を先に掛けて +Z を回す
        # (内部単位の中なのでラジアンのまま渡り、単位変換のノードを挟まない)。
        signed = self._node("multiplyDivide", "signedAngle")
        owner.getPlug("angle").connectTo(signed.getPlug("input1X"))
        owner.getPlug("side").connectTo(signed.getPlug("input2X"))
        turn = self._node("composeMatrix", "turn")
        signed.getPlug("outputX").connectTo(turn.getPlug("inputRotateY"))
        turned = self._node("multMatrix", "turnedLine")
        turn.getPlug("outputMatrix").connectTo(turned.getPlug("matrixIn")[0])
        line.getPlug("outputMatrix").connectTo(turned.getPlug("matrixIn")[1])
        direction = self._node("vectorProduct", "direction")
        direction.getPlug("operation").set(3)
        direction.getPlug("input1").set((0.0, 0.0, 1.0))
        turned.getPlug("matrixSum").connectTo(direction.getPlug("matrix"))

        # c0 = a + distance · d + (0, height, 0)
        reach = self._scaled(direction.getPlug("output"), owner.getPlug("distance"), "reach")
        base = self._node("plusMinusAverage", "basePosition")
        focus.connectTo(base.getPlug("input3D")[0])
        reach.connectTo(base.getPlug("input3D")[1])
        base.getPlug("input3D")[2].set((0.0, 0.0, 0.0))
        owner.getPlug("height").connectTo(base.getPlug("input3D")[2]["input3Dy"])
        baseMatrix = self._node("composeMatrix", "baseMatrix")
        base.getPlug("output3D").connectTo(baseMatrix.getPlug("inputTranslate"))

        # R: c0 から a へ -Z を向け、+Y をワールドの上へ揃える。
        aim = self._node("aimMatrix", "aim")
        baseMatrix.getPlug("outputMatrix").connectTo(aim.getPlug("inputMatrix"))
        heads[0].getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
        aim.getPlug("primaryMode").set(1)
        aim.getPlug("primaryInputAxis").set((0.0, 0.0, -1.0))
        aim.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        aim.getPlug("secondaryMode").set(2)
        aim.getPlug("secondaryInputAxis").set((0.0, 1.0, 0.0))
        aim.getPlug("secondaryTargetVector").set((0.0, 1.0, 0.0))

        # D と、被写体の面での画面の半分の幅・高さ。
        depth = self._node("distanceBetween", "focusDistance")
        focus.connectTo(depth.getPlug("point1"))
        base.getPlug("output3D").connectTo(depth.getPlug("point2"))
        depth.getPlug("distance").connectTo(owner.getPlug("focusDistance"))
        aperture = self._node("multiplyDivide", "apertureHalfMm")
        shape.getPlug("horizontalFilmAperture").connectTo(aperture.getPlug("input1X"))
        shape.getPlug("verticalFilmAperture").connectTo(aperture.getPlug("input1Y"))
        aperture.getPlug("input2").set((_INCH / 2.0, _INCH / 2.0, 1.0))
        spread = self._node("multiplyDivide", "depthAperture")
        for axis in "XY":
            depth.getPlug("distance").connectTo(spread.getPlug("input1" + axis))
            aperture.getPlug("output" + axis).connectTo(spread.getPlug("input2" + axis))
        half = self._node("multiplyDivide", "halfFrame")
        half.getPlug("operation").set(2)
        spread.getPlug("output").connectTo(half.getPlug("input1"))
        for axis in "XYZ":
            shape.getPlug("focalLength").connectTo(half.getPlug("input2" + axis))
        amount = self._node("multiplyDivide", "screenShift")
        half.getPlug("output").connectTo(amount.getPlug("input1"))
        owner.getPlug("screenX").connectTo(amount.getPlug("input2X"))
        owner.getPlug("screenY").connectTo(amount.getPlug("input2Y"))

        # c = c0 - screenX · halfWidth · X - screenY · halfHeight · Y(向きは R のまま)。
        right = self._axis(aim.getPlug("outputMatrix"), (1.0, 0.0, 0.0), "rightAxis")
        up = self._axis(aim.getPlug("outputMatrix"), (0.0, 1.0, 0.0), "upAxis")
        shiftX = self._scaled(right, amount.getPlug("outputX"), "shiftX")
        shiftY = self._scaled(up, amount.getPlug("outputY"), "shiftY")
        position = self._node("plusMinusAverage", "position")
        position.getPlug("operation").set(2)
        base.getPlug("output3D").connectTo(position.getPlug("input3D")[0])
        shiftX.connectTo(position.getPlug("input3D")[1])
        shiftY.connectTo(position.getPlug("input3D")[2])
        rotation = self._node("pickMatrix", "rotation")
        aim.getPlug("outputMatrix").connectTo(rotation.getPlug("inputMatrix"))
        for attr in ("useTranslate", "useScale", "useShear"):
            rotation.getPlug(attr).set(False)
        moved = self._node("composeMatrix", "positionMatrix")
        position.getPlug("output3D").connectTo(moved.getPlug("inputTranslate"))
        shot = self._node("multMatrix", "shot")
        rotation.getPlug("outputMatrix").connectTo(shot.getPlug("matrixIn")[0])
        moved.getPlug("outputMatrix").connectTo(shot.getPlug("matrixIn")[1])

        # 作成時のカメラの姿勢(定数)から肩越しの配置へ weight で補間する。
        blend = self._node("blendMatrix", "weightBlend")
        blend.getPlug("inputMatrix").set(rest)
        shot.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        owner.getPlug("weight").connectTo(blend.getPlug("target")[0]["weight"])
        blend.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["focusDistance"], keyable=False, channelBox=True)

    def _connect(self, camera):
        """出力の行列をカメラの親の空間へ戻し、translate・rotate へ接続する。

        Args:
            camera (Transform): カメラのtransform。
        """
        local = self._node("multMatrix", "cameraLocal")
        self.container.getPlug("matrix").connectTo(local.getPlug("matrixIn")[0])
        # parentInverseMatrix は offsetParentMatrix と親のワールド行列だけで決まり、ここで駆動する
        # translate・rotate には依存しないので循環しない(offsetParentMatrix を駆動する場合は親の
        # worldInverseMatrix を使う必要がある)。
        camera.getPlug("parentInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
        decompose = self._node("decomposeMatrix", "cameraDecompose")
        local.getPlug("matrixSum").connectTo(decompose.getPlug("inputMatrix"))
        camera.getPlug("rotateOrder").connectTo(decompose.getPlug("inputRotateOrder"))
        decompose.getPlug("outputTranslate").connectTo(camera.getPlug("translate"))
        decompose.getPlug("outputRotate").connectTo(camera.getPlug("rotate"))
