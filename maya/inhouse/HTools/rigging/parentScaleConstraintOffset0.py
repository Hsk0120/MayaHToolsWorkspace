# Maya Python / maya.cmds
"""選択2ノードに parent/scaleConstraint を offset 0 で作成するツール。"""

import maya.cmds as cmds

def parent_scale_constraint_offset0():
    """選択順(親→子)で parentConstraint/scaleConstraint を作成します。"""
    sel = cmds.ls(sl=True)

    if len(sel) != 2:
        cmds.warning(u"2ノード選択してください。選択順: 親 → 子")
        return

    parent = sel[0]
    child = sel[1]

    # maintainOffset=False で現在差分を作らずに拘束する。
    cmds.parentConstraint(parent, child, mo=False)
    cmds.scaleConstraint(parent, child, mo=False)

    print(u"parentConstraint / scaleConstraint を offset 0 で作成しました: {} <- {}".format(child, parent))

if __name__ == "__main__":
    parent_scale_constraint_offset0()