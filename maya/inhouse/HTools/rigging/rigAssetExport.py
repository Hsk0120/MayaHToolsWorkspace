"""選択したリグ部位の宣言またはスキンウェイトを型ごとの保存形式で書き出す。"""

import json
from pathlib import Path

import maya.cmds as cmds


def describe(node):
    """実際に保存する型と依存内容を返す。"""
    if cmds.nodeType(node) == "skinCluster":
        shapes = cmds.skinCluster(node, query=True, geometry=True) or []
        joints = cmds.skinCluster(node, query=True, influence=True) or []
        return "Skin weights", ["Geometry: " + ", ".join(shapes), "Required influences: " + ", ".join(joints),
                                "Restore onto a compatible bound geometry with these influences."]
    if not cmds.objExists(node + ".mlrigDefinition"):
        raise ValueError("Choose a rig root with a limb definition or a skinCluster.")
    from mlrig.definition import RigDefinition

    definition = RigDefinition.from_data(json.loads(cmds.getAttr(node + ".mlrigDefinition")))
    return "Rig definition", [f"Schema: {definition.schema_version}", "Joints: " + ", ".join(j.id for j in definition.joint_order()),
                              "Layers: " + ", ".join(layer.id for layer in definition.layers),
                              "Rebuilding requires a builder supporting these joints and layers."]


def export(node, filename):
    """選択ノードを検証し、対応するリグ定義またはスキン形式で書き出す。"""
    kind, _ = describe(node)
    if kind == "Skin weights":
        import mlib

        return mlib.getNode(node).exportWeights(filename)
    data = json.loads(cmds.getAttr(node + ".mlrigDefinition"))
    path = Path(filename)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run():
    """型ごとの依存を表示し、選択したJSONファイルへ保存する。"""
    window = "HToolsTypedRigExport"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect and Export Rig Data")
    cmds.columnLayout(adjustableColumn=True)
    report = cmds.scrollField(editable=False, height=160)

    def inspect(save):
        nodes = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        if len(nodes) != 1:
            raise ValueError("Select one rig root or skinCluster.")
        kind, rows = describe(nodes[0])
        cmds.scrollField(report, edit=True, text="\n".join([kind] + rows))
        if save:
            names = cmds.fileDialog2(fileMode=0, fileFilter="JSON (*.json)", caption="Export " + kind)
            if names:
                export(nodes[0], names[0])

    cmds.button(label="Inspect selected asset", command=lambda *_: inspect(False))
    cmds.button(label="Export selected asset", command=lambda *_: inspect(True))
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
