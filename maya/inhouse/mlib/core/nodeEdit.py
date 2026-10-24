"""Undoへ登録しないノード作成・改名・削除のOpenMaya実装。"""

import maya.api.OpenMaya as om2


def require_editable(node, descendants=False):
    """構造変更前に参照・ロックされたノードを拒否する。

    Args:
        node (MObject): 対象ノード。
        descendants (bool): DAG子孫も検査するか。
    """
    pending, seen = [node], set()
    while pending:
        obj = pending.pop()
        handle = om2.MObjectHandle(obj)
        if not handle.isValid() or not handle.isAlive():
            raise RuntimeError("Cannot edit an invalid node")
        key = handle.hashCode()
        if key in seen:
            continue
        seen.add(key)
        fn = om2.MFnDependencyNode(obj)
        if fn.isLocked or fn.isFromReferencedFile:
            raise RuntimeError("Node is locked or referenced: " + fn.name())
        if descendants and obj.hasFn(om2.MFn.kDagNode):
            dag = om2.MFnDagNode(obj)
            pending.extend(dag.child(i) for i in range(dag.childCount()))


def delete_node(node):
    """DAGメンバーを持つDGコンテナも扱えるmodifierでノードを削除する。

    Args:
        node (MObject): 削除するノード。削除後のMPlugを保持しないこと。
    """
    require_editable(node, descendants=True)
    modifier = om2.MDagModifier()
    # cmds.deleteと同じく、対象の空の親は残す（modifierの既定Trueとは異なる）。
    modifier.deleteNode(node, False)
    modifier.doIt()


def validate_deletion(nodes, safe=False):
    """混在した削除対象を更新前に検査し、後続の失敗による部分削除を避ける。

    Args:
        nodes (Iterable[Node]): 呼出し順の削除対象。
        safe (bool): 接続を持つ対象を残すか。
    """
    paths = []
    for node in nodes:
        if safe and node._has_delete_connections():
            continue
        path = node.getFullName()
        if any(path.startswith(parent + "|") for parent in paths):
            # 先行する親の削除で消える対象は、重ねて検証しない。
            continue
        require_editable(node.mnode(), descendants=True)
        paths.append(path)


def rename_node(node, name, ignore_shape=False):
    """ノードと、旧名の接頭辞が一致する直属Shapeを改名する。

    Args:
        node (MObject): 改名対象。
        name (str): Mayaが補正する新しい名前。
        ignore_shape (bool): 直属Shapeの連動改名を行わないか。

    Returns:
        str: Mayaが確定したノード名。
    """
    require_editable(node)
    fn = om2.MFnDependencyNode(node)
    old = fn.name()
    shapes = []
    if not ignore_shape and node.hasFn(om2.MFn.kTransform):
        dag = om2.MFnDagNode(node)
        for i in range(dag.childCount()):
            child = dag.child(i)
            child_fn = om2.MFnDependencyNode(child)
            # cmds.renameは別namespaceのShapeを連動改名しない。
            short = child_fn.name()
            if child.hasFn(om2.MFn.kShape) and short.startswith(old):
                require_editable(child)
                shapes.append((child, short[len(old):]))
    result = fn.setName(str(name))
    for shape, suffix in shapes:
        om2.MFnDependencyNode(shape).setName(result + suffix)
    return result


def create_node(node_type, flags):
    """Mayaの代表的なcreateNodeフラグをOpenMayaで実行する。

    Args:
        node_type (str): 作成するnodeType。
        flags (dict): 正規化済みname/parent/skipSelect/shared。

    Returns:
        MObject: 作成したノード。Shapeの暗黙の親ではなくShapeを返す。
    """
    from ..nodes.node import Node

    unsupported = set(flags) - {"name", "parent", "skipSelect", "shared"}
    if unsupported:
        raise NotImplementedError("Unsupported fast createNode flags: " + ", ".join(sorted(unsupported)))
    # 不明な型は作成前に拒否する。DAG作成の失敗時にDGへ切り替えても、
    # doIt前なので途中のノードをシーンへ残さない。
    om2.MNodeClass(node_type)
    parent = Node(flags["parent"]).mnode() if flags.get("parent") else om2.MObject.kNullObj
    if not parent.isNull():
        require_editable(parent)
    name = flags.get("name")
    if flags.get("shared") and name:
        selection = om2.MSelectionList()
        try:
            selection.add(name)
        except RuntimeError:
            pass
        else:
            if selection.length() == 1:
                return selection.getDependNode(0)
    modifier = om2.MDagModifier()
    try:
        obj = modifier.createNode(node_type, parent)
    except (RuntimeError, TypeError):
        if not parent.isNull():
            raise
        modifier = om2.MDGModifier()
        obj = modifier.createNode(node_type)
    modifier.doIt()
    if om2.MFnDependencyNode(obj).typeName != node_type and obj.hasFn(om2.MFn.kDagNode):
        # Shapeをワールド直下へ作る場合、MDagModifierは自動作成したTransformを返す。
        dag = om2.MFnDagNode(obj)
        obj = next(dag.child(i) for i in range(dag.childCount())
                   if om2.MFnDependencyNode(dag.child(i)).typeName == node_type)
    if name:
        om2.MFnDependencyNode(obj).setName(str(name))
    if not flags.get("skipSelect", False):
        selected = om2.MSelectionList()
        selected.add(obj)
        om2.MGlobal.setActiveSelectionList(selected, om2.MGlobal.kReplaceList)
    return obj
