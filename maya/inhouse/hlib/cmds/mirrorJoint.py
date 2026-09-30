"""Maya標準のジョイント階層ミラーを型付きの結果で返す。"""
import maya.cmds as cmds
from .._core.coerce import to_node
from .._core.flags import flag_aliases
from ..decorators.undo import undo_chunk


@flag_aliases("mirrorJoint")
@undo_chunk("hlibMirrorJoint")
def mirrorJoint(joint, **kwargs):
    """指定Joint以下の階層をMaya標準の規約でミラー複製する。

    Args:
        joint (Joint | str): 元になるルートJoint。選択には依存しない。
        **kwargs (object): mirrorYZ(myz)、mirrorXY(mxy)、mirrorXZ(mxz)、
            mirrorBehavior(mb)、searchReplace(sr)等のMaya標準フラグ。

    Returns:
        Joint | Joints: 作成結果のうちJointのみ。1件ならJoint、複数ならJoints。
            並びはMayaの返却順。元のJointは含めない。

    Raises:
        TypeError: 対象がJointでない、または長短フラグを重複指定した場合。
        RuntimeError: Mayaが複製を拒否した場合。

    オプションの既定値もMayaに従う。全作成を一回のUndoで戻せる。
    """
    from ..nodes.joint import Joint, Joints
    source = to_node(joint)
    if not isinstance(source, Joint):
        raise TypeError("mirrorJoint requires a Joint")
    names = cmds.mirrorJoint(source.full_name(), **kwargs) or []
    result = [Joint(name) for name in names if cmds.nodeType(name) == "joint"]
    return result[0] if len(result) == 1 else Joints(result)
