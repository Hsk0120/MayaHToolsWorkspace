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


def delete(nodes, *, fast=False):
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
    with _edit_context("mlibDelete", fast):
        from ..core.nodeEdit import check_deletion, delete_nodes
        from ..core.object import Object as _InputObject
        from ..nodes.node import Node

        names = _InputObject._input_names(nodes, allow_plugs=False)
        if not names:
            raise ValueError("nodes must contain at least one node")
        # アトリビュート・コンポーネント文字列は所有ノードへ変換せず、標準の扱いを維持する。
        node_names = [name for name in names if "." not in name]
        components = [name for name in names if "." in name]
        for name in components:
            # "node.tx" のようなアトリビュート名の文字列も、Plugと同じく削除の前に拒否する。
            if _resolves_to_plug(name):
                raise TypeError(
                    f"Attribute names are not accepted: {name} "
                    "(specify the node name to delete the owning node)")
        if components and fast:
            raise NotImplementedError("fast component/topology deletion is not supported")
        nodes = []
        for name in node_names:
            # Maya標準のワイルドカード指定を実ノードへ展開してから検証する。
            if any(char in name for char in "*?["):
                resolved = (list(om2.MGlobal.getSelectionListByName(name).getSelectionStrings())
                            if fast else cmds.ls(name, long=True))
            else:
                resolved = [name]
            # 名前は Node(value) と同じ解決・型選択を、生成の入口の再判定なしで行う。
            nodes.extend(Node._from_name(value) for value in (resolved or [name]))
        batch = all(type(node).delete is Node.delete for node in nodes)
        checked = None
        if nodes and (batch or fast):
            # コンポーネントを削除する前に検査し、拒否する場合は何も削除しない。
            checked = check_deletion(nodes, fast=fast)
        if components:
            cmds.delete(*components)
            # コンポーネントの削除で消えたノードは従来どおり飛ばし、残りを検査し直す。
            nodes = [node for node in nodes if node.isValid()]
            checked = None
        if not nodes:
            return
        if batch:
            delete_nodes(nodes, fast=fast, checked=checked)
            return
        for node in nodes:
            # 親・所有コンテナの削除や重複指定で既に消えた対象は再削除しない。
            if node.isValid():
                node.delete(fast=fast)


def _resolves_to_plug(name):
    """文字列がアトリビュート(プラグ)を指すか判定する。

    Mayaが解決できない名前・コンポーネント名は False にし、従来どおり ``cmds.delete`` の扱いに任せる。

    Args:
        name (str): ``"."`` を含む対象名。

    Returns:
        bool: 一致した要素のいずれかがプラグの場合は True。
    """
    selection = om2.MSelectionList()
    try:
        selection.add(name)
    except RuntimeError:
        return False
    return any(_selection_plug(selection, index) is not None for index in range(selection.length()))
