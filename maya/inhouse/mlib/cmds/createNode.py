"""Mayaノードを作成し、実際のノード型に対応するラッパーを返す。

mlibでノードを作成する唯一の入口。``cmds.createNode`` に相当し、``Node.create`` や
``Node(name, create=True)`` のような作成経路は無い。戻り値は作成したノードの実際のnodeTypeに
対応するラッパー(登録済みクラス、未登録型は登録表の規則で選ぶクラス)で、``getType()`` は
MayaのnodeType名を返す。

通常はMayaのUndoに対応し、1回のUndoで作成(shapeの自動生成transformを含む)を戻せる。
``fast=True`` は対応する作成条件をOpenMayaで直接処理し、Undo履歴を追加しない。
未対応の条件はノードを作る前に拒否する。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    child = mlib.createNode("joint", n="child", p=node, ss=True)
"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET


def createNode(type, *, fast=False,
        name=_UNSET, n=_UNSET,
        parent=_UNSET, p=_UNSET,
        shared=_UNSET, s=_UNSET,
        skipSelect=_UNSET, ss=_UNSET,
        **kwargs):
    """Mayaノードを作成し、実際の型に対応するラッパーを返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。
    ``cmds.createNode`` に無い ``query``/``edit`` は受け付けない(他のフラグと同様にMayaがTypeErrorにする)。

    親を省略したshape型はshapeを返し、``getParent()`` がMayaの自動生成したtransformになる。
    ``shared=True`` で同名・同型のノードが既にある場合は作成せずそのノードを返す(cmds.createNodeが
    作成せずNoneを返す場合。cmdsはルート名前空間の名前だけ再利用し、名前空間付きの名前は連番名で作る)。
    fast=Trueは名前で既存の同型ノードを探す近似で、名前空間付きでも既存ノードを返し、同名ノードの型が
    違う場合は新しい連番名で作らず RuntimeError にする。

    Args:
        type (str): Mayaノード型名。
        fast (bool): TrueはOpenMaya直接更新でUndoなし。既定Falseは通常処理。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parent (object): 親ノード。Node・Plug・Component・API参照は所有ノードの完全パスへ変換する。
        p (object): parentの短縮名。同時指定はできない。
        shared (bool): 同名の共有ノードがある場合のMaya標準の共有指定。
        s (bool): sharedの短縮名。同時指定はできない。
        skipSelect (bool): 作成したノードを選択しない指定。
        ss (bool): skipSelectの短縮名。同時指定はできない。
        **kwargs (object): 通常処理では追加のMayaフラグをそのまま渡す。
            fast=Trueでは対応しないフラグを作成前に拒否する。

    Returns:
        Node: 作成したノードの実際のnodeTypeに対応するラッパー。

    Raises:
        TypeError: 長名・短名の同時指定、fastがbool以外、parentが対応しない型、
            またはcmds.createNodeに無いフラグ(query/edit等)を指定した場合。
        ValueError: typeが空文字列・文字列以外、parent が空文字列、または削除済みの対象の場合。
        RuntimeError: Mayaが認識しないノード型名の場合(unknownノードを残さない。版の互換名は作成できる)、
            parent を解決できない場合、fast=Trueでロック・参照された親を指定した場合、
            またはMayaが作成を拒否した場合。
        NotImplementedError: fast=Trueで未対応のフラグを指定した場合。
    """
    if name is not _UNSET:
        if n is not _UNSET:
            raise _ArgumentError("Specify only one of 'name' and 'n'")
        kwargs["name"] = name
    elif n is not _UNSET:
        kwargs["name"] = n
    if parent is not _UNSET:
        if p is not _UNSET:
            raise _ArgumentError("Specify only one of 'parent' and 'p'")
        kwargs["parent"] = parent
    elif p is not _UNSET:
        kwargs["parent"] = p
    if shared is not _UNSET:
        if s is not _UNSET:
            raise _ArgumentError("Specify only one of 'shared' and 's'")
        kwargs["shared"] = shared
    elif s is not _UNSET:
        kwargs["shared"] = s
    if skipSelect is not _UNSET:
        if ss is not _UNSET:
            raise _ArgumentError("Specify only one of 'skipSelect' and 'ss'")
        kwargs["skipSelect"] = skipSelect
    elif ss is not _UNSET:
        kwargs["skipSelect"] = ss
    if not isinstance(fast, bool):
        raise TypeError("fast must be a bool")
    with nullcontext() if fast else undoChunk("mlib.cmds.createNode.createNode"):
        # 作成の実体はNodeの内部ヘルパー。nodesはcmdsを参照するため循環importを避けて関数内で読み込む。
        from ..nodes import Node

        return Node._create_node(type, kwargs, fast=fast)
