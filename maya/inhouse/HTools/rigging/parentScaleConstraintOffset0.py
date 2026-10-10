# Maya Python / maya.cmds
"""選択2ノードに parent/scaleConstraint を offset 0 で作成するツール。"""

import maya.cmds as cmds


def parent_scale_constraint_offset0():
    """選択順(親→子)で parentConstraint/scaleConstraint を作成します。"""
    sel = cmds.ls(sl=True)

    if len(sel) != 2:
        cmds.warning(u"Select two nodes in order: parent, then child.")
        return

    parent = sel[0]
    child = sel[1]

    # Transform 以外を渡すと Maya は追従しない拘束を作るため、作成前に拒否する。
    for node in (parent, child):
        if not cmds.objectType(node, isAType='transform'):
            cmds.warning(u"Select transform nodes (joints included): {}".format(node))
            return

    # maintainOffset=False で現在差分を作らずに拘束する。2つの拘束は1回のUndoで戻せる。
    cmds.undoInfo(openChunk=True, chunkName='parentScaleConstraintOffset0')
    try:
        cmds.parentConstraint(parent, child, maintainOffset=False)
        cmds.scaleConstraint(parent, child, maintainOffset=False)
    finally:
        cmds.undoInfo(closeChunk=True)

    print(u"Created parentConstraint / scaleConstraint with offset 0: {} <- {}".format(child, parent))

if __name__ == "__main__":
    parent_scale_constraint_offset0()