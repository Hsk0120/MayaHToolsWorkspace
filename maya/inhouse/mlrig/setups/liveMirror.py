"""左右の片側のコントロールの姿勢を、対称面で鏡に映して反対側のコントロールへ常に写す標準DGを構築する。"""

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 対称面の法線にする軸。
AXES = ("x", "y", "z")

#: 鏡に映したあとに向きを反転する局所の軸。``behavior`` は3軸すべて(Mayaの mirrorJoint の Behavior と同じ)。
FLIPS = {"behavior": (-1.0, -1.0, -1.0), "x": (-1.0, 1.0, 1.0), "y": (1.0, -1.0, 1.0), "z": (1.0, 1.0, -1.0)}


def _scaleMatrix(values):
    """対角成分だけの行列。"""
    matrix = Matrix()
    for index, value in enumerate(values):
        matrix[index * 5] = value
    return matrix


class LiveMirror(TwistDistribution):
    """source のワールド行列を対称面で鏡に映し、target が常にその姿勢になるようにする標準DG。

    左右の片側だけを動かして対称なポーズを作る「ライブのシンメトリー」や、右側のコントロールを左側の
    鏡像へ一時的に追従させる用途に使う。target 自身の translate・rotate・scale は空けたままなので、
    鏡像の上に上乗せの調整ができる。weight で元の offsetParentMatrix と鏡像の間を補間する。
    """

    @staticmethod
    def mirror(world, plane=None, axis="x", flip="behavior"):
        """ワールド行列を対称面で鏡に映し、向きを反転した行列を返す(Python版)。

        Args:
            world (MMatrix | Matrix): 鏡に映すワールド行列。
            plane (MMatrix | Matrix | None): 対称面の空間のワールド行列。Noneならワールド。scaleは打ち消し合う。
            axis (str): 対称面の法線にする plane の軸 x/y/z。
            flip (str): 向きを反転する局所の軸。``behavior``・``x``・``y``・``z``。

        Returns:
            Matrix: ``F * world * P^-1 * S * P``。
        """
        if axis not in AXES or flip not in FLIPS:
            raise ValueError("axis must be x/y/z and flip must be behavior/x/y/z")
        space = Matrix() if plane is None else Matrix(plane)
        reflect = _scaleMatrix([-1.0 if item == axis else 1.0 for item in AXES])
        return _scaleMatrix(FLIPS[flip]) * Matrix(world) * space.inverse() * reflect * space

    @classmethod
    @undoTransaction("mlrig.LiveMirror.create")
    def create(cls, source, target, name="liveMirror", plane=None, axis="x", flip="behavior",
               maintainOffset=False, weight=1.0, connect=True):
        """source の鏡像を target の offsetParentMatrix へ写す。

        Args:
            source (str | Node): 動かす側(例: 左)のtransform・joint。
            target (str | Node): 写される側(例: 右)のtransform・joint。offsetParentMatrix が未接続であること。
            name (str): 一意なcontainer名。
            plane (str | Node | None): 対称面の空間(キャラクターのルートなど)。法線は ``axis`` の軸。
                Noneならワールドの原点を通る面。scaleは打ち消し合うので影響しないが、shear(回転した親の
                下の非一様scale)があると面が歪むので使わない。
            axis (str): 対称面の法線にする軸 x/y/z。
            flip (str): 鏡に映したあとに向きを反転する局所の軸。``behavior`` は3軸すべて
                (左右を mirrorJoint の Behavior で作った場合)、``x``・``y``・``z`` は1軸。
            maintainOffset (bool): 作成時の source の鏡像と target のずれを定数で保つ。Falseなら厳密な鏡像。
            weight (float): 元の offsetParentMatrix(0)から鏡像(1)への補間。
            connect (bool): 出力 ``matrix`` を target の offsetParentMatrix へ接続する。

        Returns:
            LiveMirror: weight(keyable)と、出力 ``mirrorMatrix``(鏡像のワールド行列)・``matrix``
            (target の offsetParentMatrix へ入れる値)を持つcontainerの所有者。

        Raises:
            ValueError: 引数が不正な場合、source・plane が target 自身かその子の場合、
                target の offsetParentMatrix が接続済み・ロック済みの場合、またはnameが既に存在する場合。

        Note:
            行は行ベクトルの規約(``world = local * parent``)。``R = P^-1 * S * P``(P は対称面の空間の
            ワールド行列、S は法線の軸だけ -1 の対角行列。P = Sp * Rp * Tp なら Sp は打ち消し合う)、``F`` は flip の軸だけ -1 の
            対角行列とすると、鏡像 ``M = F * Ws * R * C``(C は maintainOffset の定数、既定は単位行列)。
            target のワールド行列を ``L * OPM * Pw``(L は target のローカル行列、Pw は親のワールド行列)とし、
            ``L`` が作成時の値 ``L0`` のときに ``M`` になるよう ``OPM = L0^-1 * M * Pw^-1`` を求め、
            作成時の offsetParentMatrix(定数)から blendMatrix で weight 補間する。
            target の translate 等を動かすと、鏡像の上に作成時からの差が上乗せされる。
            F の符号は det(F) = -1 なので、鏡に映して反転した向き(det(R) = -1)と合わせて回転が右手系に戻る。
            jointの segmentScaleCompensate で親の scale を打ち消す場合、作成後に親の scale を変えると
            ``L0`` が変わるため、親の scale は作成時のまま使う。
        """
        if axis not in AXES:
            raise ValueError("axis must be x, y or z: " + str(axis))
        if flip not in FLIPS:
            raise ValueError("flip must be behavior, x, y or z: " + str(flip))
        weight = float(weight)
        if not 0.0 <= weight <= 1.0:
            raise ValueError("weight must be from 0 to 1: " + str(weight))
        if mlib.ls(name):
            raise ValueError("LiveMirror container already exists: " + name)
        source, target = mlib.nodes.Node(source), mlib.nodes.Node(target)
        plane = None if plane is None else mlib.nodes.Node(plane)
        for node in (source, target) + (() if plane is None else (plane,)):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms or joints: " + str(node))
        for node in (source,) + (() if plane is None else (plane,)):
            if node.getUuid() == target.getUuid() or target.isAncestorOf(node):
                raise ValueError("The source and the plane must not be the target or its children")
        opm = target.getPlug("offsetParentMatrix")
        if opm.getSource(skipConversionNodes=False) is not None:
            raise ValueError("Target offsetParentMatrix is already connected")
        if opm.isLocked():
            raise ValueError("Target offsetParentMatrix must be writable")

        with nativeUnits():
            local = Matrix(target.getPlug("matrix").get())
            if local.isSingular():
                raise ValueError("Target local matrix must be invertible")
            rest_opm = Matrix(opm.get())
            plane_world = None if plane is None else Matrix(plane.getPlug("worldMatrix")[0].get())
            mirrored = cls.mirror(Matrix(source.getPlug("worldMatrix")[0].get()), plane_world, axis, flip)
            offset = Matrix()
            if maintainOffset:
                offset = mirrored.inverse() * Matrix(target.getPlug("worldMatrix")[0].get())

            graph = cls(mlib.nodes.Container.create(name=name))
            owner = graph.container
            owner.addAttr(longName="weight", attributeType="double", defaultValue=weight, minValue=0.0,
                          maxValue=1.0, keyable=True)
            for attr in ("mirrorMatrix", "matrix"):
                owner.addAttr(longName=attr, dataType="matrix")

            # 鏡像 M = F * Ws * P^-1 * S * P * C。
            world = graph._node("multMatrix", "mirrorWorld")
            inputs = world.getPlug("matrixIn")
            reflect = _scaleMatrix([-1.0 if item == axis else 1.0 for item in AXES])
            inputs[0].set(_scaleMatrix(FLIPS[flip]))
            source.getPlug("worldMatrix")[0].connectTo(inputs[1])
            if plane is None:
                inputs[2].set(reflect)
                inputs[3].set(offset)
            else:
                # P^-1 * S * P。P = Sp * Rp * Tp(shearなし)なら対角行列どうしは交換できるので、
                # Sp^-1 * S * Sp = S となり plane の scale は打ち消し合う。
                plane.getPlug("worldInverseMatrix")[0].connectTo(inputs[2])
                inputs[3].set(reflect)
                plane.getPlug("worldMatrix")[0].connectTo(inputs[4])
                inputs[5].set(offset)
            world.getPlug("matrixSum").connectTo(owner.getPlug("mirrorMatrix"))

            # target の offsetParentMatrix = L0^-1 * M * Pw^-1 を、作成時の値から weight で補間する。
            parent_space = graph._node("multMatrix", "parentSpace")
            space_inputs = parent_space.getPlug("matrixIn")
            space_inputs[0].set(local.inverse())
            owner.getPlug("mirrorMatrix").connectTo(space_inputs[1])
            # target 自身の parentInverseMatrix は offsetParentMatrix と同じノードの出力で、評価の順が
            # 保証されないため、親の worldInverseMatrix を使う(親が無ければワールドで単位行列)。
            parent = target.getParent()
            if parent is not None:
                parent.getPlug("worldInverseMatrix")[0].connectTo(space_inputs[2])
            blend = graph._node("blendMatrix", "weightBlend")
            blend.getPlug("inputMatrix").set(rest_opm)
            parent_space.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
            owner.getPlug("weight").connectTo(blend.getPlug("target")[0]["weight"])
            blend.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
            if connect:
                owner.getPlug("matrix").connectTo(opm)
        return graph
