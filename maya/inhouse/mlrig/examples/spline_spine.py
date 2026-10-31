"""mGear の背骨(spine_S_shape)に近い操作感の、スプラインIKの背骨のサンプル。

骨盤から胸までの骨列を、4つのコントローラー(腰・腰側の接線・胸側の接線・胸)をCVとする3次カーブに
沿わせる(``mlrig.setups.SplineIK``)。その上に関節ごとのFKコントローラーを階層で重ね、変形用の骨は
FKコントローラーに追従させる。計算はすべてMaya標準ノードで、毎フレームのPython実行は無い。

構成(``name="spine"`` のとき)::

    spine_rig
    ├ spine_ctrl_grp
    │  └ spine_cog_npo / spine_cog_ctrl        全体の移動。アトリビュート(下記)もここに置く
    │     ├ spine_hips_npo / spine_hips_ctrl      腰(カーブの始点、mGear の ik0)
    │     │  └ spine_tan0_npo / spine_tan0_ctrl   腰側の接線(移動のみ)
    │     ├ spine_chest_npo / spine_chest_ctrl    胸(カーブの終点、mGear の ik1)
    │     │  └ spine_tan1_npo / spine_tan1_ctrl   胸側の接線(移動のみ)
    │     └ spine_fk_grp / spine_fk01_npo / spine_fk01_ctrl / spine_fk02_npo ...   FK(階層)
    ├ spine_setup_grp(非表示)    スプラインIKの骨列・カーブ・ハンドル
    └ spine_deform_grp           変形用の骨(スキンに使う)

骨は「X が上(子の方向)、Z が正面」。``spine_cog_ctrl`` のアトリビュート:

* ``maxStretch``(既定 1.5)・``maxSquash``(既定 0.5): カーブの長さの比を、この範囲に収めて骨を伸縮する。
  範囲を超えると骨列は胸のコントローラーに届かない(mGear と同じ)。
* ``volume``(0〜1、既定 1): 伸びると細く、縮むと太くする(断面の拡大率 = 比の -0.5 乗。両端は0、中央で最大)。
* ``lockOriHips``・``lockOriChest``(0〜1、既定 1): 1 なら最下段・最上段の骨の向きを腰・胸の
  コントローラーの回転に合わせる。0 ならカーブの接線に沿う向き。
* ``tangentHips``・``tangentChest``(既定 1): 接線のコントローラーまでの長さの倍率。0 で接線が無くなる。

``stretch=False`` にすると、伸縮と体積の保持を入れないシンプル版になる(``maxStretch``・``maxSquash``・
``volume`` も作らない)。骨の長さは固定で、胸を遠ざけても骨は伸びず、近づけてもカーブより長い分は
終点の先へはみ出す。カーブ・接線・FK・向きの固定は同じ。

使い方::

    from mlrig.examples import spline_spine
    spine = spline_spine.build(name="spine", joint_count=6, length=50.0, height=100.0)
    spine.chest   # 胸のコントローラー(mlib の Node)
    simple = spline_spine.build(name="simpleSpine", stretch=False)   # 伸縮なしのシンプル版
"""

import math
import re


import mlib
from mlib.decorator import preservedSelection, undoTransaction
from mlib.maths import Matrix

from mlrig.setups import SplineIK
from mlrig.setups.controlShape import ControlShape

#: コントローラーの色(Mayaのインデックスカラー)。
COLORS = {"cog": 22, "ik": 18, "tangent": 9, "fk": 17}


class SplineSpine:
    """``build()`` が作った背骨の各ノードをまとめる。

    Attributes:
        root (Node): リグ全体のルート。
        cog (Node): 全体を動かすコントローラー。アトリビュートもここにある。
        hips (Node): 腰のコントローラー(カーブの始点)。
        chest (Node): 胸のコントローラー(カーブの終点)。
        tangents (list[Node]): 腰側・胸側の接線のコントローラー。
        fk (list[Node]): 根元から順のFKコントローラー。
        deform (list[Node]): 根元から順の変形用の骨。
        ik (list[Node]): スプラインIKが回す骨列(非表示)。
        graph (SplineIK): スプラインIKの計算グラフ(カーブ・ハンドル)。
    """

    def __init__(self, **members):
        """各ノードを受け取る。

        Args:
            **members: ``root``・``cog``・``hips``・``chest``・``tangents``・``fk``・``deform``・``ik``・``graph``。
        """
        self.__dict__.update(members)


def _transform(name, parent=None, translate=None):
    """transform を作る。

    Args:
        name (str): 名前。
        parent (Node | None): 親。
        translate (Sequence[float] | None): 親の空間での位置(シーンの長さの単位)。

    Returns:
        Node: 作ったノード。
    """
    flags = dict(name=name, skipSelect=True)
    if parent is not None:
        flags["parent"] = parent
    node = mlib.createNode("transform", **flags)
    if translate:
        node.getPlug("translate").set(tuple(mlib.common.units.distanceFromUi(v) for v in translate))
    return node


def _control(name, parent, translate, radius, normal, color, sphere=False, translateOnly=False):
    """オフセット(npo)とコントローラーの組を作る。

    Args:
        name (str): 名前の前半(``<name>_npo`` と ``<name>_ctrl`` を作る)。
        parent (Node): npo の親。
        translate (Sequence[float] | None): npo の、親の空間での位置。
        radius (float): シェイプの半径。
        normal (Sequence[float]): 円の法線。
        color (int): インデックスカラー。
        sphere (bool): True なら直交する3つの円で球のような形にする。
        translateOnly (bool): True なら回転を操作できないようにする(接線用)。

    Returns:
        tuple[Node, Node]: (npo, control)。
    """
    npo = _transform(name + "_npo", parent, translate)
    control = _transform(name + "_ctrl", npo)
    normals = [normal] + ([(1, 0, 0), (0, 0, 1)] if sphere else [])
    for index, vector in enumerate(normals):
        ControlShape.circle(control, radius, vector, color,
                            name="{}_ctrlShape{}".format(name, index or ""))
    locked = ["scale", "visibility"] + (["rotate"] if translateOnly else [])
    control.setAttrFlags(locked, locked=True, keyable=False)
    return npo, control


def _node(kind, name):
    """DGノードを作る。

    Args:
        kind (str): ノードの種類。
        name (str): 名前。

    Returns:
        Node: 作ったノード。
    """
    return mlib.createNode(kind, name=name, skipSelect=True)


def _multiply(name, source, factor):
    """``source × factor`` の出力 Plug を返す(``factor`` は数値か Plug)。

    multDoubleLinear は Maya 2027 で名前が変わったので、どの版にもある multiplyDivide を使う。

    Args:
        name (str): ノード名。
        source (Plug): 入力。
        factor (float | Plug): 掛ける値。

    Returns:
        Plug: 積。
    """
    node = _node("multiplyDivide", name)
    source.connectTo(node.getPlug("input1X"))
    if isinstance(factor, (int, float)):
        node.getPlug("input2X").set(factor)
    else:
        factor.connectTo(node.getPlug("input2X"))
    return node.getPlug("outputX")


def _add(name, source, value):
    """``source + value`` の出力 Plug を返す。

    Args:
        name (str): ノード名。
        source (Plug): 入力。
        value (float): 足す値。

    Returns:
        Plug: 和。
    """
    node = _node("plusMinusAverage", name)
    source.connectTo(node.getPlug("input1D")[0])
    node.getPlug("input1D")[1].set(value)
    return node.getPlug("output1D")


def _multMatrix(name, *inputs):
    """行列の積(``inputs`` の順に掛ける)の出力 Plug を返す。

    Args:
        name (str): ノード名。
        *inputs (Plug): 入力の行列。

    Returns:
        Plug: 積。
    """
    node = _node("multMatrix", name)
    for index, source in enumerate(inputs):
        source.connectTo(node.getPlug("matrixIn")[index])
    return node.getPlug("matrixSum")


def _worldInverse(name, source, parent):
    """ワールド行列の逆行列の Plug を返す。

    逆行列のノード(inverseMatrix)は matrixNodes プラグインが必要なので使わない。非表示の transform に
    行列を入れ、その ``worldInverseMatrix`` を使う。

    Args:
        name (str): 作る transform の名前。
        source (Plug): 入力のワールド行列。
        parent (Node): transform の親(ワールド行列から親の分を除いて入れる)。

    Returns:
        Plug: 逆行列。
    """
    holder = _transform(name, parent)
    _multMatrix(name + "_local", source, parent.getPlug("worldInverseMatrix")[0]).connectTo(
        holder.getPlug("offsetParentMatrix"))
    return holder.getPlug("worldInverseMatrix")[0]


def _lockedOrientation(name, ikWorld, control, weight):
    """骨の向きを、コントローラーの回転へ ``weight`` の割合で寄せたワールド行列の Plug を返す。

    位置はスプラインIKの骨のまま、回転だけを「作成時の骨とコントローラーの回転の差」を保って
    コントローラーに合わせ、blendMatrix で元の向きと混ぜる。

    Args:
        name (str): ノード名の前半。
        ikWorld (Plug): スプラインIKの骨のワールド行列。
        control (Node): 合わせるコントローラー。
        weight (Plug): 0〜1 の割合。

    Returns:
        Plug: 混ぜた後のワールド行列。
    """
    offset = Matrix(ikWorld.get()) * Matrix(control.getPlug("worldMatrix")[0].get()).inverse()
    for column in range(3):
        offset.setElement(3, column, 0.0)
    world = _node("multMatrix", name + "_lockWorld")
    world.getPlug("matrixIn")[0].set(offset)
    control.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
    rotate = _node("pickMatrix", name + "_lockRotate")
    world.getPlug("matrixSum").connectTo(rotate.getPlug("inputMatrix"))
    rotate.getPlug("useTranslate").set(False)
    position = _node("pickMatrix", name + "_lockPosition")
    ikWorld.connectTo(position.getPlug("inputMatrix"))
    for attr in ("useRotate", "useScale", "useShear"):
        position.getPlug(attr).set(False)
    locked = _multMatrix(name + "_locked", rotate.getPlug("outputMatrix"), position.getPlug("outputMatrix"))
    blend = _node("blendMatrix", name + "_lockBlend")
    ikWorld.connectTo(blend.getPlug("inputMatrix"))
    locked.connectTo(blend.getPlug("target")[0]["targetMatrix"])
    weight.connectTo(blend.getPlug("target")[0]["weight"])
    return blend.getPlug("outputMatrix")


def build(name="spine", joint_count=6, length=50.0, height=100.0, stretch=True):
    """mGear 風のスプラインIKの背骨を、ワールドの +Y 方向に作る。

    作成全体を1回の Undo にまとめ、元の選択を保つ。

    Args:
        name (str): 名前の前半(英数字と ``_``)。``<name>_rig`` が既にあればエラー。
        joint_count (int): 骨の数(末端の胸を含む)。4〜32。
        length (float): 腰から胸までの長さ(シーンの長さの単位)。
        height (float): 腰の高さ。
        stretch (bool): False なら伸縮と体積の保持を入れないシンプル版にする(骨の長さは固定)。

    Returns:
        SplineSpine: 作ったノード。

    Raises:
        ValueError: 名前・骨の数・長さが不正な場合。
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or "") or mlib.objExists(name + "_rig"):
        raise ValueError("Use a new name made of letters, digits and '_': {}".format(name))
    if type(joint_count) is not int or not 4 <= joint_count <= 32:
        raise ValueError("joint_count must be 4..32")
    if not (length > 0 and math.isfinite(length) and math.isfinite(height)):
        raise ValueError("length must be positive and finite")
    with preservedSelection():
        return _build(name, joint_count, float(length), float(height), bool(stretch))


@undoTransaction("mlrig.examples.spline_spine.build")
def _build(name, count, length, height, stretch):
    """``build()`` の本体。

    Args:
        name (str): 名前の前半。
        count (int): 骨の数。
        length (float): 長さ。
        height (float): 腰の高さ。
        stretch (bool): 伸縮と体積の保持を入れるか。

    Returns:
        SplineSpine: 作ったノード。
    """
    segment = length / (count - 1)
    root = _transform(name + "_rig")
    ctrlGroup = _transform(name + "_ctrl_grp", root)
    setupGroup = _transform(name + "_setup_grp", root)
    deformGroup = _transform(name + "_deform_grp", root)
    setupGroup.getPlug("visibility").set(False)

    # ---- コントローラー(mGear の ik0 / tan0 / tan1 / ik1 と同じ並び) ----
    _, cog = _control(name + "_cog", ctrlGroup, (0, height, 0), length * 0.55, (0, 1, 0), COLORS["cog"])
    _, hips = _control(name + "_hips", cog, None, length * 0.4, (0, 1, 0), COLORS["ik"])
    _, chest = _control(name + "_chest", cog, (0, length, 0), length * 0.4, (0, 1, 0), COLORS["ik"])
    tan0Npo, tan0 = _control(name + "_tan0", hips, (0, length / 3.0, 0), length * 0.08, (0, 1, 0),
                             COLORS["tangent"], sphere=True, translateOnly=True)
    tan1Npo, tan1 = _control(name + "_tan1", chest, (0, -length / 3.0, 0), length * 0.08, (0, 1, 0),
                             COLORS["tangent"], sphere=True, translateOnly=True)

    # ---- アトリビュート(cog に置く) ----
    attributes = [("lockOriHips", 1.0, 0.0, 1.0), ("lockOriChest", 1.0, 0.0, 1.0),
                  ("tangentHips", 1.0, 0.0, None), ("tangentChest", 1.0, 0.0, None)]
    if stretch:
        attributes[:0] = [("maxStretch", 1.5, 1.0, None), ("maxSquash", 0.5, 0.0, 1.0), ("volume", 1.0, 0.0, 1.0)]
    for attr, default, minimum, maximum in attributes:
        flags = dict(type="double", defaultValue=default, minValue=minimum, keyable=True)
        if maximum is not None:
            flags["maxValue"] = maximum
        cog.addAttr(attr, **flags)

    # 接線の長さ: 接線のオフセットの位置 = 元の位置 × 倍率。
    for npo, attr, sign in ((tan0Npo, "tangentHips", 1.0), (tan1Npo, "tangentChest", -1.0)):
        _multiply("{}_{}Length".format(name, attr), cog.getPlug(attr),
                  mlib.common.units.distanceFromUi(sign * length / 3.0)).connectTo(npo.getPlug("translateY"))

    # ---- スプラインIKの骨列(X が上、Z が正面) ----
    ik = []
    parent = setupGroup
    for index in range(count):
        joint = mlib.createNode("joint", name="{}_ik{:02d}_jnt".format(name, index + 1), parent=parent,
                                skipSelect=True)
        if index == 0:
            joint.getPlug("translate").set((0, mlib.common.units.distanceFromUi(height), 0))
            joint.getPlug("jointOrient").set((0, 0, 90))
        else:
            joint.getPlug("translateX").set(mlib.common.units.distanceFromUi(segment))
        ik.append(joint)
        parent = joint
    graph = SplineIK.create(ik, [hips, tan0, tan1, chest], setupGroup, name=name + "_splineGraph", up_axis="z")
    curve = graph.member("curve")
    shape = curve.getShapes(intermediates=True)[0]

    amount = _stretch(name, root, shape, cog, ik, length, segment) if stretch else None

    # ---- 各段の「実際の向き」: 最下段と最上段は腰・胸の回転へ寄せる(Lock Ori) ----
    worlds = [joint.getPlug("worldMatrix")[0] for joint in ik]
    worlds[0] = _lockedOrientation(name + "_hips", worlds[0], hips, cog.getPlug("lockOriHips"))
    worlds[-1] = _lockedOrientation(name + "_chest", worlds[-1], chest, cog.getPlug("lockOriChest"))
    inverses = [joint.getPlug("worldInverseMatrix")[0] for joint in ik]
    inverses[0] = _worldInverse(name + "_hipsLock_ref", worlds[0], setupGroup)
    return _layers(name, count, length, cog, deformGroup, worlds, inverses, amount,
                   SplineSpine(root=root, cog=cog, hips=hips, chest=chest, tangents=[tan0, tan1], ik=ik, graph=graph))


def _stretch(name, root, shape, cog, ik, length, segment):
    """伸縮と体積の計算を作り、体積の変化量の Plug を返す。

    Args:
        name (str): 名前の前半。
        root (Node): リグのルート(拡大率を読む)。
        shape (Node): スプラインのカーブのシェイプ。
        cog (Node): アトリビュートを持つコントローラー。
        ik (list[Node]): スプラインIKの骨列。
        length (float): 元の長さ。
        segment (float): 1本の骨の元の長さ。

    Returns:
        Plug: ``volume × (比^-0.5 - 1)``(段ごとの重みを掛ける前)。
    """
    # ---- 伸縮: 比 = カーブの長さ / (元の長さ × リグの拡大率) を maxSquash〜maxStretch に収める ----
    info = _node("curveInfo", name + "_curveInfo")
    shape.getPlug("worldSpace")[0].connectTo(info.getPlug("inputCurve"))
    rigScale = _node("decomposeMatrix", name + "_rigScale")
    root.getPlug("worldMatrix")[0].connectTo(rigScale.getPlug("inputMatrix"))
    restLength = _multiply(name + "_restLength", rigScale.getPlug("outputScaleY"), length)
    ratio = _node("multiplyDivide", name + "_stretchRatio")
    ratio.getPlug("operation").set(2)
    info.getPlug("arcLength").connectTo(ratio.getPlug("input1X"))
    restLength.connectTo(ratio.getPlug("input2X"))
    clamp = _node("clamp", name + "_stretchClamp")
    ratio.getPlug("outputX").connectTo(clamp.getPlug("inputR"))
    cog.getPlug("maxSquash").connectTo(clamp.getPlug("minR"))
    cog.getPlug("maxStretch").connectTo(clamp.getPlug("maxR"))
    stretch = clamp.getPlug("outputR")
    for index, joint in enumerate(ik[1:], 1):
        _multiply("{}_ik{:02d}_length".format(name, index + 1), stretch,
                  mlib.common.units.distanceFromUi(segment)).connectTo(joint.getPlug("translateX"))

    # ---- 体積: 断面の拡大率 = 1 + volume × 重み × (比^-0.5 - 1)。重みは両端0・中央1 ----
    power = _node("multiplyDivide", name + "_volumePower")
    power.getPlug("operation").set(3)
    stretch.connectTo(power.getPlug("input1X"))
    power.getPlug("input2X").set(-0.5)
    change = _add(name + "_volumeChange", power.getPlug("outputX"), -1.0)
    return _multiply(name + "_volumeAmount", change, cog.getPlug("volume"))


def _layers(name, count, length, cog, deformGroup, worlds, inverses, amount, spine):
    """FKコントローラーと変形用の骨を作り、``spine`` に足して返す。

    Args:
        name (str): 名前の前半。
        count (int): 骨の数。
        length (float): 長さ(シェイプの大きさに使う)。
        cog (Node): FKのグループの親。
        deformGroup (Node): 変形用の骨の親。
        worlds (list[Plug]): 各段の実際のワールド行列。
        inverses (list[Plug]): 各段の実際のワールド行列の逆。
        amount (Plug | None): 体積の変化量。None なら体積の保持を入れない。
        spine (SplineSpine): 作成中のノードのまとめ。

    Returns:
        SplineSpine: ``fk`` と ``deform`` を足した ``spine``。
    """
    # ---- FK(階層)。各オフセットは「一つ下の段から見たスプラインIKの段」の行列で動く ----
    fkGroup = _transform(name + "_fk_grp", cog)
    fkGroup.getPlug("inheritsTransform").set(False)
    fk = []
    parent = fkGroup
    for index in range(count):
        npo, control = _control("{}_fk{:02d}".format(name, index + 1), parent, None, length * 0.3,
                                (1, 0, 0), COLORS["fk"])
        control.getPlug("rotateOrder").set(3)  # xzy: ねじれ(X)を最初、前後の曲げ(Y)を最後に評価する
        previous = fkGroup.getPlug("worldInverseMatrix")[0] if index == 0 else inverses[index - 1]
        _multMatrix("{}_fk{:02d}_local".format(name, index + 1), worlds[index], previous).connectTo(
            npo.getPlug("offsetParentMatrix"))
        fk.append(control)
        parent = control

    # ---- 変形用の骨(平らに並べ、FKコントローラーへ追従。断面の拡大は Y・Z の scale) ----
    deform = []
    for index, control in enumerate(fk):
        joint = mlib.createNode("joint", name="{}_{:02d}_jnt".format(name, index + 1), parent=deformGroup,
                                skipSelect=True)
        joint.getPlug("radius").set(length * 0.04)
        _multMatrix("{}_{:02d}_follow".format(name, index + 1), control.getPlug("worldMatrix")[0],
                    deformGroup.getPlug("worldInverseMatrix")[0]).connectTo(joint.getPlug("offsetParentMatrix"))
        weight = math.sin(math.pi * index / (count - 1))
        if amount is not None and weight > 1.0e-6:
            scale = _add("{}_{:02d}_volumeScale".format(name, index + 1),
                         _multiply("{}_{:02d}_volumeWeight".format(name, index + 1), amount, weight), 1.0)
            scale.connectTo(joint.getPlug("scaleY"))
            scale.connectTo(joint.getPlug("scaleZ"))
        deform.append(joint)
    spine.fk, spine.deform = fk, deform
    return spine


if __name__ == "__main__":
    build()
