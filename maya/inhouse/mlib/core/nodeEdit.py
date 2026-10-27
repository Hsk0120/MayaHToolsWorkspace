"""ノード作成・改名・削除の内部実装。

作成・改名はUndoへ登録しないOpenMaya実装。削除は通常(cmds)・fast(OpenMaya)の両方で使う
事前検査と、1回にまとめた削除を提供する。
"""

import itertools

import maya.api.OpenMaya as om2
import maya.cmds as cmds


def _dag_descendants(mobject):
    """DAGノードの全子孫を深さ優先で列挙する。DGノードは何も返さない。

    Args:
        mobject (om2.MObject): 起点のノード。自身は含めない。

    Yields:
        om2.MObject: 子、その子孫の順(各親の子は末尾から辿る)。
    """
    if not mobject.hasFn(om2.MFn.kDagNode):
        return
    pending = [mobject]
    while pending:
        dag = om2.MFnDagNode(pending.pop())
        for i in range(dag.childCount()):
            child = dag.child(i)
            yield child
            pending.append(child)


def require_editable(node, descendants=False):
    """構造変更前に参照・ロックされたノードを拒否する。

    Args:
        node (MObject): 対象ノード。
        descendants (bool): DAG子孫も検査するか。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: 無効なノード、またはロック・参照されたノードが対象か子孫に含まれる場合。
    """
    seen = set()
    # 子孫の列挙は遅延するため、対象自身の有効性を確かめてから子孫を辿る。
    for obj in itertools.chain((node,), _dag_descendants(node) if descendants else ()):
        handle = om2.MObjectHandle(obj)
        if not handle.isValid() or not handle.isAlive():
            raise RuntimeError("Cannot edit an invalid node")
        key = handle.hashCode()
        if key in seen:
            continue
        seen.add(key)
        fn = om2.MFnDependencyNode(obj)
        if fn.isLocked or fn.isFromReferencedFile:
            raise RuntimeError(f"Node is locked or referenced: {fn.name()}")


def check_deletion(nodes, fast=False):
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
    entries = []
    for index, node in enumerate(nodes):
        obj = node.mnode()
        handle = om2.MObjectHandle(obj) if obj is not None else None
        if handle is None or not handle.isValid() or not handle.isAlive():
            raise _deletion_error(index, "Cannot edit an invalid node" if fast else "Cannot delete an invalid node")
        entries.append((obj, node.getFullName()))
    # 対象ごとのDAG子孫をAPIで辿り、ロック・参照の子孫と、削除可否を問い合わせる名前を集める。
    descendants = []
    names = [path for _obj, path in entries]
    for obj, _path in entries:
        found = list(_dag_descendants(obj))
        descendants.append(found)
        names += [om2.MDagPath.getAPathTo(child).fullPathName() for child in found]
    # cmds.ls(undeletable=True) が、既定・共有ノード等のMayaが削除を拒否するノードを返す
    # (ロックされたノードも含む)。全対象と子孫を1回で問い合わせる。
    blocked = set(cmds.ls(names, long=True, undeletable=True) or [])
    offset = len(entries)
    for index, (obj, path) in enumerate(entries):
        fn = om2.MFnDependencyNode(obj)
        if fn.isLocked or fn.isFromReferencedFile:
            if fast:
                raise _deletion_error(index, f"Node is locked or referenced: {fn.name()}")
            if fn.isLocked:
                raise _deletion_error(index, f"Cannot delete locked node '{_display_name(path)}'.")
            raise _deletion_error(
                index, f"Cannot delete '{_display_name(path)}' as it has locked or read-only children.")
        if fn.isDefaultNode or path in blocked:
            raise _deletion_error(index, f"Non-deletable node '{_display_name(path)}' cannot be deleted.")
        child_names = names[offset:offset + len(descendants[index])]
        offset += len(descendants[index])
        for child, child_path in zip(descendants[index], child_names):
            child_fn = om2.MFnDependencyNode(child)
            if child_fn.isLocked or child_fn.isFromReferencedFile:
                if fast:
                    raise _deletion_error(index, f"Node is locked or referenced: {child_fn.name()}")
                raise _deletion_error(
                    index, f"Cannot delete '{_display_name(path)}' as it has locked or read-only children.")
            if child_fn.isDefaultNode or child_path in blocked:
                raise _deletion_error(index, f"Non-deletable node '{_display_name(child_path)}' cannot be deleted.")
    return entries


def delete_nodes(nodes, fast=False, checked=None):
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
    entries = check_deletion(nodes, fast=fast) if checked is None else checked
    if not fast:
        cmds.delete([path for _obj, path in entries])
        return
    modifier = om2.MDagModifier()
    queued = {}
    for obj, _path in entries:
        handle = om2.MObjectHandle(obj)
        # DAG の deleteNode はその場で削除を進め、子・連鎖して消えるノードのハンドルは無効になる。
        # 消えた対象や重複を積むと doIt が失敗するため飛ばす(ハッシュの衝突は MObject の比較で区別する)。
        same = queued.setdefault(handle.hashCode(), [])
        if not handle.isValid() or any(obj == other for other in same):
            continue
        same.append(obj)
        # cmds.deleteと同じく、対象の空の親は残す（modifierの既定Trueとは異なる）。
        modifier.deleteNode(obj, False)
    modifier.doIt()


def _deletion_error(index, message):
    """対象の番号を持つ削除の RuntimeError を作る。

    Args:
        index (int): 原因の対象の番号。
        message (str): 例外の文言。

    Returns:
        RuntimeError: ``index`` 属性を持つ例外。
    """
    error = RuntimeError(message)
    error.index = index
    return error


def _display_name(path):
    """例外の文言に使う、Maya の表示と同じ最短の一意な名前を返す。

    Args:
        path (str): 完全パスまたは名前。

    Returns:
        str: DAG は partialPathName、DG はノード名。
    """
    selection = om2.MSelectionList()
    selection.add(path)
    try:
        return selection.getDagPath(0).partialPathName()
    except TypeError:
        return om2.MFnDependencyNode(selection.getDependNode(0)).name()


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
            shared=Trueで同名・同型のノードが一意に存在する場合はそのノード(cmdsはルート名前空間の
            名前だけ再利用するが、ここでは名前空間付きの名前でも既存ノードを返す近似)。

    Raises:
        RuntimeError: Mayaが認識しないnodeType、ロック・参照された親、またはshared=Trueで
            同名ノードの型が違う場合(cmdsは新しい連番名で作るが、fastは型を見て拒否する)。
        NotImplementedError: name/parent/skipSelect/shared以外のフラグを指定した場合。
    """
    from ..nodes.node import Node

    unsupported = set(flags) - {"name", "parent", "skipSelect", "shared"}
    if unsupported:
        raise NotImplementedError(f"fast createNode does not support flags: {', '.join(sorted(unsupported))}")
    # MNodeClassは未知の型名でも例外にならず typeId が 0 になるため、値で判定して作成前に拒否する
    # (呼出し側の _node_type_exists と二重だが安価)。DAG作成の失敗時にDGへ切り替えても、
    # doIt前なので途中のノードをシーンへ残さない。
    if om2.MNodeClass(node_type).typeId.id() == 0:
        raise RuntimeError(f"Unknown Maya nodeType: {node_type}")
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
                existing = selection.getDependNode(0)
                existing_type = om2.MFnDependencyNode(existing).typeName
                if existing_type != node_type:
                    raise RuntimeError(
                        f"shared=True: existing node {name!r} has type {existing_type!r}, not {node_type!r}")
                return existing
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
