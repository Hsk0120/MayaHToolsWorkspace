"""名前や条件でMayaの対象を検索し、Node・Plug・単体Componentの参照へ変換する。

``type="joint"`` はJoints、``type="skinCluster"`` はSkinClustersを返し、
それ以外はリストを返す。コンポーネント範囲は単体の参照へ展開する。
型名などシーン参照以外を返すMayaフラグには対応しない。

.. code-block:: python

    import mlib

    joints = mlib.ls(type="joint")
    vertices = mlib.ls(selection=True, type="vertex")
"""

import maya.cmds as cmds

from ..decorator import _merge_flags
from ..util import _UNSET


def ls(*args,
        absoluteName=_UNSET, an=_UNSET,
        allPaths=_UNSET, ap=_UNSET,
        assemblies=_UNSET,
        cameras=_UNSET, ca=_UNSET,
        containerType=_UNSET, ct=_UNSET,
        containers=_UNSET, con=_UNSET,
        dagObjects=_UNSET, dag=_UNSET,
        defaultNodes=_UNSET, dn=_UNSET,
        dependencyNodes=_UNSET, dep=_UNSET,
        exactType=_UNSET, et=_UNSET,
        excludeType=_UNSET, ext=_UNSET,
        flatten=_UNSET, fl=_UNSET,
        geometry=_UNSET, g=_UNSET,
        ghost=_UNSET, gh=_UNSET,
        head=_UNSET, hd=_UNSET,
        hilite=_UNSET, hl=_UNSET,
        intermediateObjects=_UNSET, io=_UNSET,
        invisible=_UNSET, iv=_UNSET,
        leaf=_UNSET, lf=_UNSET,
        lights=_UNSET, lt=_UNSET,
        live=_UNSET, lv=_UNSET,
        lockedNodes=_UNSET, ln=_UNSET,
        long=_UNSET, l=_UNSET,
        materials=_UNSET, mat=_UNSET,
        modified=_UNSET, mod=_UNSET,
        noIntermediate=_UNSET, ni=_UNSET,
        nodeTypes=_UNSET, nt=_UNSET,
        objectsOnly=_UNSET, o=_UNSET,
        orderedComponentSelection=_UNSET, ocs=_UNSET,
        orderedSelection=_UNSET, os=_UNSET,
        partitions=_UNSET, pr=_UNSET,
        persistentNodes=_UNSET, pn=_UNSET,
        planes=_UNSET, pl=_UNSET,
        preSelectHilite=_UNSET, psh=_UNSET,
        readOnly=_UNSET, ro=_UNSET,
        recursive=_UNSET, r=_UNSET,
        referencedNodes=_UNSET, rn=_UNSET,
        references=_UNSET, rf=_UNSET,
        renderGlobals=_UNSET, rg=_UNSET,
        renderQualities=_UNSET, rq=_UNSET,
        renderResolutions=_UNSET, rr=_UNSET,
        renderSetups=_UNSET, rs=_UNSET,
        selection=_UNSET, sl=_UNSET,
        sets=_UNSET, set=_UNSET,
        shapes=_UNSET, s=_UNSET,
        shortNames=_UNSET, sn=_UNSET,
        showNamespace=_UNSET, sns=_UNSET,
        showType=_UNSET, st=_UNSET,
        tail=_UNSET, tl=_UNSET,
        templated=_UNSET, tm=_UNSET,
        textures=_UNSET, tex=_UNSET,
        transforms=_UNSET, tr=_UNSET,
        type=_UNSET, typ=_UNSET,
        ufeObjects=_UNSET, ufe=_UNSET,
        undeletable=_UNSET, ud=_UNSET,
        untemplated=_UNSET, ut=_UNSET,
        uuid=_UNSET, uid=_UNSET,
        visible=_UNSET, v=_UNSET,
        query=_UNSET, q=_UNSET,
        edit=_UNSET, e=_UNSET,
        **kwargs):
    """Mayaの参照を検索し、対応するラッパーとして返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    Args:
        *args (object): 名前・パターン、Node・Plug・Component・API参照またはその列。
            Noneや空の列だけを渡した場合は空の結果を返す。
        absoluteName (bool): 名前空間を絶対表記にする指定。
        an (bool): absoluteNameの短縮名。同時指定はできない。
        allPaths (bool): DAGインスタンスの全パスを列挙する指定。
        ap (bool): allPathsの短縮名。同時指定はできない。
        assemblies (bool): 最上位のTransformを検索する指定。短名asはPython予約語のため ``**{"as": value}`` で渡す。
        cameras (bool): カメラを検索する指定。
        ca (bool): camerasの短縮名。同時指定はできない。
        containerType (str | Iterable[str]): コンテナ型の名前による検索条件。
        ct (str | Iterable[str]): containerTypeの短縮名。同時指定はできない。
        containers (bool): コンテナを検索する指定。
        con (bool): containersの短縮名。同時指定はできない。
        dagObjects (bool): DAGノードを検索する指定。
        dag (bool): dagObjectsの短縮名。同時指定はできない。
        defaultNodes (bool): 既定ノードを検索する指定。
        dn (bool): defaultNodesの短縮名。同時指定はできない。
        dependencyNodes (bool): 依存ノードを検索する指定。
        dep (bool): dependencyNodesの短縮名。同時指定はできない。
        exactType (str | Iterable[str]): 型との完全一致による検索条件。複数指定の扱いはMayaに従う。
        et (str | Iterable[str]): exactTypeの短縮名。同時指定はできない。
        excludeType (str | Iterable[str]): 検索から除外するノード型。
        ext (str | Iterable[str]): excludeTypeの短縮名。同時指定はできない。
        flatten (bool): Maya側の範囲展開指定。mlibのComponent結果はこの値によらず単体へ展開する。
        fl (bool): flattenの短縮名。同時指定はできない。
        geometry (bool): ジオメトリを検索する指定。
        g (bool): geometryの短縮名。同時指定はできない。
        ghost (bool): ゴースト表示されたノードを検索する指定。
        gh (bool): ghostの短縮名。同時指定はできない。
        head (int): 取得する先頭件数。型ごとの上限の扱いはMayaに従う。
        hd (int): headの短縮名。同時指定はできない。
        hilite (bool): ハイライトされた対象を検索する指定。
        hl (bool): hiliteの短縮名。同時指定はできない。
        intermediateObjects (bool): 中間Shapeを検索する指定。
        io (bool): intermediateObjectsの短縮名。同時指定はできない。
        invisible (bool): 非表示の対象を検索する指定。
        iv (bool): invisibleの短縮名。同時指定はできない。
        leaf (bool): 末端のDAGノードを検索する指定。
        lf (bool): leafの短縮名。同時指定はできない。
        lights (bool): ライトを検索する指定。
        lt (bool): lightsの短縮名。同時指定はできない。
        live (bool): ライブ状態の対象を検索する指定。
        lv (bool): liveの短縮名。同時指定はできない。
        lockedNodes (bool): ロックされたノードを検索する指定。
        ln (bool): lockedNodesの短縮名。同時指定はできない。
        long (bool): 完全DAGパスで結果名を受け取る指定。
        l (bool): longの短縮名。同時指定はできない。
        materials (bool): マテリアルを検索する指定。
        mat (bool): materialsの短縮名。同時指定はできない。
        modified (bool): 変更されたノードを検索する指定。
        mod (bool): modifiedの短縮名。同時指定はできない。
        noIntermediate (bool): 中間Shapeを除く指定。
        ni (bool): noIntermediateの短縮名。同時指定はできない。
        nodeTypes (bool): ノード型名の一覧を返すMayaフラグ。シーン参照を返さないためmlibでは非対応。
        nt (bool): nodeTypesの短縮名。同時指定はできない。
        objectsOnly (bool): アトリビュート・コンポーネントを除いてノードを検索する指定。
        o (bool): objectsOnlyの短縮名。同時指定はできない。
        orderedComponentSelection (bool): コンポーネントの選択順を使う指定。Maya2025以降で利用可能。
        ocs (bool): orderedComponentSelectionの短縮名。同時指定はできない。
        orderedSelection (bool): 選択順で取得する指定。Mayaの選択順追跡設定に従う。
        os (bool): orderedSelectionの短縮名。同時指定はできない。
        partitions (bool): パーティションを検索する指定。
        pr (bool): partitionsの短縮名。同時指定はできない。
        persistentNodes (bool): 永続ノードを検索する指定。
        pn (bool): persistentNodesの短縮名。同時指定はできない。
        planes (bool): プレーンを検索するMayaフラグ。
        pl (bool): planesの短縮名。同時指定はできない。
        preSelectHilite (bool): 選択前ハイライトの対象を検索する指定。
        psh (bool): preSelectHiliteの短縮名。同時指定はできない。
        readOnly (bool): 読み取り専用ノードを検索するMayaフラグ。
        ro (bool): readOnlyの短縮名。同時指定はできない。
        recursive (bool): 名前空間を再帰的に検索する指定。
        r (bool): recursiveの短縮名。同時指定はできない。
        referencedNodes (bool): 参照ファイル内のノードを検索する指定。
        rn (bool): referencedNodesの短縮名。同時指定はできない。
        references (bool): 参照ノードを検索する指定。
        rf (bool): referencesの短縮名。同時指定はできない。
        renderGlobals (bool): レンダーグローバルを検索するMayaフラグ。
        rg (bool): renderGlobalsの短縮名。同時指定はできない。
        renderQualities (bool): レンダー品質ノードを検索するMayaフラグ。
        rq (bool): renderQualitiesの短縮名。同時指定はできない。
        renderResolutions (bool): レンダー解像度ノードを検索するMayaフラグ。
        rr (bool): renderResolutionsの短縮名。同時指定はできない。
        renderSetups (bool): レンダーセットアップを検索するMayaフラグ。
        rs (bool): renderSetupsの短縮名。同時指定はできない。
        selection (bool): 現在の選択を検索する指定。
        sl (bool): selectionの短縮名。同時指定はできない。
        sets (bool): セットを検索する指定。
        set (bool): setsの短縮名。同時指定はできない。
        shapes (bool): Shapeを検索する指定。
        s (bool): shapesの短縮名。同時指定はできない。
        shortNames (bool): アトリビュート名を短名で受け取る指定。
        sn (bool): shortNamesの短縮名。同時指定はできない。
        showNamespace (bool): 名前空間を併記する指定。参照名以外を返す使い方は非対応。
        sns (bool): showNamespaceの短縮名。同時指定はできない。
        showType (bool): 型名を併記するMayaフラグ。参照名以外を返す使い方は非対応。
        st (bool): showTypeの短縮名。同時指定はできない。
        tail (int): 取得する末尾件数。型ごとの上限の扱いはMayaに従う。
        tl (int): tailの短縮名。同時指定はできない。
        templated (bool): テンプレート表示の対象を検索する指定。
        tm (bool): templatedの短縮名。同時指定はできない。
        textures (bool): テクスチャを検索する指定。
        tex (bool): texturesの短縮名。同時指定はできない。
        transforms (bool): Transformを検索する指定。
        tr (bool): transformsの短縮名。同時指定はできない。
        type (str | Iterable[str]): ノード型、またはvertex/edge/face/uv/controlVertex。joint/skinClusterは専用コレクションを返す。
        typ (str | Iterable[str]): typeの短縮名。同時指定はできない。
        ufeObjects (bool): UFE項目を含めるMayaフラグ。mlib参照へ解決できない結果は非対応。
        ufe (bool): ufeObjectsの短縮名。同時指定はできない。
        undeletable (bool): 削除不可のノードを検索する指定。
        ud (bool): undeletableの短縮名。同時指定はできない。
        untemplated (bool): テンプレートでない対象を検索する指定。
        ut (bool): untemplatedの短縮名。同時指定はできない。
        uuid (bool): UUID文字列を返すMayaフラグ。シーン参照を返さないためmlibでは非対応。
        uid (bool): uuidの短縮名。同時指定はできない。
        visible (bool): 表示中の対象を検索する指定。
        v (bool): visibleの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        **kwargs (object): 今後追加される未知のMayaフラグ。そのままMayaへ渡す。

    Returns:
        list[Node | Plug | Component] | Joints | SkinClusters: コンポーネント型指定時は単体要素のリスト。
            ノード型のtypeまたはtypがjoint/skinClusterの場合は従来の専用コレクション。

    Raises:
        TypeError: 長名・短名を同時指定した場合、または位置引数に対応しない型が含まれる場合。
        ValueError: 位置引数に削除済みの対象が含まれる場合。
        RuntimeError: 検索結果をノードとして解決できない場合。

    Note:
        型名等を返すMayaフラグは非対応。検索結果が空なら空コレクションまたは空リスト。
        結果の名前はまとめて解決するが、並び順はMayaが返した順のまま変えない。Mayaの結果に同じ名前が
        重複して含まれる場合も統合せず、それぞれを別の参照として返す。
    """
    short_assemblies = kwargs.pop("as", _UNSET)
    _merge_flags(kwargs, (
        (absoluteName, an, "absoluteName", "an"),
        (allPaths, ap, "allPaths", "ap"),
        (assemblies, short_assemblies, "assemblies", "as"),
        (cameras, ca, "cameras", "ca"),
        (containerType, ct, "containerType", "ct"),
        (containers, con, "containers", "con"),
        (dagObjects, dag, "dagObjects", "dag"),
        (defaultNodes, dn, "defaultNodes", "dn"),
        (dependencyNodes, dep, "dependencyNodes", "dep"),
        (exactType, et, "exactType", "et"),
        (excludeType, ext, "excludeType", "ext"),
        (flatten, fl, "flatten", "fl"),
        (geometry, g, "geometry", "g"),
        (ghost, gh, "ghost", "gh"),
        (head, hd, "head", "hd"),
        (hilite, hl, "hilite", "hl"),
        (intermediateObjects, io, "intermediateObjects", "io"),
        (invisible, iv, "invisible", "iv"),
        (leaf, lf, "leaf", "lf"),
        (lights, lt, "lights", "lt"),
        (live, lv, "live", "lv"),
        (lockedNodes, ln, "lockedNodes", "ln"),
        (long, l, "long", "l"),
        (materials, mat, "materials", "mat"),
        (modified, mod, "modified", "mod"),
        (noIntermediate, ni, "noIntermediate", "ni"),
        (nodeTypes, nt, "nodeTypes", "nt"),
        (objectsOnly, o, "objectsOnly", "o"),
        (orderedComponentSelection, ocs, "orderedComponentSelection", "ocs"),
        (orderedSelection, os, "orderedSelection", "os"),
        (partitions, pr, "partitions", "pr"),
        (persistentNodes, pn, "persistentNodes", "pn"),
        (planes, pl, "planes", "pl"),
        (preSelectHilite, psh, "preSelectHilite", "psh"),
        (readOnly, ro, "readOnly", "ro"),
        (recursive, r, "recursive", "r"),
        (referencedNodes, rn, "referencedNodes", "rn"),
        (references, rf, "references", "rf"),
        (renderGlobals, rg, "renderGlobals", "rg"),
        (renderQualities, rq, "renderQualities", "rq"),
        (renderResolutions, rr, "renderResolutions", "rr"),
        (renderSetups, rs, "renderSetups", "rs"),
        (selection, sl, "selection", "sl"),
        (sets, set, "sets", "set"),
        (shapes, s, "shapes", "s"),
        (shortNames, sn, "shortNames", "sn"),
        (showNamespace, sns, "showNamespace", "sns"),
        (showType, st, "showType", "st"),
        (tail, tl, "tail", "tl"),
        (templated, tm, "templated", "tm"),
        (textures, tex, "textures", "tex"),
        (transforms, tr, "transforms", "tr"),
        (type, typ, "type", "typ"),
        (ufeObjects, ufe, "ufeObjects", "ufe"),
        (undeletable, ud, "undeletable", "ud"),
        (untemplated, ut, "untemplated", "ut"),
        (uuid, uid, "uuid", "uid"),
        (visible, v, "visible", "v"),
        (query, q, "query", "q"),
        (edit, e, "edit", "e"),
    ))
    # nodes・components・common.selectionはcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Nodes as _InputNodes
    from ..core.object import Object as _InputObject
    from ..nodes import Joints, SkinClusters
    from ..components import Vertex, Edge, Face, UV, CV
    from ..common.selection import Selection

    component_types = {"vertex": Vertex, "edge": Edge, "face": Face,
                       "uv": UV, "controlVertex": CV}
    node_type = kwargs.get("type")
    component = node_type if isinstance(node_type, str) and node_type in component_types else None
    if component is not None:
        kwargs.pop("type")

    targets = []
    for arg in _InputNodes._resolve_inputs([arg for arg in args if arg is not None]):
        if isinstance(arg, str):
            targets.append(arg)
        else:
            targets.extend(_InputObject._input_names(arg))
    # 空の列だけを渡した場合に maya.cmds.ls() の全ノード検索へ変わらないようにする。
    names = (cmds.ls(*targets, **kwargs) or []) if targets or not args else []
    node_type = kwargs.get("type")
    if component is None and node_type == "joint":
        return Joints(names)
    if component is None and node_type == "skinCluster":
        return SkinClusters(names)
    # Mayaの検索・並び順を維持し、解決だけを既存のOpenMaya経路へ任せる。
    # ノード名とアトリビュート名は、名前ごとに選択リストを作らずまとめて解決する(_resolve_names)。
    # 対応付けは cmds の結果の順に行い、対応付けられない名前(重複・統合・コンポーネント・
    # 複数一致・解決の失敗)は従来の名前ごとの経路で判定する。
    from ..nodes.node import Node
    from ..plugs.plug import Plug
    from ..components import Component
    from ..common.selection import _resolve_names

    if component is None:
        resolved_nodes = iter(_resolve_names([name for name in names if "." not in name]))
        resolved_plugs = iter(_resolve_names([name for name in names if "." in name], plugs=True))
    result = []
    for name in names:
        if "." not in name:
            if component is None:
                found = next(resolved_nodes)
                # Node(name) と同じ解決・型選択を、生成の入口の再判定なしで行う。
                result.append(Node._wrap_resolved(found[0], found[1]) if found is not None
                              else Node._from_name(name))
            continue
        if component is None:
            # 1要素のアトリビュートだけに解決する名前は、下の Selection(name) と
            # Plug._resolve_input(name) が同じ手順で作る Plug をまとめた解決の結果から作る。
            found = next(resolved_plugs)
            if found is not None:
                result.append(Plug(Node._wrap_resolved(found[0], found[1]), found[2]))
                continue
        resolved = Selection(name).items
        if resolved and isinstance(resolved[0], Component):
            result.extend(resolved)
        elif component is None:
            result.append(Plug._resolve_input(name))
    if component is not None:
        return [item for item in result if isinstance(item, component_types[component])]
    return result
