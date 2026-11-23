# Maya Python / mlib
"""選択2ノードに parent/scaleConstraint を offset 0 で作成するツール。"""

import maya.cmds as cmds

import mlib
from mlib.common import Selection
from mlib.decorator import undoChunk


def parent_scale_constraint_offset0():
    """選択順(親→子)で parentConstraint/scaleConstraint を作成します。"""
    sel = Selection.capture().getItems()

    if len(sel) != 2:
        cmds.warning(u"Select two nodes in order: parent, then child.")
        return

    parent = sel[0]
    child = sel[1]

    # Transform 以外を渡すと Maya は追従しない拘束を作るため、作成前に拒否する。
    for node in (parent, child):
        if not isinstance(node, mlib.Node):
            cmds.warning(u"Select transform nodes (joints included): {}".format(node))
            return
        if not node.isType('transform'):
            cmds.warning(u"Select transform nodes (joints included): {}".format(node.getName()))
            return

    # maintainOffset=False で現在差分を作らずに拘束する。2つの拘束は1回のUndoで戻せる。
    with undoChunk('parentScaleConstraintOffset0'):
        child.addConstraint(parent, type='parent', maintainOffset=False)
        child.addConstraint(parent, type='scale', maintainOffset=False)

    print(u"Created parentConstraint / scaleConstraint with offset 0: {} <- {}".format(child.getName(), parent.getName()))

if __name__ == "__main__":
    parent_scale_constraint_offset0()
