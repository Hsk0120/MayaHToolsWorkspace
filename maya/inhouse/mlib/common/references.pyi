# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""シーン内の参照(reference)の列挙・作成を提供する。"""

from pathlib import Path
from typing import Any, Dict
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import undoChunk
from mlib.nodes.reference import Reference

_SHARED_REFERENCE_NODE: str

def _reference_nodes() -> list[tuple[str, om2.MObject]]:
    """共有参照ノードを除く参照ノードを、``cmds.ls(type="reference")`` と同じ名前順で列挙する。

    Returns:
        list[tuple[str, om2.MObject]]: ``(ノード名, MObject)`` の名前順(文字コード順)の list。
    """
    ...

def listReferences(topLevelOnly: bool = ...) -> list[Reference]:
    """シーン内の参照を Reference ラッパーの一覧として取得する。

    Args:
        topLevelOnly (bool): True の場合、他の参照にネストされていない
            トップレベルの参照だけを返す。

    Returns:
        list[Reference]: 参照ラッパーの一覧(``cmds.ls(type="reference")`` と同じ名前順)。
            参照が無ければ空リスト。名前順のため、参照を作成・読み込んだ順とは限らない。
    """
    ...

def createReference(path: str | Path, namespace: str | None = ...) -> Reference:
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

    Note:
        fast引数は持たない。参照の読込み(ファイルの読込み・参照ノードと名前空間の作成)は
        ``cmds.file(reference=True)`` だけが行え、OpenMayaに同等のUndoなし経路が無いため。
    """
    ...
