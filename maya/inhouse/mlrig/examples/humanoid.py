"""一般的な人間の全身骨格と、骨ごとの簡易プロキシメッシュを作る。

関節名は UE のマネキン / MetaHuman でよく使われる名前にそろえる。身長は約170cm(cm単位)、
Y が上、+Z が正面、キャラクターの左が +X。既定は Tポーズで、pose="A" なら腕を肩から45度下ろした
Aポーズを基準(回転0)にする。各関節は子の方向をローカル X 軸にし、
右半身は左半身を鏡像(mirrorBehavior)にして作る。プロキシメッシュは骨ごとの円柱・箱・球で、
関節の子にするので一緒に動く。リファレンス表示(ビューポートで選択できない)にして関節を選びやすくする。
"""

from maya import cmds

import math

from mlib.decorator import undoTransaction

# 体幹。(名前, 親, ワールド位置 cm)。
TORSO = [
    ("root", None, (0, 0, 0)),
    ("pelvis", "root", (0, 95, 0)),
    ("spine_01", "pelvis", (0, 105, 0)),
    ("spine_02", "spine_01", (0, 117, -0.5)),
    ("spine_03", "spine_02", (0, 130, -1)),
    ("neck_01", "spine_03", (0, 148, -1.5)),
    ("head", "neck_01", (0, 157, 0)),
]
# 左腕と左脚。右は鏡像で作る。
LEFT_LIMBS = [
    ("clavicle_l", "spine_03", (3, 143, -1)),
    ("upperarm_l", "clavicle_l", (17, 143, -3)),
    ("lowerarm_l", "upperarm_l", (45, 143, -3)),
    ("hand_l", "lowerarm_l", (71, 143, -3)),
    ("thigh_l", "pelvis", (9, 92, 0)),
    ("calf_l", "thigh_l", (9, 50, 1)),
    ("foot_l", "calf_l", (9, 8, -3)),
    ("ball_l", "foot_l", (9, 1, 11)),
]
# 指。(名前, 付け根のワールド位置, 3関節それぞれの長さ, 伸びる向き)。親は hand_l。
FINGERS = [
    ("thumb", (74, 141, 1.5), (4.5, 3.5, 3.0), (0.6, -0.15, 0.8)),
    ("index", (80, 143, 2.4), (4.5, 2.8, 2.3), (1, 0, 0.05)),
    ("middle", (80.5, 143, 0.7), (5.0, 3.2, 2.5), (1, 0, 0)),
    ("ring", (80, 143, -1.0), (4.6, 3.0, 2.4), (1, 0, -0.05)),
    ("pinky", (79, 142.5, -2.6), (3.6, 2.4, 2.0), (1, -0.05, -0.1)),
]
# プロキシ。部位名 → (形, 寸法)。寸法は関節のローカル軸(X が骨の向き)で表す。cylinder は半径(子までの
# 長さで伸ばす)、box は (X, Y, Z) の大きさで X 方向へずらして置く、pelvis は (X, Y, Z) で関節を中心に置く、
# sphere は半径、foot は (Y, Z)(X は子までの長さ)。
PROXY = {
    "pelvis": ("pelvis", (16, 20, 30)),
    "spine_01": ("cylinder", 12.5), "spine_02": ("cylinder", 13.5), "spine_03": ("cylinder", 15),
    "neck_01": ("cylinder", 5),
    "head": ("sphere", 10.5),
    "clavicle": ("cylinder", 3.5), "upperarm": ("cylinder", 5.5), "lowerarm": ("cylinder", 4.5),
    "hand": ("box", (9, 2.6, 8.5)),
    "thigh": ("cylinder", 8), "calf": ("cylinder", 6),
    "foot": ("foot", (8.5, 7)),
    "ball": ("box", (8, 3.5, 8)),
    "finger": ("cylinder", 0.85),
}
# Aポーズで腕を下ろす角度(度)。upperarm の位置を中心に、腕と指を前から見て時計回りに回す。
A_POSE_ANGLE = 45.0
# 2番目の軸。体幹と脚は前(Z)、腕・指・足先は上(Y)。
SECONDARY = (("pelvis", "zup"), ("clavicle_l", "yup"), ("thigh_l", "zup"), ("foot_l", "yup"))


def _armDown(position, pose):
    """Aポーズなら、upperarm の位置を中心に腕の点を A_POSE_ANGLE だけ下ろす(前から見て時計回り)。"""
    if pose != "A":
        return tuple(position)
    pivot = dict((name, p) for name, _, p in LEFT_LIMBS)["upperarm_l"]
    angle = -math.radians(A_POSE_ANGLE)
    x, y = position[0]-pivot[0], position[1]-pivot[1]
    return (pivot[0]+x*math.cos(angle)-y*math.sin(angle), pivot[1]+x*math.sin(angle)+y*math.cos(angle),
            position[2])


ARM_JOINTS = ("lowerarm_l", "hand_l")


def _leftSpecs(fingers, pose="T"):
    """左半身の関節(名前, 親, ワールド位置)。指を含めるか・姿勢を選ぶ。"""
    specs = [(name, parent, _armDown(position, pose) if name in ARM_JOINTS else position)
             for name, parent, position in LEFT_LIMBS]
    if fingers:
        for finger, base, lengths, direction in FINGERS:
            norm = math.sqrt(sum(v*v for v in direction))
            unit = [v/norm for v in direction]
            position, parent = list(base), "hand_l"
            for i, length in enumerate(lengths, 1):
                name = "{}_{:02d}_l".format(finger, i)
                specs.append((name, parent, _armDown(position, pose)))
                position = [p+u*length for p, u in zip(position, unit)]
                parent = name
    return specs


def jointNames(fingers=True):
    """作る関節の名前(接頭辞なし)。左右・指を含む。

    Args:
        fingers (bool): 指を含める。

    Returns:
        list[str]: 体幹・左半身・右半身の順。
    """
    left = [name for name, _, _ in _leftSpecs(fingers)]
    return [name for name, _, _ in TORSO]+left+[name[:-2]+"_r" for name in left]


def _proxySpec(name):
    """関節名(接頭辞なし)からプロキシの形と寸法を返す。対象外なら None。"""
    base = name[:-2] if name.endswith(("_l", "_r")) else name
    if any(base.startswith(finger) for finger, *_ in FINGERS):
        return PROXY["finger"]
    return PROXY.get(base)


def _addProxy(joint, name, child, material_group):
    """関節の子として、その骨の簡易プロキシメッシュを作る。

    子の関節がある骨は、関節のローカル X 軸(子の方向)に沿って伸ばす。

    Args:
        joint (str): 関節。
        name (str): 接頭辞なしの関節名。
        child (str | None): 骨の長さを決める子の関節。
        material_group (str): 割り当てる shadingEngine。

    Returns:
        str | None: 作ったメッシュ。
    """
    spec = _proxySpec(name)
    if spec is None:
        return None
    shape, size = spec
    length = cmds.getAttr(child+".translateX") if child else 0.0
    mesh_name = joint.split("|")[-1]+"_proxy"
    offset = length/2.0
    if shape == "cylinder" and child:
        mesh = cmds.polyCylinder(name=mesh_name, radius=size, height=abs(length), axis=(1, 0, 0),
                                 subdivisionsAxis=12, constructionHistory=False)[0]
    elif shape == "foot" and child:
        mesh = cmds.polyCube(name=mesh_name, width=abs(length), height=size[1], depth=size[0],
                             constructionHistory=False)[0]
    elif shape == "pelvis":
        mesh = cmds.polyCube(name=mesh_name, width=size[0], height=size[1], depth=size[2],
                             constructionHistory=False)[0]
        offset = 0.0
    elif shape == "sphere":
        mesh = cmds.polySphere(name=mesh_name, radius=size, subdivisionsX=16, subdivisionsY=12,
                               constructionHistory=False)[0]
        offset = size*0.75
    elif shape == "box":
        width, height, depth = size
        mesh = cmds.polyCube(name=mesh_name, width=width, height=height, depth=depth, constructionHistory=False)[0]
        offset = length/2.0 if child else width/2.0
    else:
        return None
    mesh = cmds.parent(mesh, joint, relative=True)[0]
    cmds.setAttr(mesh+".translateX", offset)
    cmds.sets(mesh, edit=True, forceElement=material_group)
    proxy_shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
    cmds.setAttr(proxy_shape+".overrideEnabled", True)
    cmds.setAttr(proxy_shape+".overrideDisplayType", 2)
    return mesh


@undoTransaction("mlrig.examples.humanoid.build")
def build(prefix="", fingers=True, proxy=True, pose="T"):
    """全身の骨格と簡易プロキシメッシュを作る。

    Args:
        prefix (str): 関節・メッシュ名の接頭辞。同じシーンに複数作るときに使う。
        fingers (bool): 指(親指〜小指、各3関節)を作る。
        proxy (bool): 骨ごとの簡易プロキシメッシュを作る。
        pose (str): "T" は Tポーズ、"A" は腕を肩から45度下ろした Aポーズ。どちらも、その姿勢で回転が0。

    Returns:
        dict: root(ルート関節)、joints(接頭辞なしの名前 → 関節)、meshes(プロキシメッシュ)、
            proxySet(プロキシメッシュをまとめたセット。プロキシなしなら None)。

    Raises:
        ValueError: 同じ名前のノードがすでにある、または pose が "T"・"A" 以外。
    """
    if pose not in ("T", "A"):
        raise ValueError("pose must be 'T' or 'A'")
    names = jointNames(fingers)
    for name in names:
        if cmds.objExists(prefix+name):
            raise ValueError("Node already exists: " + prefix+name)

    joints, parent_of = {}, {}
    # mirrorJoint の名前置き換えは名前の中の "_l" をすべて置き換えるので、作る間は "_l" を末尾にしか
    # 持たない一時的な名前を使い、最後に接頭辞+関節名へ付け直す。
    temporary = "humanoidTmp{}".format(len(cmds.ls(type="joint")))
    while cmds.ls(temporary+"*"):
        temporary += "x"

    def create(specs):
        """ワールド位置から関節を作って親へ入れる。"""
        for name, parent, position in specs:
            cmds.select(clear=True)
            joint = cmds.joint(name=temporary+name, position=position)
            if parent:
                joint = cmds.parent(joint, joints[parent])[0]
            joints[name], parent_of[name] = joint, parent

    def zeroEnds():
        """末端の関節は向きを親にそろえる(子がなく X 軸の向きが決まらないため)。"""
        for name in joints:
            if not any(parent_of.get(child) == name for child in joints):
                cmds.setAttr(joints[name]+".jointOrient", 0, 0, 0)

    # 体幹と手足。手は指を付ける前に向きを決め、前腕と同じ向き(X が腕の先)にする。
    create(TORSO+_leftSpecs(False, pose))
    for name, secondary in SECONDARY:
        cmds.joint(joints[name], edit=True, orientJoint="xyz", secondaryAxisOrient=secondary, children=True,
                   zeroScaleOrient=True)
    zeroEnds()
    if fingers:
        specs = [spec for spec in _leftSpecs(True, pose) if spec[0] not in joints]
        create(specs)
        for finger, *_ in FINGERS:
            cmds.joint(joints["{}_01_l".format(finger)], edit=True, orientJoint="xyz", secondaryAxisOrient="yup",
                       children=True, zeroScaleOrient=True)
        zeroEnds()

    # 右半身は左の鏡像。mirrorBehavior で左右の回転が対称に動く。
    for name in ("clavicle_l", "thigh_l"):
        cmds.mirrorJoint(joints[name], mirrorYZ=True, mirrorBehavior=True, searchReplace=("_l", "_r"))
    for name in list(joints):
        if name.endswith("_l"):
            right = name[:-2]+"_r"
            joints[right] = cmds.ls(temporary+right)[0]
            parent = parent_of[name]
            parent_of[right] = parent[:-2]+"_r" if parent.endswith("_l") else parent
    # 正式な名前へ付け直す。親から順に付け直しても子の名前は変わらない。
    for name in names:
        cmds.rename(temporary+name, prefix+name)
    for name in names:
        joints[name] = cmds.ls(prefix+name)[0]

    meshes, proxy_set = [], None
    if proxy:
        material = cmds.shadingNode("lambert", asShader=True, name=prefix+"humanProxy_mat")
        cmds.setAttr(material+".color", 0.55, 0.6, 0.68, type="double3")
        cmds.setAttr(material+".transparency", 0.45, 0.45, 0.45, type="double3")
        material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=prefix+"humanProxy_SG")
        cmds.connectAttr(material+".outColor", material_group+".surfaceShader")
        for name in names:
            children = [child for child in names if parent_of.get(child) == name]
            # 骨の長さは子が1つのときだけ子までとする(骨盤・手は子が複数なので箱を置く)。
            child = joints[children[0]] if len(children) == 1 else None
            mesh = _addProxy(joints[name], name, child, material_group)
            if mesh:
                meshes.append(mesh)
        proxy_set = cmds.sets(meshes, name=prefix+"humanProxy_set")
    cmds.select(joints["root"])
    return {"root": joints["root"], "joints": joints, "meshes": meshes, "proxySet": proxy_set}
