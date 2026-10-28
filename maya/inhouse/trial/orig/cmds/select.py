"""ノード・アトリビュート・コンポーネントの選択状態を変更する。戻り値はNone。

mlibの参照やコレクションを名前へ変換し、``maya.cmds.select`` へ渡す。
対象を省略するとフラグだけで呼び出し、空の列は空の列として渡す。
MayaのUndoに対応する。``fast=True`` は ``MGlobal.setActiveSelectionList`` で反映し、Undoに記録しない。

.. code-block:: python

    import mlib

    mlib.select(mlib.ls(type="joint"))
    mlib.select(clear=True)
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _edit_context, _merge_flags
from ..util import _UNSET


#: fastで扱えるフラグ。選択方法のフラグは同時に1つだけ指定できる。
_FAST_FLAGS = ("add", "addFirst", "clear", "deselect", "noExpand", "replace")
_FAST_MODES = {
    "add": om2.MGlobal.kAddToList,
    "addFirst": om2.MGlobal.kAddToHeadOfList,
    "deselect": om2.MGlobal.kRemoveFromList,
    "replace": om2.MGlobal.kReplaceList,
}


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
        fast=False,
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
        fast (bool): TrueはUndoなしのOpenMaya直接更新。既定False。対象の並びと、直前の要素と同じ形状・
            種類のコンポーネントをまとめる規則は ``cmds.select`` と同じ。使えるフラグは
            add・addFirst・clear(対象なし)・deselect・noExpand・replace だけで、
            他のフラグ(Falseを除く)や未知のフラグはNotImplementedError。
        **kwargs (object): 今後追加される未知のMayaフラグ。そのままMayaへ渡す。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: 長名・短名を同時指定した場合、nodesの要素が対応しない型の場合、またはfastがbool以外の場合。
        ValueError: nodes の要素に空文字列、または削除済みの対象が含まれる場合。fastで名前が見つからない場合。
        RuntimeError: Maya が選択を拒否した場合。
        NotImplementedError: fastで、未対応のフラグ(hierarchy・allDagObjects・toggle等)、複数の選択方法、
            対象を伴うclear、対象なしのclear以外のフラグ、またはnoExpandなしでセットを指定した場合。
            選択を変更する前に送出する。
    """
    _merge_flags(kwargs, (
        (addFirst, af, "addFirst", "af"),
        (allDagObjects, ado, "allDagObjects", "ado"),
        (allDependencyNodes, adn, "allDependencyNodes", "adn"),
        (clear, cl, "clear", "cl"),
        (containerCentric, cc, "containerCentric", "cc"),
        (deselect, d, "deselect", "d"),
        (hierarchy, hi, "hierarchy", "hi"),
        (noExpand, ne, "noExpand", "ne"),
        (replace, r, "replace", "r"),
        (symmetry, sym, "symmetry", "sym"),
        (symmetrySide, sys, "symmetrySide", "sys"),
        (toggle, tgl, "toggle", "tgl"),
        (visible, vis, "visible", "vis"),
        (query, q, "query", "q"),
        (edit, e, "edit", "e"),
        (add, _UNSET, "add", None),
        (all, _UNSET, "all", None),
    ))
    with _edit_context("mlibSelect", fast):
        from ..core.object import Object as _InputObject

        if fast:
            _select_fast(nodes, kwargs)
            return
        if nodes is None:
            cmds.select(**kwargs)
            return
        names = _InputObject._input_names(nodes)
        cmds.select(names, **kwargs)


def _select_fast(nodes, flags):
    """selectのfast経路。対応しない指定は選択を変える前に拒否する。

    Args:
        nodes (object): selectのnodes。
        flags (dict): 長名へそろえたMayaフラグ。

    Raises:
        NotImplementedError: fastで再現しないフラグや組合せの場合。
    """
    # common.selectionはnodes・componentsを読み込むため、cmdsパッケージの読込み時には読み込まない。
    from ..common.selection import _set_active_selection
    from ..core.object import Object as _InputObject

    unsupported = sorted(name for name, value in flags.items() if name not in _FAST_FLAGS and value is not False)
    if unsupported:
        raise NotImplementedError(f"fast select does not support flags: {', '.join(unsupported)}")
    modes = [name for name in ("add", "addFirst", "clear", "deselect", "replace") if flags.get(name)]
    if len(modes) > 1:
        raise NotImplementedError("fast select supports only one of add, addFirst, clear, deselect and replace")
    if nodes is None:
        if modes == ["clear"]:
            om2.MGlobal.setActiveSelectionList(om2.MSelectionList(), om2.MGlobal.kReplaceList)
        elif modes:
            raise NotImplementedError("fast select without nodes supports only clear")
        return
    if modes == ["clear"]:
        raise NotImplementedError("fast select does not support clear with nodes")
    names = _InputObject._input_names(nodes)
    mode = _FAST_MODES[modes[0]] if modes else om2.MGlobal.kReplaceList
    _set_active_selection(names, mode, noExpand=bool(flags.get("noExpand")))
