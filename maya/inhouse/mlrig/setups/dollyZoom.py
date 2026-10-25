"""カメラと被写体の距離から焦点距離を決め、被写体の写る大きさを保つドリーズームの標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: Mayaのcameraの焦点距離(mm)の範囲。出力はこの範囲に収める。
FOCAL_RANGE = (2.5, 100000.0)

#: フィルムバックの単位(インチ)を焦点距離の単位(mm)へ直す係数。
_INCH = 25.4

#: 被写体の面の幅の下限(0除算を避ける)。
_EPSILON = 1e-6


class DollyZoom(TwistDistribution):
    """カメラを前後に動かしても、被写体の写る大きさが変わらないように焦点距離を変える標準DG。

    被写体を通りカメラの視線に垂直な面で、画面の横幅に写る範囲の幅は
    ``W = depth · aperture / f`` (``depth`` はカメラの視線の方向に測った被写体までの距離(cm)、
    ``aperture`` は横のフィルムバック(mm)、 ``f`` は焦点距離(mm))。 ``W`` を一定に保つように
    ``f_zoom = depth · aperture / frameWidth`` とすると、カメラが近づくと広角に、離れると望遠になり、
    被写体の大きさはそのままで背景の遠近感だけが変わる(ドリーズーム、いわゆるめまいの効果)。

    ``depth`` は、カメラから被写体へのワールドのベクトルと、カメラの -Z を正規化した視線の向きの内積
    (カメラのscale・shearの影響を受けない)。
    作成時の焦点距離 ``restFocalLength`` と ``f_zoom`` を ``weight`` で補間し(``blendTwoAttr``)、
    Mayaのcameraの範囲(2.5〜100000mm)に収めて ``focalLength`` へ出す。作成時の ``frameWidth`` は
    作成時の距離と焦点距離から求めるので、作成直後の焦点距離は変わらない(跳ねない)。

    出力(containerのアトリビュート):
        - ``focalLength``: 焦点距離(mm)。 ``connect=True`` ならカメラの ``focalLength`` へ接続する。
        - ``depth``: 視線の方向の被写体までの距離(cm、被写体がカメラの後ろなら負)。
        - ``fieldOfView``: 横の画角(度、 ``2·atan(aperture / (2·focalLength))``)。

    時刻・前の結果を使わないので、どのフレームでも同じ配置から同じ値になる。 ``vectorProduct``・
    ``multiplyDivide`` は単精度で計算するため、焦点距離には相対で1e-7程度の丸めの誤差が入る。
    """

    @staticmethod
    def focalLength(depth, frameWidth, aperture, restFocalLength, weight=1.0):
        """DGと同じ式で焦点距離を求めるPython版(確認用)。

        Args:
            depth (float): 視線の方向の被写体までの距離(cm)。
            frameWidth (float): 被写体の面で画面の横幅に写る幅(cm)。
            aperture (float): 横のフィルムバック(インチ)。
            restFocalLength (float): ``weight=0`` のときの焦点距離(mm)。
            weight (float): ドリーズームの効き(0〜1)。

        Returns:
            float: 焦点距離(mm)。 :data:`FOCAL_RANGE` に収める。
        """
        zoom = depth * aperture * _INCH / max(frameWidth, _EPSILON)
        value = restFocalLength + weight * (zoom - restFocalLength)
        return min(max(value, FOCAL_RANGE[0]), FOCAL_RANGE[1])

    @staticmethod
    def fieldOfView(focalLength, aperture):
        """焦点距離と横のフィルムバックから横の画角(度)を求める。

        Args:
            focalLength (float): 焦点距離(mm)。
            aperture (float): 横のフィルムバック(インチ)。

        Returns:
            float: 横の画角(度)。
        """
        return math.degrees(2.0 * math.atan(aperture * _INCH / (2.0 * focalLength)))

    @classmethod
    @undoTransaction("mlrig.DollyZoom.create")
    def create(cls, camera, subject, name="dollyZoom", weight=1.0, connect=True):
        """カメラの焦点距離を被写体までの距離から決めるcontainerを作る。

        Args:
            camera (str | Node): cameraのシェイプを持つtransform、またはcameraのシェイプ。
            subject (str | Node): 写る大きさを保つ被写体のtransform。
            name (str): 一意なcontainer名。
            weight (float): ドリーズームの効き(0〜1)。containerの ``weight`` (keyable)の初期値。
            connect (bool): Trueなら出力の ``focalLength`` をカメラの焦点距離へ接続する。

        Returns:
            DollyZoom: weight・frameWidth・restFocalLength(keyable)と、focalLength・depth・fieldOfView の所有者。

        Raises:
            ValueError: 引数が不正な場合、被写体がカメラの前に無い場合、カメラの焦点距離が範囲外の場合、
                ``connect=True`` で焦点距離が既に接続されている場合、またはnameが既に存在する場合。

        Note:
            画面の横幅に写る幅を保つが、焦点距離と距離の比が一定になるので、フィルムの合わせ方(film fit)に
            よらず被写体の面の写り方全体が保たれる。被写体の面より手前・奥のものは、距離の比に応じて大きさが
            変わる。カメラのフィルムバックを作成後に変えると ``frameWidth`` の意味(幅)は保たれたまま
            焦点距離が変わる。
        """
        transform, shape = cls._camera(camera)
        target = subject if isinstance(subject, mlib.nodes.Node) else (
            mlib.getNode(str(subject)) if mlib.ls(str(subject)) else None)
        if not isinstance(target, mlib.nodes.Transform):
            raise ValueError("Expected an existing transform: " + str(subject))
        if target.getUuid() == transform.getUuid():
            raise ValueError("subject must be different from the camera")
        weight = float(weight)
        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
            raise ValueError("weight must be from 0 to 1: " + str(weight))
        focal = shape.getPlug("focalLength")
        if connect and focal.getSource() is not None:
            raise ValueError("The camera focalLength is already connected: " + str(focal))
        if mlib.ls(name):
            raise ValueError("DollyZoom container already exists: " + name)
        restFocal = float(focal.get())
        if not FOCAL_RANGE[0] <= restFocal <= FOCAL_RANGE[1]:
            raise ValueError("The camera focalLength is out of range: " + str(restFocal))
        aperture = float(shape.getPlug("horizontalFilmAperture").get())
        graph = cls(mlib.nodes.Container.create(name=name))
        depth = graph._buildDepth(transform, target)
        restDepth = float(graph.container.getPlug("depth").get())
        if restDepth <= _EPSILON:
            # undoTransactionが例外で作りかけのノードを取り消す。
            raise ValueError("subject must be in front of the camera")
        frameWidth = restDepth * aperture * _INCH / restFocal
        graph._buildFocal(shape, depth, restFocal, frameWidth, weight)
        if connect:
            graph.container.getPlug("focalLength").connectTo(focal)
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

    def _buildDepth(self, camera, subject):
        """被写体をカメラの空間へ移し、視線の方向の距離を出すノードを作る。

        Args:
            camera (Transform): カメラのtransform。
            subject (Transform): 被写体。

        Returns:
            Plug: 距離(cm)。
        """
        owner = self.container
        owner.addAttr(longName="depth", attributeType="double")
        # 位置は点(0,0,0)の変換(vectorProductの4)、視線はカメラの -Z を回して正規化した向き(3)。
        # 行列の逆を使わないので、カメラのscale・shearは距離に影響しない。
        points = []
        for node, role in ((subject, "subjectPoint"), (camera, "cameraPoint")):
            point = self._node("vectorProduct", role)
            point.getPlug("operation").set(4)
            for axis in "XYZ":
                point.getPlug("input1" + axis).set(0.0)
            node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrix"))
            points.append(point)
        forward = self._node("vectorProduct", "cameraForward")
        forward.getPlug("operation").set(3)
        forward.getPlug("normalizeOutput").set(True)
        for axis, value in zip("XYZ", (0.0, 0.0, -1.0)):
            forward.getPlug("input1" + axis).set(value)
        camera.getPlug("worldMatrix")[0].connectTo(forward.getPlug("matrix"))
        offset = self._node("plusMinusAverage", "subjectOffset")
        offset.getPlug("operation").set(2)
        points[0].getPlug("output").connectTo(offset.getPlug("input3D")[0])
        points[1].getPlug("output").connectTo(offset.getPlug("input3D")[1])
        dot = self._node("vectorProduct", "depth")
        dot.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(dot.getPlug("input1"))
        forward.getPlug("output").connectTo(dot.getPlug("input2"))
        dot.getPlug("outputX").connectTo(owner.getPlug("depth"))
        return owner.getPlug("depth")

    def _buildFocal(self, shape, depth, restFocal, frameWidth, weight):
        """距離から焦点距離・画角を求めるノードを作る。

        Args:
            shape (Node): cameraのシェイプ。
            depth (Plug): 視線の方向の距離。
            restFocal (float): 作成時の焦点距離(mm)。
            frameWidth (float): 作成時の被写体の面の幅(cm)。
            weight (float): ドリーズームの効きの初期値。
        """
        owner = self.container
        owner.addAttr(longName="weight", attributeType="double", defaultValue=weight, minValue=0.0, maxValue=1.0,
                      keyable=True)
        owner.addAttr(longName="frameWidth", attributeType="double", defaultValue=frameWidth, minValue=_EPSILON,
                      keyable=True)
        owner.addAttr(longName="restFocalLength", attributeType="double", defaultValue=restFocal,
                      minValue=FOCAL_RANGE[0], keyable=True)
        owner.addAttr(longName="focalLength", attributeType="double")
        owner.addAttr(longName="fieldOfView", attributeType="doubleAngle")

        # 横のフィルムバック(インチ)を mm に直した値(X)と、その半分の正負(Y・Z、画角に使う)。
        aperture = self._node("multiplyDivide", "apertureMm")
        for axis, factor in (("X", _INCH), ("Y", _INCH / 2.0), ("Z", -_INCH / 2.0)):
            shape.getPlug("horizontalFilmAperture").connectTo(aperture.getPlug("input1" + axis))
            aperture.getPlug("input2" + axis).set(factor)
        product = self._node("multiplyDivide", "depthAperture")
        depth.connectTo(product.getPlug("input1X"))
        aperture.getPlug("outputX").connectTo(product.getPlug("input2X"))
        zoom = self._node("multiplyDivide", "zoomFocal")
        zoom.getPlug("operation").set(2)
        product.getPlug("outputX").connectTo(zoom.getPlug("input1X"))
        owner.getPlug("frameWidth").connectTo(zoom.getPlug("input2X"))
        blend = self._node("blendTwoAttr", "weightBlend")
        owner.getPlug("restFocalLength").connectTo(blend.getPlug("input")[0])
        zoom.getPlug("outputX").connectTo(blend.getPlug("input")[1])
        owner.getPlug("weight").connectTo(blend.getPlug("attributesBlender"))
        limit = self._node("clamp", "focalRange")
        limit.getPlug("minR").set(FOCAL_RANGE[0])
        limit.getPlug("maxR").set(FOCAL_RANGE[1])
        blend.getPlug("output").connectTo(limit.getPlug("inputR"))
        limit.getPlug("outputR").connectTo(owner.getPlug("focalLength"))

        # 横の画角: (f, +a/2) と (f, -a/2) の2つのベクトルのなす角が 2·atan(a / 2f)。
        angle = self._node("angleBetween", "fieldOfView")
        for index, axis in ((1, "Y"), (2, "Z")):
            limit.getPlug("outputR").connectTo(angle.getPlug("vector{}X".format(index)))
            aperture.getPlug("output" + axis).connectTo(angle.getPlug("vector{}Y".format(index)))
            angle.getPlug("vector{}Z".format(index)).set(0.0)
        angle.getPlug("angle").connectTo(owner.getPlug("fieldOfView"))
        owner.setAttrFlags(["depth", "focalLength", "fieldOfView"], keyable=False, channelBox=True)
