# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノード作成・改名・削除の内部実装。

作成・改名はUndoへ登録しないOpenMaya実装。削除は通常(cmds)・fast(OpenMaya)の両方で使う
事前検査と、1回にまとめた削除を提供する。
"""

import itertools
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from typing import Iterator, Sequence
from mlib.nodes.node import Node


def _dag_descendants(mobject: om2.MObject) -> Iterator[om2.MObject]:
    """DAGノードの全子孫を深さ優先で列挙する。DGノードは何も返さない。

    Args:
        mobject (om2.MObject): 起点のノード。自身は含めない。

    Yields:
        om2.MObject: 子、その子孫の順(各親の子は末尾から辿る)。
    """
    ...

def require_editable(node: om2.MObject, descendants: bool = ...) -> None:
    """構造変更前に参照・ロックされたノードを拒否する。

    Args:
        node (MObject): 対象ノード。
        descendants (bool): DAG子孫も検査するか。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: 無効なノード、またはロック・参照されたノードが対象か子孫に含まれる場合。
    """
    ...

def check_deletion(nodes: Sequence[Node], fast: bool = ...) -> list[tuple[om2.MObject, str]]:
    """削除の前に全対象を検査し、削除できない対象があれば何も削除せずに拒否する。

    対象と DAG 子孫のロック・参照、Maya が削除を拒否するノード(``cmds.ls(undeletable=True)`` が
    返す既定・共有ノード等。time1・persp・defaultLayer など)を調べる。通常の ``cmds.delete`` は
    一括で渡すとこれらをエラー表示だけで飛ばして他を削除し続け、OpenMaya の削除は既定・共有
    ノードで Maya が異常終了するため、更新の前に例外にする。

    Args:
        nodes (Sequence[Node]): 呼出し順の削除対象。
        fast (bool): 例外の文言を fast(OpenMaya)経路の従来の文言にするか。

    Returns:
        list[tuple[om2.MObject, str]]: 対象順の (MObject, 完全パスまたは名前)。

    Raises:
        RuntimeError: 無効な対象、またはロック・参照・削除できないノードが対象か DAG 子孫に
            含まれる場合。属性 ``index`` に原因の対象の番号を持つ。
    """
    ...

def delete_nodes(nodes: Sequence[Node], fast: bool = ..., checked: list | None = ...) -> None:
    """検査を済ませた上で、全対象を1回の削除にまとめる。

    通常は1回の ``cmds.delete`` に完全パスを渡し、fast は1つの MDagModifier へ全対象を積んで
    doIt を1回呼ぶ(DG ノードも同じ modifier で扱う)。削除の順・連鎖して消えるノードは
    Maya がまとめて削除するときの規則に従う。重複・親子の両方の指定は通常は ``cmds.delete`` が
    まとめ、fast は先行する削除で既に消えた対象(親と一緒に消えた子・連鎖して消えたノード・
    同じノードの重複)を積まない。

    Args:
        nodes (Sequence[Node]): 呼出し順の削除対象。1つ以上。
        fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
        checked (list | None): 同じ nodes に対する :func:`check_deletion` の戻り値。
            Noneならここで検査する。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: :func:`check_deletion` が拒否した場合。何も削除しない。
    """
    ...

def _referenced_message(path: str, owner: str | None = ...) -> str:
    """参照ファイルから読み込んだノードを削除しようとしたときの文言を作る。

    Args:
        path (str): 参照されたノードの完全パスまたは名前。
        owner (str | None): 削除しようとした対象(pathがその子孫の場合)。

    Returns:
        str: 参照ノード(``RN`` ノード)とファイルを示す文言。
    """
    ...

def _deletion_error(index: int, message: str) -> RuntimeError:
    """対象の番号を持つ削除の RuntimeError を作る。

    Args:
        index (int): 原因の対象の番号。
        message (str): 例外の文言。

    Returns:
        RuntimeError: ``index`` 属性を持つ例外。
    """
    ...

def _display_name(path: str) -> str:
    """例外の文言に使う、Maya の表示と同じ最短の一意な名前を返す。

    Args:
        path (str): 完全パスまたは名前。

    Returns:
        str: DAG は partialPathName、DG はノード名。
    """
    ...

def rename_node(node: om2.MObject, name: str, ignore_shape: bool = ...) -> str:
    """ノードと、旧名の接頭辞が一致する直属Shapeを改名する。

    Args:
        node (MObject): 改名対象。
        name (str): Mayaが補正する新しい名前。
        ignore_shape (bool): 直属Shapeの連動改名を行わないか。

    Returns:
        str: Mayaが確定したノード名。
    """
    ...

def create_node(node_type: str, flags: dict) -> om2.MObject:
    """Mayaの代表的なcreateNodeフラグをOpenMayaで実行する。

    Args:
        node_type (str): 作成するnodeType。
        flags (dict): 正規化済みname/parent/skipSelect/shared。

    Returns:
        MObject: 作成したノード。Shapeの暗黙の親ではなくShapeを返す。
            shared=Trueで同名・同型のノードが一意に存在する場合はそのノード(cmdsはルート名前空間の
            名前だけ再利用するが、ここでは名前空間付きの名前でも既存ノードを返す近似)。

    Raises:
        RuntimeError: Mayaが認識しないnodeType、ロック・参照された親、またはshared=Trueで
            同名ノードの型が違う場合(cmdsは新しい連番名で作るが、fastは型を見て拒否する)。
        NotImplementedError: name/parent/skipSelect/shared以外のフラグを指定した場合。
    """
    ...
