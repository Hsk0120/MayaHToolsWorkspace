"""単一の対象を複製し、複製結果の先頭ノードを型に応じたラッパーで返す。

通常は ``maya.cmds.duplicate`` に委ね、MayaのUndoに対応する(1回のUndoで戻せる)。
``fast=True`` は ``om2.MFnDagNode.duplicate`` で複製し、Undo履歴を追加しない。fastは
``cmds.duplicate`` と同じ結果(名前・親・アトリビュートのロック/キー設定可能/チャンネルボックス表示・
セットの所属・jointのinverseScale接続・選択・戻り値)になると確かめた組合せだけを受け付け、
それ以外は複製する前に NotImplementedError にする。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    copied = mlib.duplicate(node, name="exampleCopy")
    fastCopy = mlib.duplicate(node, fast=True)
"""

import re

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _edit_context, _merge_flags
from ..util import _UNSET

#: fast=True で複製できる階層内のnodeType。他の型はcmds固有の複製規則を確かめていないため拒否する。
_FAST_NODE_TYPES = frozenset(("transform", "joint", "mesh", "nurbsCurve", "nurbsSurface", "locator"))
#: fast=True で既定値(False)の指定だけを受け付けるフラグ。True はcmdsと同じ結果を作れない。
_FAST_FALSE_ONLY_FLAGS = frozenset(("inputConnections", "instanceLeaf", "parentOnly", "renameChildren",
                                    "smartTransform", "transformsOnly", "upstreamNodes"))
#: fast=True で値によらず受け付けるフラグ。cmdsの戻り値の形だけを変え、mlibは常に複製ルートを返す。
_FAST_RESULT_FLAGS = frozenset(("fullPath", "returnRootsOnly"))
#: 名前の末尾の数字を分ける。
_TRAILING_DIGITS = re.compile(r"^(.*?)(\d*)$")


def duplicate(node, *, fast=False,
        fullPath=_UNSET, f=_UNSET,
        inputConnections=_UNSET, ic=_UNSET,
        instanceLeaf=_UNSET, ilf=_UNSET,
        name=_UNSET, n=_UNSET,
        parentOnly=_UNSET, po=_UNSET,
        renameChildren=_UNSET, rc=_UNSET,
        returnRootsOnly=_UNSET, rr=_UNSET,
        smartTransform=_UNSET, st=_UNSET,
        transformsOnly=_UNSET, to=_UNSET,
        upstreamNodes=_UNSET, un=_UNSET,
        query=_UNSET, q=_UNSET,
        edit=_UNSET, e=_UNSET,
        **kwargs):
    """指定したノードを複製し、対応する mlib wrapper として返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    ``fast=True`` の対応範囲(範囲外は複製する前に NotImplementedError):

    - 対象はインスタンス化されていない transform・joint の DAG 階層。階層内の型は transform・joint・
      mesh・nurbsCurve・nurbsSurface・locator に限る。中間オブジェクト・名前空間付きの名前・ロックまたは
      参照されたノード・ロックされた親は扱わない。現在の名前空間がルートであること。
    - フラグは name/n・fullPath/f・returnRootsOnly/rr と、inputConnections/ic・instanceLeaf/ilf・
      parentOnly/po・renameChildren/rc・smartTransform/st・transformsOnly/to・upstreamNodes/un の
      False 指定だけ。name に名前空間(``:``)は使えない。query/edit と未知のフラグは受け付けない。
    - 階層の DG 接続は、外部からの入力(cmds と同様に複製しない)・ノード全体のセット所属
      (shadingEngine・objectSet。複製側も同じセットへ加える)・DAG 親の scale から joint の
      inverseScale への接続(複製側にも作る)だけ。フェース単位の割り当て・display layer・
      その他の出力側の接続は扱わない。
    - 名前は cmds と同じ規則で決める(ルートは Maya の連番または name、子は元の名前、ルート直下の
      shape はルートの改名に連動)。選択は複製元が選択されていた場合だけ複製ルートに置き換える。

    Args:
        node (object): 複製元のNode・Plug・Component・API参照または名前。Mayaへ渡す一意な名前へ変換する。
        fast (bool): TrueはOpenMayaで複製しUndoに記録しない。既定Falseはcmds.duplicate。
        fullPath (bool): Mayaの複製結果を完全DAGパスで受け取る指定。mlibの戻り型は変わらない。
        f (bool): fullPathの短縮名。同時指定はできない。
        inputConnections (bool): 入力接続も複製する指定。
        ic (bool): inputConnectionsの短縮名。同時指定はできない。
        instanceLeaf (bool): 末端ノードを複製せずインスタンス化する指定。
        ilf (bool): instanceLeafの短縮名。同時指定はできない。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parentOnly (bool): 指定した対象だけを複製し、子階層を含めない指定。
        po (bool): parentOnlyの短縮名。同時指定はできない。
        renameChildren (bool): 複製した子の名前をMayaの規則で補正する指定。
        rc (bool): renameChildrenの短縮名。同時指定はできない。
        returnRootsOnly (bool): Maya側の戻り値を複製ルートだけにする指定。mlibは先頭をラップする。
        rr (bool): returnRootsOnlyの短縮名。同時指定はできない。
        smartTransform (bool): 前回の複製からの変換差を使うMayaの複製指定。
        st (bool): smartTransformの短縮名。同時指定はできない。
        transformsOnly (bool): Transformのみを複製するMayaフラグ。
        to (bool): transformsOnlyの短縮名。同時指定はできない。
        upstreamNodes (bool): 上流の依存ノードも複製する指定。
        un (bool): upstreamNodesの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        **kwargs (object): 今後追加される未知のMayaフラグ。通常はそのままMayaへ渡し、
            fast=Trueでは複製する前に拒否する。

    Returns:
        Node: 複製された起点ノードに対応するラッパー。

    Raises:
        TypeError: 長名・短名を同時指定した場合、fastがbool以外、またはnodeが対応しない型の場合。
        ValueError: node が空文字列・存在しない名前・複数に一致する名前、または削除済みの対象の場合。
        RuntimeError: Maya が複製を拒否した場合。
        NotImplementedError: fast=Trueで上記の対応範囲外の対象・フラグを指定した場合(複製しない)。
    """
    _merge_flags(kwargs, (
        (fullPath, f, "fullPath", "f"),
        (inputConnections, ic, "inputConnections", "ic"),
        (instanceLeaf, ilf, "instanceLeaf", "ilf"),
        (name, n, "name", "n"),
        (parentOnly, po, "parentOnly", "po"),
        (renameChildren, rc, "renameChildren", "rc"),
        (returnRootsOnly, rr, "returnRootsOnly", "rr"),
        (smartTransform, st, "smartTransform", "st"),
        (transformsOnly, to, "transformsOnly", "to"),
        (upstreamNodes, un, "upstreamNodes", "un"),
        (query, q, "query", "q"),
        (edit, e, "edit", "e"),
    ))
    with _edit_context("mlibDuplicate", fast):
        # nodesはcmdsを参照するため、循環importを避けて関数内で読み込む。
        from ..core.object import Object as _InputObject
        from ..nodes import Node

        name = _InputObject._input_name(node)
        if fast:
            return Node._wrap_dag_path(_duplicate_fast(name, kwargs))
        result = cmds.duplicate(name, **kwargs)
        return Node(result[0])


def _duplicate_fast(name, flags):
    """``cmds.duplicate`` と同じ結果になる条件だけをOpenMayaで複製する。

    検査はすべて複製の前に行い、範囲外ならシーンを変更せずに拒否する。

    Args:
        name (str): 複製元の名前。
        flags (dict): 長名へ正規化したフラグ。

    Returns:
        om2.MDagPath: 複製したルートのDAGパス。

    Raises:
        ValueError: nameが存在しない、または複数のノードに一致する場合。
        NotImplementedError: 対応範囲外の対象・フラグの場合。
        RuntimeError: 複製した階層が複製元と対応しない場合(複製結果は削除する)。
    """
    new_name = _fast_name(flags)
    source = _source_path(name)
    nodes = _fast_hierarchy(source)
    joint_links, set_links = _fast_connections(nodes)
    states = [_plug_states(om2.MFnDependencyNode(path.node())) for path in nodes]
    was_selected = om2.MGlobal.getActiveSelectionList().hasItem(source)

    root = om2.MDagPath.getAPathTo(om2.MFnDagNode(source).duplicate(False, False))
    copies = _hierarchy_paths(root)
    if [om2.MFnDagNode(path).typeName for path in copies] != [om2.MFnDagNode(path).typeName for path in nodes]:
        modifier = om2.MDagModifier()
        modifier.deleteNode(root.node())
        modifier.doIt()
        raise RuntimeError(f"Duplicated hierarchy does not match the source: {name}")
    _apply_names(nodes, copies, new_name)
    for state, copy in zip(states, copies):
        _restore_plug_states(om2.MFnDependencyNode(copy.node()), state)
    index_of = {path.fullPathName(): index for index, path in enumerate(nodes)}
    modifier = om2.MDGModifier()
    for child_index, parent_path in joint_links:
        parent_index = index_of.get(parent_path.fullPathName())
        parent = copies[parent_index].node() if parent_index is not None else parent_path.node()
        modifier.connect(om2.MFnDependencyNode(parent).findPlug("scale", False),
                         om2.MFnDependencyNode(copies[child_index].node()).findPlug("inverseScale", False))
    modifier.doIt()
    for node_index, set_object in set_links:
        om2.MFnSet(set_object).addMember((copies[node_index], om2.MObject.kNullObj))
    if was_selected:
        selection = om2.MSelectionList()
        selection.add(copies[0])
        om2.MGlobal.setActiveSelectionList(selection, om2.MGlobal.kReplaceList)
    return copies[0]


def _fast_name(flags):
    """fastで受け付けるフラグを検査し、ルートの新しい名前を返す。

    Args:
        flags (dict): 長名へ正規化したフラグ。

    Returns:
        str | None: nameフラグの値。省略・空文字列はNone(cmdsと同じくMayaの連番名)。

    Raises:
        NotImplementedError: 未対応のフラグ・値の場合。
    """
    unsupported = sorted(key for key, value in flags.items()
                         if key != "name" and key not in _FAST_RESULT_FLAGS
                         and not (key in _FAST_FALSE_ONLY_FLAGS and value is False))
    if unsupported:
        raise NotImplementedError(f"fast duplicate does not support flags: {', '.join(unsupported)}")
    new_name = flags.get("name")
    if new_name is None or new_name == "":
        return None
    if not isinstance(new_name, str):
        raise NotImplementedError("fast duplicate supports only a string name")
    if ":" in new_name:
        raise NotImplementedError("fast duplicate does not support namespaces in name")
    return new_name


def _source_path(name):
    """複製元の名前をDAGパスへ解決する。

    Args:
        name (str): 複製元の名前。

    Returns:
        om2.MDagPath: 複製元のDAGパス。

    Raises:
        ValueError: 存在しない、または複数のノードに一致する場合。
        NotImplementedError: コンポーネント・アトリビュート・transform以外のノードの場合。
    """
    if "." in name:
        raise NotImplementedError("fast duplicate does not support components or attributes")
    selection = om2.MSelectionList()
    try:
        selection.add(name)
    except RuntimeError:
        raise ValueError(f"No object matches name: {name}") from None
    if selection.length() != 1:
        raise ValueError(f"More than one object matches name: {name}")
    if not selection.getDependNode(0).hasFn(om2.MFn.kTransform):
        raise NotImplementedError("fast duplicate supports only DAG transforms")
    return selection.getDagPath(0)


def _hierarchy_paths(root):
    """ルートと子孫のDAGパスを、子の番号順の深さ優先で返す。

    Args:
        root (om2.MDagPath): 階層のルート。

    Returns:
        list[om2.MDagPath]: ルートを先頭とする階層。
    """
    paths = []
    pending = [om2.MDagPath(root)]
    while pending:
        path = pending.pop(0)
        paths.append(path)
        children = []
        for index in range(path.childCount()):
            child = om2.MDagPath(path)
            child.push(path.child(index))
            children.append(child)
        pending[0:0] = children
    return paths


def _fast_hierarchy(source):
    """複製する階層を集め、fastの対応範囲かを検査する。

    Args:
        source (om2.MDagPath): 複製元のルート。

    Returns:
        list[om2.MDagPath]: :func:`_hierarchy_paths` の順の階層。

    Raises:
        NotImplementedError: 対応範囲外の階層の場合。
    """
    if om2.MNamespace.currentNamespace() != ":":
        raise NotImplementedError("fast duplicate requires the root namespace to be current")
    parent = om2.MFnDagNode(source).parent(0)
    if not parent.hasFn(om2.MFn.kWorld) and om2.MFnDependencyNode(parent).isLocked:
        raise NotImplementedError("fast duplicate does not support a locked parent")
    nodes = _hierarchy_paths(source)
    for path in nodes:
        fn = om2.MFnDagNode(path)
        if path.isInstanced():
            raise NotImplementedError("fast duplicate does not support instanced nodes")
        if fn.typeName not in _FAST_NODE_TYPES:
            raise NotImplementedError(f"fast duplicate does not support node type {fn.typeName}")
        if fn.isIntermediateObject:
            raise NotImplementedError("fast duplicate does not support intermediate objects")
        if fn.isLocked or fn.isFromReferencedFile:
            raise NotImplementedError("fast duplicate does not support locked or referenced nodes")
        if ":" in fn.name():
            raise NotImplementedError("fast duplicate does not support namespaced nodes")
    return nodes


def _fast_connections(nodes):
    """階層のDG接続を分類し、複製側へ作り直す接続を返す。

    Args:
        nodes (list[om2.MDagPath]): 複製する階層。

    Returns:
        tuple[list, list]: (jointの番号とDAG親のパス) のリストと、(ノード番号とセットのMObject) のリスト。

    Raises:
        NotImplementedError: cmdsと同じ結果を作れない接続がある場合。
    """
    joint_links, set_links = [], []
    for index, path in enumerate(nodes):
        node = path.node()
        for plug in om2.MFnDependencyNode(node).getConnections():
            attribute = om2.MFnAttribute(plug.attribute()).name
            if plug.isDestination:
                source = plug.source()
                if attribute == "inverseScale":
                    parent_path = om2.MDagPath(path)
                    parent_path.pop()
                    if (source.node() != parent_path.node()
                            or om2.MFnAttribute(source.attribute()).name != "scale"):
                        raise NotImplementedError("fast duplicate supports inverseScale only from the DAG parent")
                    joint_links.append((index, parent_path))
                elif attribute == "drawOverride":
                    raise NotImplementedError("fast duplicate does not support display layer membership")
                # その他の外部からの入力は、cmds.duplicate と同様に複製しない。
            if not plug.isSource:
                continue
            for target in plug.destinations():
                target_node = target.node()
                target_attribute = om2.MFnAttribute(target.attribute()).name
                if attribute == "scale" and target_attribute == "inverseScale":
                    # 子jointのinverseScaleへの接続は、子の側で作り直す。
                    continue
                if (attribute == "instObjGroups" and plug.isElement and target_attribute == "dagSetMembers"
                        and target_node.hasFn(om2.MFn.kSet)):
                    set_links.append((index, target_node))
                    continue
                raise NotImplementedError(
                    f"fast duplicate does not support the connection {plug.name()} -> {target.name()}")
    return joint_links, set_links


def _apply_names(nodes, copies, new_name):
    """複製した階層をcmds.duplicateと同じ名前にする。

    ルートはMayaの連番(またはname)、子は元の短い名前にする。ルート直下のshapeは、
    元の名前がルート名で始まる場合はその部分を、``<ルートの数字以外>Shape<ルートの数字>`` の
    場合はその形を、新しいルート名に合わせる。

    Args:
        nodes (list[om2.MDagPath]): 複製元の階層。
        copies (list[om2.MDagPath]): 同じ順の複製側の階層。
        new_name (str | None): ルートの名前。Noneは複製時のMayaの連番名。
    """
    old_root = om2.MFnDependencyNode(nodes[0].node()).name()
    root_fn = om2.MFnDependencyNode(copies[0].node())
    root_name = root_fn.setName(new_name) if new_name is not None else root_fn.name()
    old_base, old_digits = _TRAILING_DIGITS.match(old_root).groups()
    new_base, new_digits = _TRAILING_DIGITS.match(root_name).groups()
    for source, copy in zip(nodes[1:], copies[1:]):
        name = om2.MFnDependencyNode(source.node()).name()
        if copy.length() == copies[0].length() + 1 and copy.node().hasFn(om2.MFn.kShape):
            if name.startswith(old_root):
                name = root_name + name[len(old_root):]
            elif name == old_base + "Shape" + old_digits:
                name = new_base + "Shape" + new_digits
        fn = om2.MFnDependencyNode(copy.node())
        if fn.name() != name:
            fn.setName(name)


def _plug_states(fn):
    """複製で失われるプラグごとのロック・キー設定可能・チャンネルボックス表示を集める。

    Args:
        fn (om2.MFnDependencyNode): 対象のノード。

    Returns:
        dict[str, tuple[om2.MPlug, bool, bool, bool]]: アトリビュートのパスごとの
            (プラグ, ロック, キー設定可能, チャンネルボックス)。
    """
    states = {}
    for index in range(fn.attributeCount()):
        attribute = fn.attribute(index)
        if om2.MFnAttribute(attribute).parent.isNull():
            _collect_plug_states(fn.findPlug(attribute, False), states)
    return states


def _collect_plug_states(plug, states):
    """プラグと子・既存要素の状態を再帰的に集める。

    Args:
        plug (om2.MPlug): 対象のプラグ。
        states (dict): 状態を追加する辞書。
    """
    key = plug.partialName(includeNonMandatoryIndices=True, includeInstancedIndices=True,
                           useFullAttributePath=True, useLongNames=True)
    states[key] = (plug, plug.isLocked, plug.isKeyable, plug.isChannelBox)
    if plug.isArray:
        for logical in plug.getExistingArrayAttributeIndices():
            _collect_plug_states(plug.elementByLogicalIndex(logical), states)
    elif plug.isCompound:
        for child in range(plug.numChildren()):
            _collect_plug_states(plug.child(child), states)


def _restore_plug_states(fn, states):
    """複製元と違うプラグの状態を複製側へ書き戻す。

    Args:
        fn (om2.MFnDependencyNode): 複製側のノード。
        states (dict): 複製元の :func:`_plug_states` の戻り値。
    """
    copied = _plug_states(fn)
    for key, (_, locked, keyable, channel_box) in states.items():
        if key not in copied:
            continue
        plug, copy_locked, copy_keyable, copy_channel_box = copied[key]
        if copy_keyable != keyable:
            plug.isKeyable = keyable
        if copy_channel_box != channel_box:
            plug.isChannelBox = channel_box
        if copy_locked != locked:
            plug.isLocked = locked
