"""シーン内の参照(reference)を列挙する。"""

import maya.cmds as cmds

# Maya が常に作成する共有参照ノード。ユーザーが作成した参照ではないため一覧から除外する。
_SHARED_REFERENCE_NODE = "sharedReferenceNode"


def list_references(top_level_only=False):
    """シーン内の参照を Reference ラッパーの一覧として取得する。

    Args:
        top_level_only (bool): True の場合、他の参照にネストされていない
            トップレベルの参照だけを返す。

    Returns:
        list[Reference]: 参照ラッパーの一覧。参照が無ければ空リスト。
    """
    # nodes.reference が ..scenes を逆方向 import しないが、
    # hlib 内の他の相互依存箇所と合わせて遅延 import で統一する。
    from ..nodes.reference import Reference

    names = [name for name in (cmds.ls(type="reference") or []) if name != _SHARED_REFERENCE_NODE]
    references = [Reference(name) for name in names]
    if top_level_only:
        references = [reference for reference in references if reference.parent_reference() is None]
    return references
