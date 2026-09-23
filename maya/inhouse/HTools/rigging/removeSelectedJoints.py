"""Menu-compatible entry point for selected joint removal."""

import hlib
from hlib.decorators import undo_chunk

hlib.reload()
from hlib import cmds as hlib_cmds

@undo_chunk("removeSelectedJoints")
def remove_selected_joint():
    """Move selected joint weights to parent influences and delete them."""
    joints = hlib_cmds.ls(sl=True, type="joint", long=True)
    joints.delete()


if __name__ == "__main__":
    remove_selected_joint()
