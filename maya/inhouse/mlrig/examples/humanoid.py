"""一般的な人間の全身骨格と、骨ごとの簡易プロキシメッシュを作る。

関節名は UE のマネキン / MetaHuman でよく使われる名前にそろえる。身長は約170cm(cm単位)、
Y が上、+Z が正面、キャラクターの左が +X。既定は Tポーズで、pose="A" なら腕を肩から45度下ろした
Aポーズを基準(回転0)にする。各関節は子の方向をローカル X 軸にし、
右半身は左半身を鏡像(mirrorBehavior)にして作る。プロキシメッシュは骨ごとの円柱・箱・球で、
関節の子にするので一緒に動く。リファレンス表示(ビューポートで選択できない)にして関節を選びやすくする。
"""

import math

import maya.cmds as cmds
import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector
from mlib.nodes import Joint

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
# 子が複数あっても、骨の長さをこの子までとする関節(胸は首まで)。
LENGTH_CHILD = {"spine_03": "neck_01"}
# Aポーズで腕を下ろす角度(度)。upperarm の位置を中心に、腕と指を前から見て時計回りに回す。
A_POSE_ANGLE = 45.0
# 2番目の軸。体幹と脚は前(Z)、腕・指・足先は上(Y)。
SECONDARY = (("pelvis", "zup"), ("clavicle_l", "yup"), ("thigh_l", "zup"), ("foot_l", "yup"))
ARM_JOINTS = ("lowerarm_l", "hand_l")


def _armDown(position, pose):
    """Aポーズなら、upperarm の位置を中心に腕の点を A_POSE_ANGLE だけ下ろす(前から見て時計回り)。"""
    if pose != "A":
        return tuple(position)
    pivot = dict((name, p) for name, _, p in LEFT_LIMBS)["upperarm_l"]
    angle = -math.radians(A_POSE_ANGLE)
    x, y = position[0]-pivot[0], position[1]-pivot[1]
    return (pivot[0]+x*math.cos(angle)-y*math.sin(angle), pivot[1]+x*math.sin(angle)+y*math.cos(angle),
            position[2])


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
        material_group (str | ShadingEngine): 割り当てるshadingEngine。

    Returns:
        str | None: 作ったメッシュ。
    """
    spec = _proxySpec(name)
    if spec is None:
        return None
    shape, size = spec
    length = mlib.nodes.Node(child).getPlug("translateX").get(uiUnits=True) if child else 0.0
    mesh_name = joint.split("|")[-1]+"_proxy"
    offset = length/2.0
    # 大きさは現在の距離単位で決めているため、作成関数の内部単位(cm)へ換算して渡す。
    ui = mlib.common.units.distanceFromUi
    if shape == "cylinder" and child:
        mesh = mlib.createPolyCylinder(radius=ui(size), height=ui(abs(length)), subdivisions=(12, 1, 1),
                                       axis=(1, 0, 0), name=mesh_name).getParent()
    elif shape == "foot" and child:
        mesh = mlib.createPolyCube(width=ui(abs(length)), height=ui(size[1]), depth=ui(size[0]), name=mesh_name).getParent()
    elif shape == "pelvis":
        mesh = mlib.createPolyCube(width=ui(size[0]), height=ui(size[1]), depth=ui(size[2]), name=mesh_name).getParent()
        offset = 0.0
    elif shape == "sphere":
        mesh = mlib.createPolySphere(radius=ui(size), subdivisions=(16, 12), name=mesh_name).getParent()
        offset = size*0.75
    elif shape == "box":
        width, height, depth = size
        mesh = mlib.createPolyCube(width=ui(width), height=ui(height), depth=ui(depth), name=mesh_name).getParent()
        offset = length/2.0 if child else width/2.0
    else:
        return None
    mesh.setParent(joint, relative=True)
    mesh.getPlug("translateX").set(offset, uiUnits=True)
    mlib.nodes.Node(material_group).assign(mesh)
    proxy_shape = mesh.getShape()
    proxy_shape.getPlug("overrideEnabled").set(True)
    proxy_shape.getPlug("overrideDisplayType").set(2)
    return mesh_name


def _orientChain(root, secondary):
    """例示骨格のX軸を子へ、Y軸を指定のワールド上方向へそろえる。

    ジョイントを親から順に編集し、全関節のワールド位置を保持する。
    この例の新規・等倍・回転0の骨格を対象とし、一般的なjoint編集APIは追加しない。
    向きと移動の書込みはmlibの通常setterを使い、呼出し側のUndoへまとめる。

    Args:
        root (str): 向きを合わせる階層のルートJoint。
        secondary (str): yupはワールドY、zupはワールドZをローカルYの基準にする。

    Raises:
        ValueError: 子の方向と上方向が平行で、基準を決められない場合。
    """
    nodes = mlib.nodes.Node(root).getChildren(allDescendents=True, order="breadthFirst", includeSelf=True)
    positions = {node.getUuid(): Vector(node.getMatrix(worldSpace=True).translate) for node in nodes}
    up = Vector(0, 1, 0) if secondary == "yup" else Vector(0, 0, 1)
    for node in nodes:
        position = positions[node.getUuid()]
        children = node.getChildren()
        frame = None
        if children:
            x_axis = (positions[children[0].getUuid()] - position).normal()
            y_axis = up - x_axis * (up * x_axis)
            if y_axis.length() < 1e-10:
                raise ValueError("Cannot orient a bone parallel to its reference up axis")
            y_axis = y_axis.normal()
            z_axis = (x_axis ^ y_axis).normal()
            frame = Matrix((x_axis.x, x_axis.y, x_axis.z, 0,
                            y_axis.x, y_axis.y, y_axis.z, 0,
                            z_axis.x, z_axis.y, z_axis.z, 0,
                            position.x, position.y, position.z, 1))
        parent = node.getParent()
        parent_inverse = parent.getMatrix(worldSpace=True).inverse() if parent else Matrix()
        node.getPlug("translate").set(parent_inverse.transformPoint(position))
        if frame is not None:
            node.getPlug("rotateAxis").set((0, 0, 0))
            node.getPlug("jointOrient").set((frame * parent_inverse).quaternion.asEulerRotation())


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
        if mlib.objExists(prefix+name):
            raise ValueError("Node already exists: " + prefix+name)

    joints, parent_of = {}, {}
    # mirrorJoint の名前置き換えは名前の中の "_l" をすべて置き換えるので、作る間は "_l" を末尾にしか
    # 持たない一時的な名前を使い、最後に接頭辞+関節名へ付け直す。
    temporary = "humanoidTmp{}".format(len(mlib.ls(type="joint")))
    while mlib.ls(temporary+"*"):
        temporary += "x"

    def create(specs):
        """ワールド位置から関節を作って親へ入れる。"""
        for name, parent, position in specs:
            mlib.select(clear=True)
            node = mlib.createNode("joint", name=temporary+name)
            node.getPlug("translate").set(position, uiUnits=True)
            if parent:
                node.setParent(joints[parent])
            joint = node.getName()
            joints[name], parent_of[name] = joint, parent

    def zeroEnds():
        """末端の関節は向きを親にそろえる(子がなく X 軸の向きが決まらないため)。"""
        for name in joints:
            if not any(parent_of.get(child) == name for child in joints):
                mlib.nodes.Node(joints[name]).getPlug("jointOrient").set((0, 0, 0))

    # 体幹と手足。手は指を付ける前に向きを決め、前腕と同じ向き(X が腕の先)にする。
    create(TORSO+_leftSpecs(False, pose))
    for name, secondary in SECONDARY:
        _orientChain(joints[name], secondary)
    zeroEnds()
    if fingers:
        specs = [spec for spec in _leftSpecs(True, pose) if spec[0] not in joints]
        create(specs)
        for finger, *_ in FINGERS:
            _orientChain(joints["{}_01_l".format(finger)], "yup")
        zeroEnds()

    # 右半身は左の鏡像。mirrorBehavior で左右の回転が対称に動く。
    for name in ("clavicle_l", "thigh_l"):
        mirrored = mlib.nodes.Node(joints[name]).mirror("YZ", behavior=True, searchReplace=("_l", "_r"))
        for joint in mirrored.getChildren(allDescendents=True, includeSelf=True):
            if not isinstance(joint, Joint):
                continue
            orient = joint.getPlug("jointOrient")
            # 等価解の判定はラジアンで行う。
            values = tuple(orient.get(unit="rad"))
            # 行列の丸めで右大腿の-180度が+180度側へ出るのを避ける。
            # 2πだけずらす等価なEuler値なので、姿勢や子の位置は変えない。
            adjusted = tuple(value - 2 * math.pi if abs(value - math.pi) < 1e-7 else value
                             for value in values)
            if adjusted != values:
                orient.set(adjusted, unit="rad")
    for name in list(joints):
        if name.endswith("_l"):
            right = name[:-2]+"_r"
            joints[right] = mlib.nodes.Node(temporary+right).getName()
            parent = parent_of[name]
            parent_of[right] = parent[:-2]+"_r" if parent.endswith("_l") else parent
    # 正式な名前へ付け直す。親から順に付け直しても子の名前は変わらない。
    for name in names:
        mlib.nodes.Node(temporary+name).rename(prefix+name)
    for name in names:
        joints[name] = mlib.nodes.Node(prefix+name).getName()

    meshes, proxy_set = [], None
    if proxy:
        material = mlib.nodes.Node(cmds.shadingNode("lambert", asShader=True, name=prefix+"humanProxy_mat"))
        material.getPlug("color").set((0.55, 0.6, 0.68))
        material.getPlug("transparency").set((0.45, 0.45, 0.45))
        material_group = mlib.nodes.Node(cmds.sets(
            renderable=True, noSurfaceShader=True, empty=True, name=prefix+"humanProxy_SG"
        ))
        material_group.setShader(material)
        for name in names:
            children = [child for child in names if parent_of.get(child) == name]
            # 骨の長さは子が1つのときだけ子までとする(骨盤・手は子が複数なので箱を置く)。
            # 胸(spine_03)は首・左右の鎖骨が子なので、LENGTH_CHILD で首までの長さにする。
            if name in LENGTH_CHILD:
                children = [LENGTH_CHILD[name]]
            child = joints[children[0]] if len(children) == 1 else None
            mesh = _addProxy(joints[name], name, child, material_group)
            if mesh:
                meshes.append(mesh)
        proxy_set = mlib.createNode("objectSet", name=prefix+"humanProxy_set", skipSelect=True)
        proxy_set = proxy_set.addMembers(*meshes).getName()
    mlib.select(joints["root"])
    return {"root": joints["root"], "joints": joints, "meshes": meshes, "proxySet": proxy_set}
