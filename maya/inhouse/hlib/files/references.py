"""シーン内の参照(reference)の列挙・作成を提供する。"""

from pathlib import Path

import maya.cmds as cmds

from ..decorators.undo import undo_chunk

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
    # nodes.reference が ..namespaces を逆方向 import しないが、
    # hlib 内の他の相互依存箇所と合わせて遅延 import で統一する。
    from ..nodes.reference import Reference

    names = [name for name in (cmds.ls(type="reference") or []) if name != _SHARED_REFERENCE_NODE]
    references = [Reference(name) for name in names]
    if top_level_only:
        references = [reference for reference in references if reference.parent_reference() is None]
    return references


@undo_chunk("hlibCreateReference")
def create_reference(path, namespace=None):
    """新しい Reference を作成する。

    Args:
        path (str | Path): 参照するファイルのパス。
        namespace (str | None): 参照内容に付ける名前空間。省略時はMayaの既定
            (ファイル名ベース)を使う。

    Returns:
        Reference: 作成された参照ノードのラッパー。

    Raises:
        ValueError: path が空文字列または str/Path 以外の場合。
        RuntimeError: Maya が参照の作成に失敗した、または作成された参照ノードを
            一意に特定できない場合。
    """
    from ..nodes.reference import Reference

    if not isinstance(path, (str, Path)) or not str(path):
        raise ValueError("path must be a non-empty string or Path")
    scene_path = Path(path).expanduser()

    existing = set(cmds.ls(type="reference") or [])
    kwargs = {"reference": True}
    if namespace is not None:
        kwargs["namespace"] = namespace
    cmds.file(str(scene_path), **kwargs)

    created = [Reference(name) for name in (cmds.ls(type="reference") or []) if name not in existing]
    # 参照先ファイル自身がネストした参照を持つ場合、その子参照ノードも同時に
    # 新規ノードとして現れるため、親を持たないトップレベルのものだけを選ぶ。
    top_level = [reference for reference in created if reference.parent_reference() is None]
    if len(top_level) != 1:
        names = [reference.name() for reference in created]
        raise RuntimeError(f"Failed to identify the newly created reference node: {names}")
    return top_level[0]
