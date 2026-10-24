"""
Synopsis
--------

.. code-block:: python

    mlib.ls(*args, **kwargs)

名前や条件で Maya ノードを検索し、検索結果を mlib ラッパーへ変換します。

コンポーネント範囲は単体の参照へ展開します。型名などシーン参照以外を返すフラグには対応しません。

Return value
------------

``list[Node | Plug | Component] | Joints | SkinClusters``
    コンポーネント型指定時は該当する単体コンポーネントのリスト。ノード型のtype="joint" は Joints、type="skinCluster" は SkinClusters。それ以外は参照のリスト。未検出時は空。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :meth:`~mlib.nodes.transform.Transform.addConstraint`

Flags
-----

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``*args``
     - ``str | Node | Plug | Component | Components | MObject | MDagPath | MPlug | Iterable``
     - 省略可
     - 名前やワイルドカードなど、maya.cmds.ls の位置引数。文字列以外は一意な名前に変換して渡します（:doc:`/cmds_interop`）。空の列と ``None`` は空の結果になります。
   * - ``type (typ)``
     - ``str``
     - 省略可
     - Mayaのノード型、またはvertex / edge / face / uv / controlVertex。コンポーネントは単一の正式名称で指定し、vtx/e/f/map/cv等の別名は追加しません。種類の変換は行いません。
   * - ``selection (sl)``
     - ``bool``
     - False
     - 選択中のノード・アトリビュート・コンポーネントを取得。
   * - ``long (l)``
     - ``bool``
     - False
     - Maya から完全な DAG パスを取得。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の ls フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import mlib

    nodes = mlib.ls(type="transform")
    joints = mlib.ls(type="joint")
    selected = mlib.ls(selection=True)
    vertices = mlib.ls(sl=True, type="vertex")
    faces = mlib.ls(sl=True, type="face")
"""

import maya.cmds as cmds

from ..util import _ArgumentError, _UNSET


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

    型名等を返すMayaフラグは非対応。検索結果が空なら空コレクションまたは空リスト。
    """
    if absoluteName is not _UNSET:
        if an is not _UNSET:
            raise _ArgumentError("Specify only one of 'absoluteName' and 'an'")
        kwargs["absoluteName"] = absoluteName
    elif an is not _UNSET:
        kwargs["absoluteName"] = an
    if allPaths is not _UNSET:
        if ap is not _UNSET:
            raise _ArgumentError("Specify only one of 'allPaths' and 'ap'")
        kwargs["allPaths"] = allPaths
    elif ap is not _UNSET:
        kwargs["allPaths"] = ap
    short_assemblies = kwargs.pop("as", _UNSET)
    if assemblies is not _UNSET:
        if short_assemblies is not _UNSET:
            raise _ArgumentError("Specify only one of 'assemblies' and 'as'")
        kwargs["assemblies"] = assemblies
    elif short_assemblies is not _UNSET:
        kwargs["assemblies"] = short_assemblies
    if cameras is not _UNSET:
        if ca is not _UNSET:
            raise _ArgumentError("Specify only one of 'cameras' and 'ca'")
        kwargs["cameras"] = cameras
    elif ca is not _UNSET:
        kwargs["cameras"] = ca
    if containerType is not _UNSET:
        if ct is not _UNSET:
            raise _ArgumentError("Specify only one of 'containerType' and 'ct'")
        kwargs["containerType"] = containerType
    elif ct is not _UNSET:
        kwargs["containerType"] = ct
    if containers is not _UNSET:
        if con is not _UNSET:
            raise _ArgumentError("Specify only one of 'containers' and 'con'")
        kwargs["containers"] = containers
    elif con is not _UNSET:
        kwargs["containers"] = con
    if dagObjects is not _UNSET:
        if dag is not _UNSET:
            raise _ArgumentError("Specify only one of 'dagObjects' and 'dag'")
        kwargs["dagObjects"] = dagObjects
    elif dag is not _UNSET:
        kwargs["dagObjects"] = dag
    if defaultNodes is not _UNSET:
        if dn is not _UNSET:
            raise _ArgumentError("Specify only one of 'defaultNodes' and 'dn'")
        kwargs["defaultNodes"] = defaultNodes
    elif dn is not _UNSET:
        kwargs["defaultNodes"] = dn
    if dependencyNodes is not _UNSET:
        if dep is not _UNSET:
            raise _ArgumentError("Specify only one of 'dependencyNodes' and 'dep'")
        kwargs["dependencyNodes"] = dependencyNodes
    elif dep is not _UNSET:
        kwargs["dependencyNodes"] = dep
    if exactType is not _UNSET:
        if et is not _UNSET:
            raise _ArgumentError("Specify only one of 'exactType' and 'et'")
        kwargs["exactType"] = exactType
    elif et is not _UNSET:
        kwargs["exactType"] = et
    if excludeType is not _UNSET:
        if ext is not _UNSET:
            raise _ArgumentError("Specify only one of 'excludeType' and 'ext'")
        kwargs["excludeType"] = excludeType
    elif ext is not _UNSET:
        kwargs["excludeType"] = ext
    if flatten is not _UNSET:
        if fl is not _UNSET:
            raise _ArgumentError("Specify only one of 'flatten' and 'fl'")
        kwargs["flatten"] = flatten
    elif fl is not _UNSET:
        kwargs["flatten"] = fl
    if geometry is not _UNSET:
        if g is not _UNSET:
            raise _ArgumentError("Specify only one of 'geometry' and 'g'")
        kwargs["geometry"] = geometry
    elif g is not _UNSET:
        kwargs["geometry"] = g
    if ghost is not _UNSET:
        if gh is not _UNSET:
            raise _ArgumentError("Specify only one of 'ghost' and 'gh'")
        kwargs["ghost"] = ghost
    elif gh is not _UNSET:
        kwargs["ghost"] = gh
    if head is not _UNSET:
        if hd is not _UNSET:
            raise _ArgumentError("Specify only one of 'head' and 'hd'")
        kwargs["head"] = head
    elif hd is not _UNSET:
        kwargs["head"] = hd
    if hilite is not _UNSET:
        if hl is not _UNSET:
            raise _ArgumentError("Specify only one of 'hilite' and 'hl'")
        kwargs["hilite"] = hilite
    elif hl is not _UNSET:
        kwargs["hilite"] = hl
    if intermediateObjects is not _UNSET:
        if io is not _UNSET:
            raise _ArgumentError("Specify only one of 'intermediateObjects' and 'io'")
        kwargs["intermediateObjects"] = intermediateObjects
    elif io is not _UNSET:
        kwargs["intermediateObjects"] = io
    if invisible is not _UNSET:
        if iv is not _UNSET:
            raise _ArgumentError("Specify only one of 'invisible' and 'iv'")
        kwargs["invisible"] = invisible
    elif iv is not _UNSET:
        kwargs["invisible"] = iv
    if leaf is not _UNSET:
        if lf is not _UNSET:
            raise _ArgumentError("Specify only one of 'leaf' and 'lf'")
        kwargs["leaf"] = leaf
    elif lf is not _UNSET:
        kwargs["leaf"] = lf
    if lights is not _UNSET:
        if lt is not _UNSET:
            raise _ArgumentError("Specify only one of 'lights' and 'lt'")
        kwargs["lights"] = lights
    elif lt is not _UNSET:
        kwargs["lights"] = lt
    if live is not _UNSET:
        if lv is not _UNSET:
            raise _ArgumentError("Specify only one of 'live' and 'lv'")
        kwargs["live"] = live
    elif lv is not _UNSET:
        kwargs["live"] = lv
    if lockedNodes is not _UNSET:
        if ln is not _UNSET:
            raise _ArgumentError("Specify only one of 'lockedNodes' and 'ln'")
        kwargs["lockedNodes"] = lockedNodes
    elif ln is not _UNSET:
        kwargs["lockedNodes"] = ln
    if long is not _UNSET:
        if l is not _UNSET:
            raise _ArgumentError("Specify only one of 'long' and 'l'")
        kwargs["long"] = long
    elif l is not _UNSET:
        kwargs["long"] = l
    if materials is not _UNSET:
        if mat is not _UNSET:
            raise _ArgumentError("Specify only one of 'materials' and 'mat'")
        kwargs["materials"] = materials
    elif mat is not _UNSET:
        kwargs["materials"] = mat
    if modified is not _UNSET:
        if mod is not _UNSET:
            raise _ArgumentError("Specify only one of 'modified' and 'mod'")
        kwargs["modified"] = modified
    elif mod is not _UNSET:
        kwargs["modified"] = mod
    if noIntermediate is not _UNSET:
        if ni is not _UNSET:
            raise _ArgumentError("Specify only one of 'noIntermediate' and 'ni'")
        kwargs["noIntermediate"] = noIntermediate
    elif ni is not _UNSET:
        kwargs["noIntermediate"] = ni
    if nodeTypes is not _UNSET:
        if nt is not _UNSET:
            raise _ArgumentError("Specify only one of 'nodeTypes' and 'nt'")
        kwargs["nodeTypes"] = nodeTypes
    elif nt is not _UNSET:
        kwargs["nodeTypes"] = nt
    if objectsOnly is not _UNSET:
        if o is not _UNSET:
            raise _ArgumentError("Specify only one of 'objectsOnly' and 'o'")
        kwargs["objectsOnly"] = objectsOnly
    elif o is not _UNSET:
        kwargs["objectsOnly"] = o
    if orderedComponentSelection is not _UNSET:
        if ocs is not _UNSET:
            raise _ArgumentError("Specify only one of 'orderedComponentSelection' and 'ocs'")
        kwargs["orderedComponentSelection"] = orderedComponentSelection
    elif ocs is not _UNSET:
        kwargs["orderedComponentSelection"] = ocs
    if orderedSelection is not _UNSET:
        if os is not _UNSET:
            raise _ArgumentError("Specify only one of 'orderedSelection' and 'os'")
        kwargs["orderedSelection"] = orderedSelection
    elif os is not _UNSET:
        kwargs["orderedSelection"] = os
    if partitions is not _UNSET:
        if pr is not _UNSET:
            raise _ArgumentError("Specify only one of 'partitions' and 'pr'")
        kwargs["partitions"] = partitions
    elif pr is not _UNSET:
        kwargs["partitions"] = pr
    if persistentNodes is not _UNSET:
        if pn is not _UNSET:
            raise _ArgumentError("Specify only one of 'persistentNodes' and 'pn'")
        kwargs["persistentNodes"] = persistentNodes
    elif pn is not _UNSET:
        kwargs["persistentNodes"] = pn
    if planes is not _UNSET:
        if pl is not _UNSET:
            raise _ArgumentError("Specify only one of 'planes' and 'pl'")
        kwargs["planes"] = planes
    elif pl is not _UNSET:
        kwargs["planes"] = pl
    if preSelectHilite is not _UNSET:
        if psh is not _UNSET:
            raise _ArgumentError("Specify only one of 'preSelectHilite' and 'psh'")
        kwargs["preSelectHilite"] = preSelectHilite
    elif psh is not _UNSET:
        kwargs["preSelectHilite"] = psh
    if readOnly is not _UNSET:
        if ro is not _UNSET:
            raise _ArgumentError("Specify only one of 'readOnly' and 'ro'")
        kwargs["readOnly"] = readOnly
    elif ro is not _UNSET:
        kwargs["readOnly"] = ro
    if recursive is not _UNSET:
        if r is not _UNSET:
            raise _ArgumentError("Specify only one of 'recursive' and 'r'")
        kwargs["recursive"] = recursive
    elif r is not _UNSET:
        kwargs["recursive"] = r
    if referencedNodes is not _UNSET:
        if rn is not _UNSET:
            raise _ArgumentError("Specify only one of 'referencedNodes' and 'rn'")
        kwargs["referencedNodes"] = referencedNodes
    elif rn is not _UNSET:
        kwargs["referencedNodes"] = rn
    if references is not _UNSET:
        if rf is not _UNSET:
            raise _ArgumentError("Specify only one of 'references' and 'rf'")
        kwargs["references"] = references
    elif rf is not _UNSET:
        kwargs["references"] = rf
    if renderGlobals is not _UNSET:
        if rg is not _UNSET:
            raise _ArgumentError("Specify only one of 'renderGlobals' and 'rg'")
        kwargs["renderGlobals"] = renderGlobals
    elif rg is not _UNSET:
        kwargs["renderGlobals"] = rg
    if renderQualities is not _UNSET:
        if rq is not _UNSET:
            raise _ArgumentError("Specify only one of 'renderQualities' and 'rq'")
        kwargs["renderQualities"] = renderQualities
    elif rq is not _UNSET:
        kwargs["renderQualities"] = rq
    if renderResolutions is not _UNSET:
        if rr is not _UNSET:
            raise _ArgumentError("Specify only one of 'renderResolutions' and 'rr'")
        kwargs["renderResolutions"] = renderResolutions
    elif rr is not _UNSET:
        kwargs["renderResolutions"] = rr
    if renderSetups is not _UNSET:
        if rs is not _UNSET:
            raise _ArgumentError("Specify only one of 'renderSetups' and 'rs'")
        kwargs["renderSetups"] = renderSetups
    elif rs is not _UNSET:
        kwargs["renderSetups"] = rs
    if selection is not _UNSET:
        if sl is not _UNSET:
            raise _ArgumentError("Specify only one of 'selection' and 'sl'")
        kwargs["selection"] = selection
    elif sl is not _UNSET:
        kwargs["selection"] = sl
    if sets is not _UNSET:
        if set is not _UNSET:
            raise _ArgumentError("Specify only one of 'sets' and 'set'")
        kwargs["sets"] = sets
    elif set is not _UNSET:
        kwargs["sets"] = set
    if shapes is not _UNSET:
        if s is not _UNSET:
            raise _ArgumentError("Specify only one of 'shapes' and 's'")
        kwargs["shapes"] = shapes
    elif s is not _UNSET:
        kwargs["shapes"] = s
    if shortNames is not _UNSET:
        if sn is not _UNSET:
            raise _ArgumentError("Specify only one of 'shortNames' and 'sn'")
        kwargs["shortNames"] = shortNames
    elif sn is not _UNSET:
        kwargs["shortNames"] = sn
    if showNamespace is not _UNSET:
        if sns is not _UNSET:
            raise _ArgumentError("Specify only one of 'showNamespace' and 'sns'")
        kwargs["showNamespace"] = showNamespace
    elif sns is not _UNSET:
        kwargs["showNamespace"] = sns
    if showType is not _UNSET:
        if st is not _UNSET:
            raise _ArgumentError("Specify only one of 'showType' and 'st'")
        kwargs["showType"] = showType
    elif st is not _UNSET:
        kwargs["showType"] = st
    if tail is not _UNSET:
        if tl is not _UNSET:
            raise _ArgumentError("Specify only one of 'tail' and 'tl'")
        kwargs["tail"] = tail
    elif tl is not _UNSET:
        kwargs["tail"] = tl
    if templated is not _UNSET:
        if tm is not _UNSET:
            raise _ArgumentError("Specify only one of 'templated' and 'tm'")
        kwargs["templated"] = templated
    elif tm is not _UNSET:
        kwargs["templated"] = tm
    if textures is not _UNSET:
        if tex is not _UNSET:
            raise _ArgumentError("Specify only one of 'textures' and 'tex'")
        kwargs["textures"] = textures
    elif tex is not _UNSET:
        kwargs["textures"] = tex
    if transforms is not _UNSET:
        if tr is not _UNSET:
            raise _ArgumentError("Specify only one of 'transforms' and 'tr'")
        kwargs["transforms"] = transforms
    elif tr is not _UNSET:
        kwargs["transforms"] = tr
    if type is not _UNSET:
        if typ is not _UNSET:
            raise _ArgumentError("Specify only one of 'type' and 'typ'")
        kwargs["type"] = type
    elif typ is not _UNSET:
        kwargs["type"] = typ
    if ufeObjects is not _UNSET:
        if ufe is not _UNSET:
            raise _ArgumentError("Specify only one of 'ufeObjects' and 'ufe'")
        kwargs["ufeObjects"] = ufeObjects
    elif ufe is not _UNSET:
        kwargs["ufeObjects"] = ufe
    if undeletable is not _UNSET:
        if ud is not _UNSET:
            raise _ArgumentError("Specify only one of 'undeletable' and 'ud'")
        kwargs["undeletable"] = undeletable
    elif ud is not _UNSET:
        kwargs["undeletable"] = ud
    if untemplated is not _UNSET:
        if ut is not _UNSET:
            raise _ArgumentError("Specify only one of 'untemplated' and 'ut'")
        kwargs["untemplated"] = untemplated
    elif ut is not _UNSET:
        kwargs["untemplated"] = ut
    if uuid is not _UNSET:
        if uid is not _UNSET:
            raise _ArgumentError("Specify only one of 'uuid' and 'uid'")
        kwargs["uuid"] = uuid
    elif uid is not _UNSET:
        kwargs["uuid"] = uid
    if visible is not _UNSET:
        if v is not _UNSET:
            raise _ArgumentError("Specify only one of 'visible' and 'v'")
        kwargs["visible"] = visible
    elif v is not _UNSET:
        kwargs["visible"] = v
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
        if arg is None:
            continue
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
    # 全件を単一Selectionにすると重複が除かれるため、結果ごとに解決する。
    from ..nodes.node import Node
    from ..plugs.plug import Plug
    from ..components import Component

    result = []
    for name in names:
        if "." not in name:
            if component is None:
                result.append(Node(name))
            continue
        resolved = Selection(name).items
        if resolved and isinstance(resolved[0], Component):
            result.extend(resolved)
        elif component is None:
            result.append(Plug._resolve_input(name))
    if component is not None:
        return [item for item in result if isinstance(item, component_types[component])]
    return result
