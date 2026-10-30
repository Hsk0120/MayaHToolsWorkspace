# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノードまたはコンポーネントを削除する。戻り値はNone。

Plug・MPlugは受け付けない。アトリビュートの削除は ``plug.delete()``、
マルチアトリビュートの要素の削除は ``multi_plug.removeElement(index)`` を使う。
通常はMayaのUndoに対応する。``fast=True`` はノードの直接削除に限り、
コンポーネントを含む入力は何も削除せず拒否する。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    mlib.delete(node)
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import _selection_plug
from ..decorator import _edit_context
from typing import Iterable
from mlib.common.selection import Selection
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.nodes.node import Node


def delete(nodes: Node | Component | Components | Selection | str | om2.MObject | om2.MDagPath | Iterable, *, fast: bool = ...) -> None:
    """指定したノード・コンポーネントを削除する。

    ノードは全対象を1回の削除にまとめる。通常は1回の ``cmds.delete`` (1回のUndoで全て戻る)、
    fastは1つの MDagModifier の doIt 1回で削除する。削除の順(削除通知の順)と連鎖して消える
    ノード(unitConversion・構築履歴など)は、Mayaがまとめて削除するときの規則に従う
    (DGとDAGが混ざると渡した順にならない場合がある)。

    削除の前に全対象とDAG子孫を検査し、ロックされたノード・参照のノード・Mayaが削除を拒否する
    ノード(既定・共有ノード等。time1・persp・defaultLayer など)が一つでも含まれる場合は、
    コンポーネントを含めて何も削除せずRuntimeErrorにする。

    Args:
        nodes (Node | Component | Components | Selection | str | om2.MObject | om2.MDagPath | Iterable):
            削除する対象、またはその列(入れ子のコレクションも展開する)。
            同じノードの重複、親と子の両方の指定はまとめて1回だけ削除する(親と一緒に消える)。
            ワイルドカードは一致したノードへ展開する。
        fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: 要素が対応しない型の場合、またはfastがbool以外の場合。要素に Plug(MultiPlug を含む)・
            om2.MPlug、またはアトリビュートに解決される文字列(``"node.tx"`` 等)が含まれる場合
            (maya.cmds.delete はアトリビュートを削除せずエラーを表示するだけのため。何も削除しない)。
        ValueError: nodes が空、または要素が空文字列・削除済みの対象の場合(何も削除しない)。
        RuntimeError: 存在しない名前を含む場合(``getNode`` と同じ文言。何も削除しない)。
            ロック・参照・削除できないノードを含む場合(何も削除しない。文言は
            cmds.delete の要素ごとの表示に合わせ、例えば ``Cannot delete locked node 'x'.``、
            ``Cannot delete 'x' as it has locked or read-only children.``、
            ``Non-deletable node 'x' cannot be deleted.``。fastのロック・参照は
            ``Node is locked or referenced: x``)、または Maya が削除を拒否した場合。
        NotImplementedError: fast=Trueでコンポーネントを含む入力を指定した場合(何も削除しない)。

    Note:
        fastはノードの直接削除に限る。コンポーネントのトポロジー削除には
        対応せず、入力に含まれる場合は何も削除せずNotImplementedErrorにする。
        専用のdeleteを上書きした派生クラスのノードを含む場合だけ、従来どおり各ノードの
        deleteを順に呼ぶ(親の削除で既に消えた対象は飛ばす)。
        コンポーネントは、ノードの検査の後、ノードより先に別の1回の ``cmds.delete`` で削除する。
    """
    ...

def _resolves_to_plug(name: str) -> bool:
    """文字列がアトリビュート(プラグ)を指すか判定する。

    Mayaが解決できない名前・コンポーネント名は False にし、従来どおり ``cmds.delete`` の扱いに任せる。

    Args:
        name (str): ``"."`` を含む対象名。

    Returns:
        bool: 一致した要素のいずれかがプラグの場合は True。
    """
    ...
