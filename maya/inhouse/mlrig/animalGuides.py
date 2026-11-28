"""非人型のガイドとFK骨を部位ごとの配置から作成する。Yが上、Zが前方。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction


_HIND = (("hip", None, (0, 4, 0)), ("knee", "hip", (0, -1.7, 0.6)), ("hock", "knee", (0, -1.3, -0.8)))
_PRESETS = {
    "plantigrade": (
        ("hip", None, (0, 4, 0)),
        ("knee", "hip", (0, -2, 0.4)),
        ("heel", "knee", (0, -2, -0.4)),
        ("ball", "heel", (0, 0, 0.7)),
        ("toe", "ball", (0, 0, 0.5)),
    ),
    "digitigrade": _HIND + (("ball", "hock", (0, -1, 0.4)), ("toe", "ball", (0, 0, 0.6))),
    "unguligrade": _HIND + (("fetlock", "hock", (0, -0.65, 0.15)), ("hoof", "fetlock", (0, -0.35, 0.35))),
    "bird": _HIND + (("foot", "hock", (0, -1, 0.2)), ("frontToe", "foot", (0, 0, 0.65)), ("rearToe", "foot", (0, 0, -0.45))),
    "tail": (("base", None, (0, 0, 0)), ("mid", "base", (0, 0, -1)), ("tip", "mid", (0, 0, -1))),
    "wheel": (("body", None, (0, 1, 0)), ("axle", "body", (1, 0, 0)), ("rim", "axle", (0, -1, 0))),
}
ITEMS = (
    ("plantigrade", "蹠行の脚"),
    ("digitigrade", "趾行の脚"),
    ("unguligrade", "蹄行の脚"),
    ("bird", "鳥の脚と前後指"),
    ("tail", "尾"),
    ("wheel", "車体と車輪"),
)


def _member(root, name):
    plug = root + "." + name
    if not cmds.objExists(plug):
        return None
    source = cmds.connectionInfo(plug, sourceFromDestination=True)
    if not source:
        raise ValueError("登録された部品が見つかりません: " + name)
    return ([item.getName(full=True) for item in mlib.ls(source.rpartition(".")[0], long=True)] or [None])[0]


def _record(root, name, node):
    cmds.addAttr(root, longName=name, attributeType="message")
    cmds.connectAttr(node + ".message", root + "." + name)


@undoTransaction("mlrigAnimalGuides")
def create(kind):
    """部位のモデル合わせに使うガイドを作る。"""
    spec = _PRESETS[kind]
    root = mlib.createNode("transform", name=kind + "Rig#").getName()
    cmds.addAttr(root, longName="mlrigAnimalPreset", dataType="string")
    cmds.setAttr(root + ".mlrigAnimalPreset", kind, type="string", lock=True)
    for role, parent, translation in spec:
        guide = cmds.spaceLocator(name=root + "_" + role + "Guide")[0]
        guide = cmds.parent(guide, _member(root, "guide_" + parent) if parent else root, relative=True)[0]
        cmds.setAttr(guide + ".translate", *translation)
        _record(root, "guide_" + role, guide)
    mlib.select(root)
    return root


@undoTransaction("mlrigAnimalBones")
def build(root):
    """ガイドのローカル姿勢をFK骨の基準姿勢に適用し、既存骨・キーを保持する。"""
    if not cmds.objExists(root + ".mlrigAnimalPreset"):
        raise ValueError("非人型プリセットのルートを選択してください")
    spec = _PRESETS[cmds.getAttr(root + ".mlrigAnimalPreset")]
    from . import buildStages
    from .definition import JointSpec, RigDefinition

    ordered = RigDefinition("unit", tuple(JointSpec(*row) for row in spec), ()).joint_order()
    entries = buildStages.declarations(root, {joint.id for joint in ordered})
    prefix = root.rpartition("|")[2]
    result = {}
    for joint in ordered:
        role = joint.id
        buildStages.run(root, entries, "guide", role, _member(root, "guide_" + role))
    for joint in ordered:
        role, parent = joint.id, joint.parent
        guide = _member(root, "guide_" + role)
        expected = _member(root, "guide_" + parent) if parent else [item.getName(full=True) for item in mlib.ls(root, long=True)][0]
        if (cmds.listRelatives(guide, parent=True, fullPath=True) or []) != [expected]:
            raise ValueError("ガイドの親役割が変更されています: " + role)
        bone = _member(root, "bone_" + role)
        bone_parent = result[parent] if parent else root
        if bone is None:
            bone = mlib.createNode("joint", name=prefix + "_" + role, parent=bone_parent).getName()
            _record(root, "bone_" + role, bone)
        elif cmds.listRelatives(bone, parent=True, fullPath=True) != [item.getName(full=True) for item in mlib.ls(bone_parent, long=True)]:
            raise ValueError("骨の親役割が変更されています: " + role)
        cmds.setAttr(bone + ".offsetParentMatrix", *cmds.getAttr(guide + ".matrix"), type="matrix")
        result[role] = bone
        buildStages.run(root, entries, "bone", role, bone)
    for role, bone in result.items():
        buildStages.run(root, entries, "finish", role, bone)
    return result
