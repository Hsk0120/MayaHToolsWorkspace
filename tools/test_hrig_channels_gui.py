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
        import hlib
        common_owner = hlib.events.ScriptJobs()
        external_owner = hlib.events.ScriptJobs()
        probe = hlib.createNode('transform', name='eventProbe', skipSelect=True)
        probe.add_attribute('setting', attribute_type='long', default_value=0)
        observed = []
        external = external_owner.add('external', event='SelectionChanged', callback=lambda: None)
        try:
            first = common_owner.add('setting', attribute=probe.plug('setting'),
                                     callback=lambda: observed.append(1), kill_with_scene=True)
            check(first is common_owner.add('setting', attribute=probe.plug('setting'),
                                            callback=lambda: None), 'Common jobs deduplicate by key')
            probe.plug('setting').set(1)
            yield
            check(len(observed) == 1, 'Common attribute job executes on GUI idle')
            probe.rename('renamedEventProbe')
            probe.plug('setting').set(2)
            yield
            check(len(observed) == 2, 'Common attribute job survives rename')
            import importlib
            importlib.reload(hlib.ui)
            check(first.exists(), 'Common job ownership survives library reload')
            common_owner.stop()
            probe.plug('setting').set(3)
            yield
            check(len(observed) == 2 and external.exists(), 'Stopping owner preserves unrelated jobs')
            common_owner.add('setting', attribute=probe.plug('setting'),
                             callback=lambda: None, kill_with_scene=True)
            cmds.file(new=True, force=True)
            yield
            check(not common_owner.exists() and external.exists(), 'Scene clear ends only scene jobs')
        finally:
            common_owner.stop()
            external_owner.stop()
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
        target, pole = rig.controls()['target'], rig.controls()['pole']
        target_pose = cmds.xform(target, q=True, ws=True, matrix=True)
        cmds.flushUndo()
        cmds.setAttr(target+'.space', 1)
        yield
        check(rig.space_switch('ik').current() == 'world', 'IK channel switches to World')
        check(same([target_pose], [cmds.xform(target,q=True,ws=True,matrix=True)]), 'World switch preserves pose')
        cmds.undo()
        yield
        check(rig.space_switch('ik').current() == 'local' and cmds.getAttr(target+'.space') == 0, 'Space switch single Undo')
        cmds.redo()
        yield
        check(rig.space_switch('ik').current() == 'world' and cmds.getAttr(target+'.space') == 1, 'Space switch single Redo')
        cmds.setAttr(pole+'.space', 2)
        yield
        check(rig.space_switch('pole').current() == 'foot', 'Pole channel switches to Foot')
        pole_before = cmds.xform(pole,q=True,ws=True,t=True)
        cmds.setAttr(target+'.ty', 1)
        yield
        pole_after = cmds.xform(pole,q=True,ws=True,t=True)
        check(abs(pole_after[1]-pole_before[1]-1) < 0.001, 'Pole follows foot')
        cmds.setAttr(target+'.ty', 0)
        yield
        check(cmds.getAttr(rig._member('channel_space')+'.active'), 'Space layer shown active')
        twist = rig._member('channel_twist')
        check(len(rig.twist_joints()) == 6, 'Demo has three twist joints per segment')
        check(cmds.getAttr(twist+'.active'), 'Twist layer active')
        cmds.setAttr(twist+'.enabled', False)
        yield
        check(all(not cmds.connectionInfo(j+'.offsetParentMatrix',isDestination=True) for j in rig.twist_joints()), 'Twist channel disconnects evaluation')
        cmds.undo()
        yield
        check(cmds.getAttr(twist+'.enabled') and all(cmds.connectionInfo(j+'.offsetParentMatrix',isDestination=True) for j in rig.twist_joints()), 'Twist layer single Undo')
        bend = rig._member('channel_bend')
        half, inner, outer = rig.bend_joints()
        check(cmds.getAttr(bend+'.active'), 'Bend layer active')
        cmds.setAttr(bend+'.enabled', False)
        yield
        check(not cmds.connectionInfo(half+'.offsetParentMatrix',isDestination=True) and not cmds.connectionInfo(inner+'.ty',isDestination=True), 'Bend channel disconnects outputs')
        cmds.undo()
        yield
        check(cmds.getAttr(bend+'.enabled') and cmds.connectionInfo(half+'.offsetParentMatrix',isDestination=True), 'Bend single Undo reconnects')
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
        check(not cmds.getAttr(twist+'.active'), 'Low LOD disables twist')
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
        check(len(rig.bend_joints()) == 3 and cmds.getAttr(rig._member('channel_bend')+'.active'), 'Bend survives scene reload')
        check(len(rig.twist_joints()) == 6 and cmds.getAttr(rig._member('channel_twist')+'.active'), 'Twist survives scene reload')
        check(rig.space_switch('ik').current() == 'world' and rig.space_switch('pole').current() == 'foot', 'Saved spaces restored')
        cmds.setAttr(rig.controls()['target']+'.space',0)
        yield
        check(rig.space_switch('ik').current() == 'local','Saved scene reattaches space jobs')
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
