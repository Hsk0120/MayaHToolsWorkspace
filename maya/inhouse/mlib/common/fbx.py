"""Maya 2022以降のFBX読み書き。import時にfbxmayaをロードしない。"""

from pathlib import Path

import maya.cmds as cmds
import maya.mel as mel

from .plugin import Plugin


def _path(value, existing=False):
    """FBXパスを検証し、絶対パスへ正規化する。

    Args:
        value: 変換・設定する入力値。
        existing: 対象ファイルが存在することを要求するか。
    """
    result = Path(value).expanduser().resolve()
    if result.suffix.lower() != '.fbx':
        raise ValueError('Expected an .fbx path')
    if existing and not result.is_file():
        raise FileNotFoundError(str(result))
    if not existing and not result.parent.is_dir():
        raise FileNotFoundError(str(result.parent))
    return result


def importFbx(path, namespace=None):
    """FBXを現在のシーンへ追加する。既存シーンの置換は行わない。

    Args:
        path (str | Path): 存在するFBXファイル。
        namespace (str | None): 指定時に使用する名前空間。
    Returns:
        tuple[str]: 読み込み前後のノード参照差分から求めた新規ノード名。
    Note:
        インポートはUndoで完全に復元できると保証しない。
        ImportModeだけaddへ変更して復元する。他の設定は現在値を使用する。
    """
    target = _path(path, existing=True)
    Plugin('fbxmaya').ensureLoaded()
    kwargs = {'namespace': namespace} if namespace is not None else {}
    # FBXは既存ノードのUUIDも変更することがあるため、MObjectの同一性で判定する。
    from maya.api import OpenMaya as om
    before = {}
    iterator = om.MItDependencyNodes()
    while not iterator.isDone():
        handle = om.MObjectHandle(iterator.thisNode())
        before.setdefault(handle.hashCode(), []).append(handle)
        iterator.next()
    previous_mode = mel.eval('FBXImportMode -q;')
    try:
        mel.eval('FBXImportMode -v "add";')
        cmds.file(str(target), i=True, type='FBX', **kwargs)
    finally:
        import json
        mel.eval('FBXImportMode -v {};'.format(json.dumps(previous_mode)))
    result = []
    iterator = om.MItDependencyNodes()
    while not iterator.isDone():
        obj = iterator.thisNode()
        key = om.MObjectHandle(obj).hashCode()
        if not any(handle.isValid() and handle.object() == obj for handle in before.get(key, ())):
            if obj.hasFn(om.MFn.kDagNode):
                result.append(om.MFnDagNode(obj).fullPathName())
            else:
                result.append(om.MFnDependencyNode(obj).name())
        iterator.next()
    return tuple(result)


def exportFbx(path, selection=None, overwrite=False, animation=True):
    """シーン全体または明示したノードをFBXへ書き出す。

    Args:
        path (str | Path): 出力先。
        selection (iterable | None): 指定時はこのノード群だけを書き出す。
        overwrite (bool): 既存ファイルの上書きを許可する。
        animation (bool): アニメーションを含める。
    Returns:
        Path: 出力した絶対パス。
    Note:
        FBXのAnimation設定と選択を復元する。他のFBX設定は現在値を使う。
    """
    from ..nodes.node import Node as _InputNode
    target = _path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(str(target))
    nodes = None
    if selection is not None:
        if isinstance(selection, str):
            raise TypeError('selection must be a sequence, not a string')
        nodes = [_InputNode._input_name(node) for node in selection]
        if not nodes:
            raise ValueError('selection must not be empty')
    Plugin('fbxmaya').ensureLoaded()
    saved_selection = cmds.ls(selection=True, long=True) or []
    saved_animation = mel.eval('FBXProperty Export|IncludeGrp|Animation -q;')
    try:
        mel.eval('FBXProperty Export|IncludeGrp|Animation -v {};'.format('true' if animation else 'false'))
        if nodes is not None:
            cmds.select(nodes, replace=True)
        flag = 'exportSelected' if nodes is not None else 'exportAll'
        cmds.file(str(target), type='FBX export', force=overwrite, **{flag: True})
    finally:
        mel.eval('FBXProperty Export|IncludeGrp|Animation -v {};'.format('true' if saved_animation else 'false'))
        cmds.select(saved_selection, replace=True) if saved_selection else cmds.select(clear=True)
    return target


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('export_fbx', 'import_fbx'):
    globals().pop(_obsolete_name, None)
