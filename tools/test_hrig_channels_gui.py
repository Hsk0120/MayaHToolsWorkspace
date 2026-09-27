"""隔離したMaya GUIでチャンネル操作とイベント処理を検証する。"""

import json
from pathlib import Path
import traceback


def main(output_dir=None, finished=None):
    """専用GUIで実行する。ユーザーの作業中シーンへ送信しない。

    Args:
        output_dir (str): 結果と確認画像の保存先。
        finished (Callable): ランナーへ終了を通知する関数。
    """
    from maya import cmds, OpenMayaUI, utils
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
    from hrig.examples.limb_demo import build_demo
    from hrig.limb import LimbRig
    from hrig import channel_controls
    output = Path(output_dir)
    result = {'status': 'running', 'checks': []}
    diagnostic_timer = QtCore.QTimer(QtWidgets.QApplication.instance())

    def diagnose():
        """テストが待機した場合にモーダルウィンドウの状態を残す。"""
        widgets = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()]
        (output/'windows.json').write_text(json.dumps([
            {'title':w.windowTitle(),'class':w.metaObject().className(),'modal':w.isModal()}
            for w in widgets],indent=2),encoding='utf-8')

    diagnostic_timer.timeout.connect(diagnose)
    diagnostic_timer.start(5000)

    def check(value, label):
        """検証結果を記録する。"""
        if not value:
            raise AssertionError(label)
        result['checks'].append(label)
        (output/'progress.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

    def pose(rig):
        """関節のワールド行列を取得する。"""
        return [cmds.xform(j, q=True, ws=True, matrix=True) for j in rig.joints()[:3]]

    def same(a, b):
        """数値誤差を許容して姿勢を比較する。"""
        return all(abs(x-y) < 0.003 for ma, mb in zip(a,b) for x,y in zip(ma,mb))

    def steps():
        """各操作後にGUIのidleへ制御を返す。"""
        check(not cmds.about(batch=True), 'Maya GUI')
        rig = build_demo()['rig']
        module = rig._member('channelModule')
        check(cmds.getAttr(module+'.mode') == 1, 'Initial IK state synchronized')
        check(not cmds.getAttr(module+'.mode',keyable=True), 'Mode is configuration, not keyable')
        if cmds.workspaceControl('ChannelBoxLayerEditor',exists=True):
            cmds.workspaceControl('ChannelBoxLayerEditor',edit=True,visible=True)
        cmds.select(module)
        yield
        check('mode' in (cmds.listAttr(module,channelBox=True) or []), 'Mode exposed to channel box')
        result['channel_box_objects'] = cmds.channelBox('mainChannelBox',q=True,mainObjectList=True)
        before = pose(rig)
        cmds.flushUndo()
        cmds.setAttr(module+'.mode', 0)
        yield
        check(rig.mode() == 'fk' and same(before, pose(rig)), 'Channel edit matches IK to FK')
        check(cmds.getAttr(rig._member('softGraph')+'.nodeState') == 2, 'FK blocks Soft IK')
        cmds.undo()
        yield
        check(rig.mode() == 'ik' and cmds.getAttr(module+'.mode') == 1 and same(before,pose(rig)), 'Single Undo restores mode and pose')
        cmds.redo()
        yield
        check(rig.mode() == 'fk' and cmds.getAttr(module+'.mode') == 0 and same(before,pose(rig)), 'Single Redo restores mode and pose')
        cmds.setAttr(module+'.mode', 1)
        yield
        check(rig.mode() == 'ik' and same(before,pose(rig)), 'FK to IK match')
        soft = rig._member('channel_soft')
        cmds.setAttr(soft+'.enabled', False)
        yield
        check(not rig.layer_enabled('soft') and not cmds.getAttr(soft+'.active'), 'Soft layer disabled')
        check(cmds.getAttr(rig._member('softGraph')+'.nodeState') == 2, 'Disabled layer evaluation blocked')
        cmds.undo()
        yield
        check(rig.layer_enabled('soft') and cmds.getAttr(soft+'.enabled'), 'Layer toggle Undo')
        cmds.setAttr(module+'.lod', 0)
        yield
        check(rig.lod() == 0 and not cmds.getAttr(soft+'.active') and cmds.getAttr(soft+'.enabled'), 'LOD distinguishes Enabled and Active')
        cmds.setAttr(module+'.lod', 1)
        yield
        check(cmds.getAttr(soft+'.active'), 'Full LOD restores active layer')
        cmds.setAttr(rig._member('channel_helper')+'.enabled',False)
        yield
        check(not cmds.connectionInfo(rig._member('helper')+'.rotate',isDestination=True), 'Helper disabled connection')
        cmds.setAttr(rig._member('channel_foot')+'.enabled',False)
        yield
        check(not cmds.getAttr(rig._member('channel_foot')+'.active'), 'Reverse foot disabled')
        scene = str(output/'channels.ma')
        cmds.file(rename=scene);cmds.file(save=True,type='mayaAscii')
        cmds.file(new=True,force=True)
        cmds.file(scene,open=True,force=True)
        yield
        rig = LimbRig('rig')
        module = rig._member('channelModule')
        check(not rig.layer_enabled('helper'), 'Saved layer preference restored')
        cmds.setAttr(module+'.mode',0)
        yield
        check(rig.mode() == 'fk', 'Saved scene automatically reattaches jobs')
        cmds.rename('rig','renamedRig')
        rig = LimbRig('renamedRig')
        module = rig._member('channelModule')
        cmds.setAttr(module+'.mode',1)
        yield
        check(rig.mode() == 'ik','Rename preserves controls')
        count = len(cmds.scriptJob(listJobs=True))
        channel_controls.install();channel_controls.install()
        check(len(cmds.scriptJob(listJobs=True)) == count,'No duplicate jobs')
        rig.set_lod(0)
        cmds.setAttr(rig.controls()['target']+'.tx',2)
        rig.match_fk();rig.set_mode('fk');rig.set_lod(1)
        cmds.setAttr(module+'.mode',1)
        yield
        check(rig.mode() == 'fk' and cmds.getAttr(module+'.mode') == 0,'Invalid Soft IK match rejects and restores request')
        cmds.setAttr(module+'.matchOnSwitch',False)
        cmds.setAttr(module+'.mode',1)
        yield
        check(rig.mode() == 'ik','Explicit switch without matching')
        editors = [cmds.outlinerPanel(panel,q=True,outlinerEditor=True)
                   for panel in cmds.getPanel(type='outlinerPanel')]
        cmds.select(rig.root.full_name())
        yield
        for editor in editors:
            cmds.outlinerEditor(editor,e=True,expandAllSelectedItems=True)
        cmds.select([rig._member(role) for role in ('geometryGroup','jointGroup','controlGroup','setupGroup')])
        yield
        for editor in editors:
            cmds.outlinerEditor(editor,e=True,expandAllSelectedItems=False)
        cmds.select(module)
        # 標準Mayaウィンドウを撮影する。独自の操作UIは作らない。
        yield
        widget = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()),QtWidgets.QWidget)
        widget.grab().save(str(output/'channels.png'))
        cmds.select(rig._member('channel_soft'))
        yield
        cmds.channelBox('mainChannelBox',e=True,select=rig._member('channel_soft')+'.enabled')
        check('enabled' in (cmds.channelBox('mainChannelBox',q=True,selectedMainAttributes=True) or []), 'Enabled visible and selectable in standard channel box')
        widget.grab().save(str(output/'layer.png'))

    iterator = steps()

    def next_idle():
        """マウス入力のない自動テストでもMayaのidleキューを処理する。"""
        utils.processIdleEvents()
        advance()

    def advance():
        """idle処理を挟んで次の検証へ進める。"""
        try:
            next(iterator)
            QtCore.QTimer.singleShot(350, next_idle)
            return
        except StopIteration:
            result['status'] = 'passed'
        except Exception:
            result.update(status='failed',error=traceback.format_exc())
        widget = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()),QtWidgets.QWidget)
        widget.grab().save(str(output/'final.png'))
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        diagnostic_timer.stop()
        def late_edit():
            """終了予約後のシーン変更でも保存確認が出ないことを検証する。"""
            cmds.createNode('transform',name='hrigShutdownDirtyProbe',skipSelect=True)
            (output/'late-dirty.json').write_text(json.dumps({'modified':cmds.file(q=True,modified=True)}),encoding='utf-8')
        cmds.evalDeferred(late_edit)
        finished(result)

    # 起動時のQtネストイベントループではMayaのidleがまだ動かない。
    # GUIの初回idle後にシーン構築を開始する。
    cmds.evalDeferred(advance, lowestPriority=True)
