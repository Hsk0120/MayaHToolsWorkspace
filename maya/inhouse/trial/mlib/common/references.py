"""シーン内の参照(reference)の列挙・作成を提供する。"""

from pathlib import Path

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import undoChunk

# Maya が常に作成する共有参照ノード。ユーザーが作成した参照ではないため一覧から除外する。
_SHARED_REFERENCE_NODE = "sharedReferenceNode"


def _reference_nodes():
    """共有参照ノードを除く参照ノードを、``cmds.ls(type="reference")`` と同じ名前順で列挙する。

    Returns:
        list[tuple[str, om2.MObject]]: ``(ノード名, MObject)`` の名前順(文字コード順)の list。
    """
    iterator = om2.MItDependencyNodes(om2.MFn.kReference)
    fn = om2.MFnDependencyNode()
    nodes = []
    while not iterator.isDone():
        mobject = iterator.thisNode()
        iterator.next()
        fn.setObject(mobject)
        name = fn.name()
        if name != _SHARED_REFERENCE_NODE:
            nodes.append((name, mobject))
    # cmds.ls(type="reference") は名前の文字コード順で返すため、作成順の反復結果を並べ替える。
    nodes.sort(key=lambda item: item[0])
    return nodes


def listReferences(topLevelOnly=False):
    """シーン内の参照を Reference ラッパーの一覧として取得する。

    Args:
        topLevelOnly (bool): True の場合、他の参照にネストされていない
            トップレベルの参照だけを返す。

    Returns:
        list[Reference]: 参照ラッパーの一覧(``cmds.ls(type="reference")`` と同じ名前順)。
            参照が無ければ空リスト。
    """
    # commonの初期化時にnodesを読み込まないよう、使用時にReferenceを読み込む。
    from ..nodes.reference import Reference

    references = [Reference(mobject) for _, mobject in _reference_nodes()]
    if topLevelOnly:
        references = [reference for reference in references if reference.getParentReference() is None]
    return references


@undoChunk("mlibCreateReference")
def createReference(path, namespace=None):
    """ファイルを参照し、新しく作られたトップレベルReferenceを返す。

    参照先のネストした子参照も作成され得るが、返すのは親参照を持たない1件だけ。
    参照ノードの特定に失敗しても、作成内容を自動で戻さない。

    Args:
        path (str | Path): 参照ファイル。ユーザーホームを展開する。
        namespace (str | None): 参照内容の名前空間。NoneはMayaの既定を使う。

    Returns:
        Reference: 作成したトップレベル参照ノード。

    Raises:
        ValueError: pathが空またはstr/Path以外の場合。
        RuntimeError: Mayaが作成を拒否した、または新規トップレベル参照が1件に定まらない場合。
    """
    from ..nodes.reference import Reference

    if not isinstance(path, (str, Path)) or not str(path):
        raise ValueError("path must be a non-empty string or Path")
    scene_path = Path(path).expanduser()

    existing = {name for name, _ in _reference_nodes()}
    kwargs = {"reference": True}
    if namespace is not None:
        kwargs["namespace"] = namespace
    cmds.file(str(scene_path), **kwargs)

    created = [Reference(mobject) for name, mobject in _reference_nodes() if name not in existing]
    # 参照先ファイル自身がネストした参照を持つ場合、その子参照ノードも同時に
    # 新規ノードとして現れるため、親を持たないトップレベルのものだけを選ぶ。
    top_level = [reference for reference in created if reference.getParentReference() is None]
    if len(top_level) != 1:
        names = [reference.getName() for reference in created]
        raise RuntimeError(f"Failed to identify the newly created reference node: {names}")
    return top_level[0]


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ("create_reference", "list_references"):
    globals().pop(_obsolete_name, None)
