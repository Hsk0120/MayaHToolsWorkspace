"""ノード・アトリビュート・コンポーネントの選択状態を変更する。戻り値はNone。

mlibの参照やコレクションを名前へ変換し、``maya.cmds.select`` へ渡す。
対象を省略するとフラグだけで呼び出し、空の列は空の列として渡す。
MayaのUndoに対応する。

.. code-block:: python

    import mlib

    mlib.select(mlib.ls(type="joint"))
    mlib.select(clear=True)
"""

import maya.cmds as cmds

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET


def select(nodes=None, *,
        add=_UNSET,
        addFirst=_UNSET, af=_UNSET,
        all=_UNSET,
        allDagObjects=_UNSET, ado=_UNSET,
        allDependencyNodes=_UNSET, adn=_UNSET,
        clear=_UNSET, cl=_UNSET,
        containerCentric=_UNSET, cc=_UNSET,
        deselect=_UNSET, d=_UNSET,
        hierarchy=_UNSET, hi=_UNSET,
        noExpand=_UNSET, ne=_UNSET,
        replace=_UNSET, r=_UNSET,
        symmetry=_UNSET, sym=_UNSET,
        symmetrySide=_UNSET, sys=_UNSET,
        toggle=_UNSET, tgl=_UNSET,
        visible=_UNSET, vis=_UNSET,
        query=_UNSET, q=_UNSET,
        edit=_UNSET, e=_UNSET,
        **kwargs):
    """指定したノード・アトリビュート・コンポーネントを選択する。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    Args:
        nodes (object): 選択する対象またはその列。NoneはフラグだけでMayaを呼び、空列は空列として渡す。
        add (bool): 既存の選択に追加する指定。
        addFirst (bool): 既存の選択の先頭へ追加する指定。
        af (bool): addFirstの短縮名。同時指定はできない。
        all (bool): 削除可能な全ノードを選択するMayaフラグ。
        allDagObjects (bool): 全DAG対象を選択する指定。
        ado (bool): allDagObjectsの短縮名。同時指定はできない。
        allDependencyNodes (bool): 全依存ノードを選択する指定。
        adn (bool): allDependencyNodesの短縮名。同時指定はできない。
        clear (bool): 選択を解除する指定。
        cl (bool): clearの短縮名。同時指定はできない。
        containerCentric (bool): コンテナ中心の選択規則を使う指定。
        cc (bool): containerCentricの短縮名。同時指定はできない。
        deselect (bool): 指定対象を選択から外す指定。
        d (bool): deselectの短縮名。同時指定はできない。
        hierarchy (bool): 子階層も選択する指定。
        hi (bool): hierarchyの短縮名。同時指定はできない。
        noExpand (bool): セットのメンバーへ展開しない指定。
        ne (bool): noExpandの短縮名。同時指定はできない。
        replace (bool): 既存の選択を置き換える指定。省略時のMaya既定動作は変更しない。
        r (bool): replaceの短縮名。同時指定はできない。
        symmetry (bool): 対称選択を使うMayaフラグ。
        sym (bool): symmetryの短縮名。同時指定はできない。
        symmetrySide (int): 対称選択に使う側の指定。
        sys (int): symmetrySideの短縮名。同時指定はできない。
        toggle (bool): 指定対象の選択状態を切り替える指定。
        tgl (bool): toggleの短縮名。同時指定はできない。
        visible (bool): 表示中の対象だけを選択する指定。
        vis (bool): visibleの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        **kwargs (object): 今後追加される未知のMayaフラグ。そのままMayaへ渡す。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: 長名・短名を同時指定した場合、またはnodesの要素が対応しない型の場合。
        ValueError: nodes の要素に空文字列、または削除済みの対象が含まれる場合。
        RuntimeError: Maya が選択を拒否した場合。
    """
    if add is not _UNSET:
        kwargs["add"] = add
    if addFirst is not _UNSET:
        if af is not _UNSET:
            raise _ArgumentError("Specify only one of 'addFirst' and 'af'")
        kwargs["addFirst"] = addFirst
    elif af is not _UNSET:
        kwargs["addFirst"] = af
    if all is not _UNSET:
        kwargs["all"] = all
    if allDagObjects is not _UNSET:
        if ado is not _UNSET:
            raise _ArgumentError("Specify only one of 'allDagObjects' and 'ado'")
        kwargs["allDagObjects"] = allDagObjects
    elif ado is not _UNSET:
        kwargs["allDagObjects"] = ado
    if allDependencyNodes is not _UNSET:
        if adn is not _UNSET:
            raise _ArgumentError("Specify only one of 'allDependencyNodes' and 'adn'")
        kwargs["allDependencyNodes"] = allDependencyNodes
    elif adn is not _UNSET:
        kwargs["allDependencyNodes"] = adn
    if clear is not _UNSET:
        if cl is not _UNSET:
            raise _ArgumentError("Specify only one of 'clear' and 'cl'")
        kwargs["clear"] = clear
    elif cl is not _UNSET:
        kwargs["clear"] = cl
    if containerCentric is not _UNSET:
        if cc is not _UNSET:
            raise _ArgumentError("Specify only one of 'containerCentric' and 'cc'")
        kwargs["containerCentric"] = containerCentric
    elif cc is not _UNSET:
        kwargs["containerCentric"] = cc
    if deselect is not _UNSET:
        if d is not _UNSET:
            raise _ArgumentError("Specify only one of 'deselect' and 'd'")
        kwargs["deselect"] = deselect
    elif d is not _UNSET:
        kwargs["deselect"] = d
    if hierarchy is not _UNSET:
        if hi is not _UNSET:
            raise _ArgumentError("Specify only one of 'hierarchy' and 'hi'")
        kwargs["hierarchy"] = hierarchy
    elif hi is not _UNSET:
        kwargs["hierarchy"] = hi
    if noExpand is not _UNSET:
        if ne is not _UNSET:
            raise _ArgumentError("Specify only one of 'noExpand' and 'ne'")
        kwargs["noExpand"] = noExpand
    elif ne is not _UNSET:
        kwargs["noExpand"] = ne
    if replace is not _UNSET:
        if r is not _UNSET:
            raise _ArgumentError("Specify only one of 'replace' and 'r'")
        kwargs["replace"] = replace
    elif r is not _UNSET:
        kwargs["replace"] = r
    if symmetry is not _UNSET:
        if sym is not _UNSET:
            raise _ArgumentError("Specify only one of 'symmetry' and 'sym'")
        kwargs["symmetry"] = symmetry
    elif sym is not _UNSET:
        kwargs["symmetry"] = sym
    if symmetrySide is not _UNSET:
        if sys is not _UNSET:
            raise _ArgumentError("Specify only one of 'symmetrySide' and 'sys'")
        kwargs["symmetrySide"] = symmetrySide
    elif sys is not _UNSET:
        kwargs["symmetrySide"] = sys
    if toggle is not _UNSET:
        if tgl is not _UNSET:
            raise _ArgumentError("Specify only one of 'toggle' and 'tgl'")
        kwargs["toggle"] = toggle
    elif tgl is not _UNSET:
        kwargs["toggle"] = tgl
    if visible is not _UNSET:
        if vis is not _UNSET:
            raise _ArgumentError("Specify only one of 'visible' and 'vis'")
        kwargs["visible"] = visible
    elif vis is not _UNSET:
        kwargs["visible"] = vis
    if query is not _UNSET:
        if q is not _UNSET:
            raise _ArgumentError("Specify only one of 'query' and 'q'")
        kwargs["query"] = query
    elif q is not _UNSET:
        kwargs["query"] = q
    if edit is not _UNSET:
        if e is not _UNSET:
            raise _ArgumentError("Specify only one of 'edit' and 'e'")
        kwargs["edit"] = edit
    elif e is not _UNSET:
        kwargs["edit"] = e
    with undoChunk("mlib.cmds.select.select"):
        from ..core.object import Object as _InputObject

        if nodes is None:
            cmds.select(**kwargs)
            return
        names = _InputObject._input_names(nodes)
        cmds.select(names, **kwargs)
