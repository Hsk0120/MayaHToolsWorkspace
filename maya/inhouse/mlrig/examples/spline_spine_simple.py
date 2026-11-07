"""スプラインIKの背骨のサンプル(:mod:`mlrig.examples.spline_spine`)を、読みやすく組み直した簡易版。

元のサンプルとの違い:

* コンテナを使わない(``mlrig.setups.SplineIK`` を使わず、カーブとIKハンドルをこのファイルで直接作る)。
* マトリクスのノード(multMatrix・decomposeMatrix・pickMatrix・blendMatrix)を使わず、
  追従はすべてコンストレイント(parent・point・orient)で行う。
* 接線の長さの倍率(``tangentHips``・``tangentChest``)を作らない。接線のコントローラーはそのまま残す。
* ``fk=False`` で、FKコントローラーと ``lockOri*`` を作らない版にできる(変形用の骨をIKの骨列と腰・胸へ直接追従させる)。

構成(``name="spine"`` のとき)::

    spine_rig
    ├ spine_ctrl_grp
    │  └ spine_cog_npo / spine_cog_ctrl        全体の移動。アトリビュート(下記)もここに置く
    │     ├ spine_hips_npo / spine_hips_ctrl      腰(カーブの始点)
    │     │  └ spine_tan0_npo / spine_tan0_ctrl   腰側の接線(移動のみ)
    │     ├ spine_chest_npo / spine_chest_ctrl    胸(カーブの終点)
    │     │  └ spine_tan1_npo / spine_tan1_ctrl   胸側の接線(移動のみ)
    │     └ spine_fk_grp / spine_fk01_npo / spine_fk01_ctrl / spine_fk02_npo ...   FK(階層)
    ├ spine_setup_grp(非表示)    カーブ・CVの位置・IKの骨列・ハンドル・向きの固定
    └ spine_deform_grp           変形用の骨(スキンに使う)

しくみ:

1. CV: ``spine_cv0``〜``cv3`` を腰・接線・胸へ pointConstraint し、その translate をカーブの CV へつなぐ。
2. IK: スプラインIK(ねじれは腰・胸の回転から取る)で、IKの骨列をカーブに沿わせる。
3. 向きの固定: ``spine_hipsLock``・``spine_chestLock`` を最下段・最上段のIKの骨へ pointConstraint し、
   向きは「IKの骨」と「腰・胸のコントローラー」の2つへの parentConstraint(maintainOffset、translate は
   スキップ)で決める(ウェイトを ``lockOriHips``・``lockOriChest`` と ``1 - その値`` にする)。
4. FK: 段ごとの「一つ下の段から見た向きと位置」を、一つ下の段の子にした ``spine_fk02_local`` 等の
   parentConstraint で測り、その translate・rotate をFKのオフセット(npo)へつなぐ。
   FKコントローラーを回すと上の段が一緒に回る。
5. 変形用の骨は、FKコントローラーへ parentConstraint する。``fk=False`` のときは 4 を作らず、
   3 も作らず(``lockOri*`` も無い)、中間の段はIKの骨へ parentConstraint する。最下段は腰のコントローラーへ
   parentConstraint、最上段は位置をIKの骨への pointConstraint、向きを胸のコントローラーへの
   orientConstraint で取る(どちらも maintainOffset で、コントローラーと骨の軸の違いをオフセットにする)。

骨は「X が上(子の方向)、Z が正面」。``spine_cog_ctrl`` のアトリビュート:

* ``maxStretch``(既定 1.5)・``maxSquash``(既定 0.5): カーブの長さの比を、この範囲に収めて骨を伸縮する。
* ``volume``(0〜1、既定 1): 伸びると細く、縮むと太くする(両端は0、中央で最大)。
* ``lockOriHips``・``lockOriChest``(0〜1、既定 1): 1 なら最下段・最上段の骨の向きを腰・胸の
  コントローラーの回転に合わせる。0 ならカーブに沿う向き。``fk=False`` では作らない(常に 1 と同じ)。

``stretch=False`` にすると、伸縮と体積の保持を入れない(``maxStretch``・``maxSquash``・``volume`` も作らない)。
``fk=False`` にすると、FKコントローラー(``spine_fk_grp`` 以下)と ``lockOri*`` を作らない。

使い方::

    from mlrig.examples import spline_spine_simple
    spine = spline_spine_simple.build(name="spine", joint_count=6, length=50.0, height=100.0)
    spine.chest   # 胸のコントローラー(mlib の Node)
    noFk = spline_spine_simple.build(name="noFkSpine", fk=False)   # FKコントローラーなし
"""

import math
import re

import mlib
from mlib.decorator import preservedSelection, undoTransaction

from mlrig.setups.controlShape import ControlShape

#: コントローラーの色(Mayaのインデックスカラー)。
COLORS = {"cog": 22, "ik": 18, "tangent": 9, "fk": 17}


class SimpleSplineSpine:
    """``build()`` が作った背骨の各ノードをまとめる。

    Attributes:
        root (Node): リグ全体のルート。
        cog (Node): 全体を動かすコントローラー。アトリビュートもここにある。
        hips (Node): 腰のコントローラー(カーブの始点)。
        chest (Node): 胸のコントローラー(カーブの終点)。
        tangents (list[Node]): 腰側・胸側の接線のコントローラー。
        fk (list[Node]): 根元から順のFKコントローラー(``fk=False`` なら空)。
        deform (list[Node]): 根元から順の変形用の骨。
        ik (list[Node]): スプラインIKが回す骨列(非表示)。
        curve (Node): スプラインのカーブ(transform)。
        handle (Node): スプラインIKのハンドル。
    """

    def __init__(self, **members):
        """各ノードを受け取る。

        Args:
            **members: 上の Attributes の名前と値。
        """
        self.__dict__.update(members)


def _cm(value):
    """cm の値を、シーンの長さの単位の値にする。

    Args:
        value (float): cm の値。

    Returns:
        float: シーンの長さの単位の値。
    """
    return mlib.common.units.distanceFromUi(value)


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
        node.getPlug("translate").set(tuple(_cm(v) for v in translate))
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
        ControlShape.circle(control, radius, vector, color, name="{}_ctrlShape{}".format(name, index or ""))
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


def _lock(name, parent, joint, control, weight):
    """骨の位置にあり、向きを「骨」と「コントローラー」の間で ``weight`` の割合で混ぜる transform を作る。

    位置は骨への pointConstraint で取り、向きは骨とコントローラーの2つへの parentConstraint
    (translate はスキップ)で混ぜる。parentConstraint の maintainOffset はターゲットごとに別の
    オフセットを持つので、コントローラーと骨の軸の違い(コントローラーは Y が上、骨は X が上)を
    コントローラー側のオフセットが吸収し、``weight`` がどの値でも作成時の姿勢は変わらない
    (orientConstraint の maintainOffset はターゲット全体で1つのオフセットになり、ウェイトを変えるとずれる)。

    Args:
        name (str): 名前。
        parent (Node): 親(セットアップのグループ)。
        joint (Node): スプラインIKの骨。
        control (Node): 向きを合わせるコントローラー。
        weight (Plug): 0〜1 の割合。1 でコントローラーの向き。

    Returns:
        Node: 作った transform。
    """
    lock = _transform(name, parent)
    # 作成時に骨と同じ向きにしてからオフセットを取る(骨側のオフセットを 0 にする)。
    lock.matchTransform(joint, position=False, scale=False)
    lock.addConstraint(joint, type="point")
    orient = lock.addConstraint([joint, control], type="parent", maintainOffset=True,
                                skipTranslate=("x", "y", "z"))
    orient.getPlug("interpType").set(2)  # Shortest(回転の差が小さい方で混ぜる)
    jointWeight, controlWeight = orient.getWeightPlugs()
    reverse = _node("reverse", name + "_reverse")
    weight.connectTo(reverse.getPlug("inputX"))
    reverse.getPlug("outputX").connectTo(jointWeight)
    weight.connectTo(controlWeight)
    return lock


def build(name="spine", joint_count=6, length=50.0, height=100.0, stretch=True, fk=True):
    """スプラインIKの背骨の簡易版を、ワールドの +Y 方向に作る。

    作成全体を1回の Undo にまとめ、元の選択を保つ。

    Args:
        name (str): 名前の前半(英数字と ``_``)。``<name>_rig`` が既にあればエラー。
        joint_count (int): 骨の数(末端の胸を含む)。4〜32。
        length (float): 腰から胸までの長さ(cm)。
        height (float): 腰の高さ(cm)。
        stretch (bool): False なら伸縮と体積の保持を入れない(骨の長さは固定)。
        fk (bool): False ならFKコントローラーと ``lockOri*`` を作らず、変形用の骨をIKの骨列と腰・胸へ直接追従させる。

    Returns:
        SimpleSplineSpine: 作ったノード。

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
        return _build(name, joint_count, float(length), float(height), bool(stretch), bool(fk))


@undoTransaction("mlrig.examples.spline_spine_simple.build")
def _build(name, count, length, height, stretch, useFk):
    """``build()`` の本体。

    Args:
        name (str): 名前の前半。
        count (int): 骨の数。
        length (float): 長さ(cm)。
        height (float): 腰の高さ(cm)。
        stretch (bool): 伸縮と体積の保持を入れるか。
        useFk (bool): FKコントローラーを作るか。

    Returns:
        SimpleSplineSpine: 作ったノード。
    """
    segment = length / (count - 1)
    root = _transform(name + "_rig")
    ctrlGroup = _transform(name + "_ctrl_grp", root)
    setupGroup = _transform(name + "_setup_grp", root)
    deformGroup = _transform(name + "_deform_grp", root)
    setupGroup.getPlug("visibility").set(False)

    # ---- コントローラー ----
    _, cog = _control(name + "_cog", ctrlGroup, (0, height, 0), length * 0.55, (0, 1, 0), COLORS["cog"])
    _, hips = _control(name + "_hips", cog, None, length * 0.4, (0, 1, 0), COLORS["ik"])
    _, chest = _control(name + "_chest", cog, (0, length, 0), length * 0.4, (0, 1, 0), COLORS["ik"])
    _, tan0 = _control(name + "_tan0", hips, (0, length / 3.0, 0), length * 0.08, (0, 1, 0),
                       COLORS["tangent"], sphere=True, translateOnly=True)
    _, tan1 = _control(name + "_tan1", chest, (0, -length / 3.0, 0), length * 0.08, (0, 1, 0),
                       COLORS["tangent"], sphere=True, translateOnly=True)

    # ---- アトリビュート(cog に置く) ----
    attributes = [("lockOriHips", 1.0, 0.0, 1.0), ("lockOriChest", 1.0, 0.0, 1.0)] if useFk else []
    if stretch:
        attributes[:0] = [("maxStretch", 1.5, 1.0, None), ("maxSquash", 0.5, 0.0, 1.0), ("volume", 1.0, 0.0, 1.0)]
    for attr, default, minimum, maximum in attributes:
        flags = dict(type="double", defaultValue=default, minValue=minimum, keyable=True)
        if maximum is not None:
            flags["maxValue"] = maximum
        cog.addAttr(attr, **flags)

    # ---- カーブ: CV の位置を pointConstraint で取り、カーブの CV へつなぐ ----
    # カーブと CV の transform はどちらも setup_grp の直下(単位マトリクス)なので、translate がそのまま CV の位置になる。
    points = [(0, height, 0), (0, height + length / 3.0, 0), (0, height + length * 2 / 3.0, 0), (0, height + length, 0)]
    shape = mlib.createCurve([tuple(_cm(v) for v in p) for p in points], degree=3, name=name + "_curve",
                             parent=setupGroup)
    curve = shape.getParent()
    for index, control in enumerate((hips, tan0, tan1, chest)):
        cv = _transform("{}_cv{}".format(name, index), setupGroup)
        cv.addConstraint(control, type="point")
        cv.getPlug("translate").connectTo(shape.getPlug("controlPoints")[index])

    # ---- スプラインIKの骨列(X が上、Z が正面) ----
    ik = []
    parent = setupGroup
    for index in range(count):
        joint = mlib.createNode("joint", name="{}_ik{:02d}_jnt".format(name, index + 1), parent=parent,
                                skipSelect=True)
        if index == 0:
            joint.getPlug("translate").set((0, _cm(height), 0))
            joint.getPlug("jointOrient").set((0, 0, 90))
        else:
            joint.getPlug("translateX").set(_cm(segment))
        ik.append(joint)
        parent = joint
    handle = mlib.createIkHandle(ik[0], ik[-1], solver="ikSplineSolver", name=name + "_ikh", curve=curve,
                                 parentCurve=False, rootOnCurve=True)
    handle.getEffector().rename(name + "_effector")
    handle.setParent(setupGroup)
    # ねじれ: 骨の Z(正面)を、腰・胸のコントローラーの Z に合わせる(Object Rotation Up (Start/End))。
    handle.getPlug("dTwistControlEnable").set(True)
    handle.getPlug("dWorldUpType").set(4)
    handle.getPlug("dForwardAxis").set(0)   # +X
    handle.getPlug("dWorldUpAxis").set(3)   # +Z
    for attr in ("dWorldUpVector", "dWorldUpVectorEnd"):
        handle.getPlug(attr).set((0, 0, 1))
    hips.getPlug("worldMatrix")[0].connectTo(handle.getPlug("dWorldUpMatrix"))
    chest.getPlug("worldMatrix")[0].connectTo(handle.getPlug("dWorldUpMatrixEnd"))

    amount = _stretch(name, root, shape, cog, ik, segment, length) if stretch else None

    # ---- 各段の「実際の向き」: 最下段と最上段は腰・胸の回転へ寄せる(lockOri。FKありのみ) ----
    actual = list(ik)
    if useFk:
        actual[0] = _lock(name + "_hipsLock", setupGroup, ik[0], hips, cog.getPlug("lockOriHips"))
        actual[-1] = _lock(name + "_chestLock", setupGroup, ik[-1], chest, cog.getPlug("lockOriChest"))

    # ---- FK(階層)。fk=False なら作らず、変形用の骨をIKの骨列へ直接追従させる ----
    fk = []
    parent = _transform(name + "_fk_grp", cog) if useFk else None
    for index in range(count if useFk else 0):
        label = "{}_fk{:02d}".format(name, index + 1)
        npo, control = _control(label, parent, None, length * 0.3, (1, 0, 0), COLORS["fk"])
        control.getPlug("rotateOrder").set(3)  # xzy: ねじれ(X)を最初、前後の曲げ(Y)を最後に評価する
        if index == 0:
            npo.addConstraint(actual[0], type="parent")
        else:
            # 一つ下の段の子にした transform を、この段へ parentConstraint すると、その translate・rotate が
            # 「一つ下の段から見たこの段」になる。それを npo へつなぐと、FK の親を回したときに上の段も回る。
            local = _transform(label + "_local", actual[index - 1])
            local.addConstraint(actual[index], type="parent")
            local.getPlug("translate").connectTo(npo.getPlug("translate"))
            local.getPlug("rotate").connectTo(npo.getPlug("rotate"))
        fk.append(control)
        parent = control

    # ---- 変形用の骨(平らに並べ、FKコントローラーへ追従。断面の拡大は Y・Z の scale) ----
    deform = []
    for index, control in enumerate(fk or actual):
        joint = mlib.createNode("joint", name="{}_{:02d}_jnt".format(name, index + 1), parent=deformGroup,
                                skipSelect=True)
        joint.getPlug("radius").set(length * 0.04)
        if not useFk and index in (0, count - 1):
            # FKなしは lockOri を持たず、両端の骨の向きは腰・胸のコントローラーにそのまま合わせる。
            # 作成時に骨をIKの骨へ重ねてから maintainOffset で付け、コントローラーとの軸の違いをオフセットにする。
            joint.matchTransform(ik[index], scale=False)
            if index == 0:
                # IKの根元は常にカーブの始点(= 腰の位置)にあるので、位置も腰から取れる。
                joint.addConstraint(hips, type="parent", maintainOffset=True)
            else:
                # 最上段は伸縮の上限や stretch=False で胸に届かないことがあるので、位置はIKの骨から取る。
                joint.addConstraint(ik[index], type="point")
                joint.addConstraint(chest, type="orient", maintainOffset=True)
        else:
            joint.addConstraint(control, type="parent")
        weight = math.sin(math.pi * index / (count - 1))
        if amount is not None and weight > 1.0e-6:
            scale = _add("{}_{:02d}_volumeScale".format(name, index + 1),
                         _multiply("{}_{:02d}_volumeWeight".format(name, index + 1), amount, weight), 1.0)
            scale.connectTo(joint.getPlug("scaleY"))
            scale.connectTo(joint.getPlug("scaleZ"))
        deform.append(joint)

    curve.getPlug("visibility").set(False)
    handle.getPlug("visibility").set(False)
    return SimpleSplineSpine(root=root, cog=cog, hips=hips, chest=chest, tangents=[tan0, tan1], fk=fk,
                             deform=deform, ik=ik, curve=curve, handle=handle)


def _stretch(name, root, shape, cog, ik, segment, length):
    """伸縮と体積の計算を作り、体積の変化量の Plug を返す。

    Args:
        name (str): 名前の前半。
        root (Node): リグのルート(``scaleY`` をリグの拡大率として読む)。
        shape (Node): スプラインのカーブのシェイプ。
        cog (Node): アトリビュートを持つコントローラー。
        ik (list[Node]): スプラインIKの骨列。
        segment (float): 1本の骨の元の長さ(cm)。
        length (float): 元の長さ(cm)。

    Returns:
        Plug: ``volume × (比^-0.5 - 1)``(段ごとの重みを掛ける前)。
    """
    # ---- 伸縮: 比 = カーブの長さ / (元の長さ × リグの拡大率) を maxSquash〜maxStretch に収める ----
    info = _node("curveInfo", name + "_curveInfo")
    shape.getPlug("worldSpace")[0].connectTo(info.getPlug("inputCurve"))
    restLength = _multiply(name + "_restLength", root.getPlug("scaleY"), _cm(length))
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
        _multiply("{}_ik{:02d}_length".format(name, index + 1), stretch, _cm(segment)).connectTo(
            joint.getPlug("translateX"))

    # ---- 体積: 断面の拡大率 = 1 + volume × 重み × (比^-0.5 - 1)。重みは両端0・中央1 ----
    power = _node("multiplyDivide", name + "_volumePower")
    power.getPlug("operation").set(3)
    stretch.connectTo(power.getPlug("input1X"))
    power.getPlug("input2X").set(-0.5)
    change = _add(name + "_volumeChange", power.getPlug("outputX"), -1.0)
    return _multiply(name + "_volumeAmount", change, cog.getPlug("volume"))


if __name__ == "__main__":
    build()
