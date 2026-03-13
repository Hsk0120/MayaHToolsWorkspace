# Maya Python / maya.cmds
import maya.cmds as cmds

def parent_scale_constraint_offset0():
    sel = cmds.ls(sl=True)

    if len(sel) != 2:
        cmds.warning(u"2ノード選択してください。選択順: 親 → 子")
        return

    parent = sel[0]
    child = sel[1]

    # offset 0 で拘束
    cmds.parentConstraint(parent, child, mo=False)
    cmds.scaleConstraint(parent, child, mo=False)

    print(u"parentConstraint / scaleConstraint を offset 0 で作成しました: {} <- {}".format(child, parent))

if __name__ == "__main__":
    parent_scale_constraint_offset0()