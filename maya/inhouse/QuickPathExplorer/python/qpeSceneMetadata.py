"""Mayaの保存済みシーンに、明示操作で確認用の付随情報を作る。"""
import json
import os
from pathlib import Path
from qpeQt import QtWidgets


def saveCurrent(parent):
    """現在シーンの参照・テクスチャ・表示画像を付随ファイルへ保存する。

    Args:
        parent (QWidget): 上書き確認の親。

    Returns:
        str: 保存したメタデータのパス。
    """
    from maya import cmds
    scene = cmds.file(query=True, sceneName=True)
    if not scene or not os.path.isfile(scene):
        raise ValueError('Save the scene first.')
    if cmds.file(query=True, modified=True):
        raise ValueError('Save scene changes before saving its information and thumbnail.')
    path = Path(scene)
    metadata = path.with_suffix(path.suffix + '.qpe.json')
    thumbnail = path.with_suffix(path.suffix + '.qpe.png')
    if metadata.exists() or thumbnail.exists():
        if QtWidgets.QMessageBox.question(parent, 'Update scene information and thumbnail',
                'Replace QPE metadata / thumbnail for\n' + scene,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
            return 'Cancelled'
    references = cmds.file(query=True, reference=True) or []
    textures = []
    for node in cmds.ls(type='file') or []:
        textures.append(cmds.getAttr(node + '.fileTextureName') or '')
    values = dict(scene=scene, maya=cmds.about(version=True), project=cmds.workspace(query=True, rootDirectory=True),
                  references=references, textures=textures, sceneModified=path.stat().st_mtime)
    metadata.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf8')
    # playblastは現在のmodelPanelを使用し、フレームもシーンも変更しない。
    panel = cmds.getPanel(withFocus=True)
    if not panel or cmds.getPanel(typeOf=panel) != 'modelPanel':
        visible = cmds.getPanel(visiblePanels=True) or []
        panel = next((p for p in cmds.getPanel(type='modelPanel') if p in visible), None)
    if panel:
        cmds.playblast(completeFilename=str(thumbnail), format='image', compression='png',
                       frame=cmds.currentTime(query=True), viewer=False, showOrnaments=False,
                       offScreen=True, widthHeight=(640, 360), percent=100, forceOverwrite=True,
                       editorPanelName=panel)
    return str(metadata)
