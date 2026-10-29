"""専用Maya GUIでFBXの実読込・設定復元とQPE操作を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
sys.path.insert(0, str(ROOT / 'tools'))


def main(output_dir, finished):
    """使い捨てのシーンでアニメーション更新と通常オープンを録画する。"""
    from maya import cmds, mel
    from qpeQt import QtCore, QtGui, QtWidgets, QtTest
    from qpe_ui_maya import pause, waitFor, selectFile
    import qpeHost
    from qpeFbx import openFbx, FbxOptions

    output = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(output / 'qpe-settings.json')
    data = output / 'assets'
    data.mkdir()
    frames = output / 'frames'
    frames.mkdir()
    checks = []
    captured = []
    timer = None
    widget = None

    def check(name, condition):
        """条件と結果を保存し、不一致ならそこで停止する。"""
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        cmds.loadPlugin('fbxmaya', quiet=True)
        cmds.file(new=True, force=True)
        cmds.createNode('joint', name='motionJoint')
        cmds.setAttr('motionJoint.ty', 7)
        cmds.setKeyframe('motionJoint', attribute='translateX', time=1, value=2)
        cmds.setKeyframe('motionJoint', attribute='translateX', time=10, value=12)
        cmds.createNode('transform', name='extraFromFbx')
        cmds.createNode('transform', name='unkeyedTransform')
        cmds.setAttr('unkeyedTransform.ty', 7)
        path = data / 'animation test.fbx'
        mel.eval('FBXPushSettings;')
        try:
            mel.eval('FBXExportAnimationOnly -v false;')
            mel.eval('FBXExport -f {};'.format(json.dumps(path.as_posix())))
        finally:
            mel.eval('FBXPopSettings;')
        check('export fixture', path.is_file())
        widget = qpeHost.show(str(data))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1300, resizeHeight=900)
        widget.inspectorButton.setChecked(True)
        caption = QtWidgets.QLabel(widget)
        caption.setStyleSheet('background:#17363b;color:white;padding:8px;font-size:16px;')
        widget.layout().insertWidget(0, caption)

        def capture():
            """操作対象の実ウィジェットだけを撮影する。"""
            pixmap = QtGui.QPixmap(1400, 1000)
            pixmap.fill(QtGui.QColor('#202020'))
            painter = QtGui.QPainter(pixmap)
            painter.drawPixmap(0, 0, widget.grab())
            painter.end()
            pixmap.save(str(frames / ('%05d.png' % len(captured))))
            captured.append(len(captured))

        timer = QtCore.QTimer(widget)
        timer.timeout.connect(capture)
        timer.start(200)

        def stage(text):
            """Qt操作とシーンの結果を字幕で区別する。"""
            caption.setText('Maya {} / Qt GUI test / {}'.format(cmds.about(version=True), text))
            pause(900)

        def working_scene():
            """同名ジョイントと更新対象外ノードを持つ作業シーンを作る。"""
            cmds.file(new=True, force=True)
            cmds.createNode('joint', name='motionJoint')
            cmds.setAttr('motionJoint.ty', 99)
            cmds.setKeyframe('motionJoint', attribute='translateX', time=1, value=-5)
            cmds.setKeyframe('motionJoint', attribute='translateX', time=10, value=-5)
            cmds.createNode('transform', name='keepInScene')
            cmds.createNode('transform', name='unkeyedTransform')
            cmds.setAttr('unkeyedTransform.ty', 99)
            cmds.file(rename=str(data / 'working.mb'))
            cmds.file(save=True, type='mayaBinary', force=True)

        def activate():
            """一覧上の実ダブルクリックを送り、ホストの読込入口を通す。"""
            widget.navigate(str(data))
            selectFile(widget, path)
            pause(100)
            index = widget.files.currentIndex()
            QtTest.QTest.mouseDClick(widget.files.viewport(), QtCore.Qt.LeftButton,
                                    QtCore.Qt.NoModifier, widget.files.visualRect(index).center())
            pause(600)

        def choose(mode):
            """右サイドバーでOpen時の挙動を変更する。"""
            widget.fbxOptions.mode.setCurrentIndex(widget.fbxOptions.mode.findData(mode))
            pause(150)

        # FBXの全体設定を変更する他ツールへ影響しないことを検証する。
        mel.eval('FBXImportMode -v "merge";')
        mel.eval('FBXImportFillTimeline -v true;')
        mel.eval('FBXProperty "Import|IncludeGrp|Animation" -v false;')
        original = [mel.eval(command) for command in (
            'FBXImportMode -q;', 'FBXImportFillTimeline -q;',
            'FBXProperty "Import|IncludeGrp|Animation" -q;')]

        working_scene()
        widget.navigate(str(data))
        selectFile(widget, path)
        waitFor(lambda: not widget.fbxModeButton.isHidden())
        check('FBX sidebar visible', not widget.fbxOptions.isHidden())
        check('default open scene', widget.fbxOptions.mode.currentData() == 'open')
        choose('exmerge')
        restored = FbxOptions()
        check('mode persisted', restored.mode.currentData() == 'exmerge')
        restored.deleteLater()
        check('toolbar follows mode', 'Update animation only' in widget.fbxModeButton.text())
        stage('Update animation only: existing joint -5 -> 2 / 12')
        activate()
        check('existing scene preserved', cmds.objExists('keepInScene'))
        check('unmatched FBX node ignored', not cmds.objExists('extraFromFbx'))
        check('scene name preserved', Path(cmds.file(query=True, sceneName=True)).name == 'working.mb')
        check('animation updated', cmds.keyframe('motionJoint.tx', query=True, valueChange=True) == [2.0, 12.0])
        check('modified remains true', cmds.file(query=True, modified=True))
        check('settings restored', original == [mel.eval(command) for command in (
            'FBXImportMode -q;', 'FBXImportFillTimeline -q;',
            'FBXProperty "Import|IncludeGrp|Animation" -q;')])
        stage('PASS: original scene retained, animation updated, extra object ignored')

        choose('open')
        stage('Open as scene: cancel preserves current scene')
        answer = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *args, **kwargs: QtWidgets.QMessageBox.Cancel
        try:
            widget.requestFiles('open', [str(path)])
        finally:
            QtWidgets.QMessageBox.question = answer
        check('cancel open preserves scene', cmds.objExists('keepInScene'))
        cmds.file(modified=False)  # 専用シーンだけを、破棄確認なしで切り替える。
        stage('Open as scene: replace scene with FBX')
        activate()
        check('open replaced scene', not cmds.objExists('keepInScene'))
        check('open loaded FBX content', cmds.objExists('extraFromFbx') and cmds.objExists('motionJoint'))
        check('open loaded animation', cmds.keyframe('motionJoint.tx', query=True, valueChange=True) == [2.0, 12.0])
        stage('PASS: FBX scene opened in this Maya')

        for mode in ('add', 'merge', 'exmergekeyedxforms'):
            working_scene()
            choose(mode)
            stage('Mode: ' + widget.fbxOptions.mode.currentText())
            widget.requestFiles('open', [str(path)])
            check(mode + ' keeps scene', cmds.objExists('keepInScene'))
            check(mode + ' node inclusion', cmds.objExists('extraFromFbx') == (mode != 'exmergekeyedxforms'))
            if mode != 'add':
                check(mode + ' animation', cmds.keyframe('motionJoint.tx', query=True, valueChange=True) == [2.0, 12.0])
            if mode == 'exmergekeyedxforms':
                check('keyed mode preserves unkeyed transform', cmds.getAttr('unkeyedTransform.ty') == 99)

        # 読込失敗後にも設定を復元する。FBXImport部分だけ例外を注入する。
        real_eval = mel.eval

        def failing_eval(command):
            """FBX読込の例外経路を設定保存/復元とは独立に検査する。"""
            if command.startswith('FBXImport -f '):
                raise RuntimeError('Injected FBX read error')
            return real_eval(command)

        mel.eval = failing_eval
        try:
            try:
                openFbx(str(path), {'mode': 'exmerge', 'timeline': False})
            except RuntimeError as error:
                check('import failure propagated', 'Injected' in str(error))
            else:
                check('import failure propagated', False)
        finally:
            mel.eval = real_eval
        check('settings restored after failure', original == [mel.eval(command) for command in (
            'FBXImportMode -q;', 'FBXImportFillTimeline -q;',
            'FBXProperty "Import|IncludeGrp|Animation" -q;')])
        working_scene()
        cmds.playbackOptions(minTime=-10, maxTime=80, animationStartTime=-10, animationEndTime=80)
        openFbx(str(path), {'mode': 'exmerge', 'timeline': False})
        check('keep playback range', cmds.playbackOptions(query=True, minTime=True) == -10
              and cmds.playbackOptions(query=True, maxTime=True) == 80)
        openFbx(str(path), {'mode': 'exmerge', 'timeline': True})
        check('update playback range', cmds.playbackOptions(query=True, minTime=True) != -10
              or cmds.playbackOptions(query=True, maxTime=True) != 80)
        # FBX以外の関連付けと.ma/.mbの既存入口を変えない。
        from unittest.mock import patch
        text_path = data / 'notes.txt'
        text_path.write_text('test file', encoding='utf-8')
        with patch.object(widget, 'openAssociatedFile') as associated:
            widget.requestFiles('open', [str(text_path)])
            check('other files still associated', associated.call_count == 1)
        with patch.object(widget, 'openAssociatedFile') as associated:
            choose('exmerge')
            widget.requestFiles('open', [str(path)])
            check('FBX never associated in Maya', associated.call_count == 0)
        cmds.file(modified=False)
        widget.requestFiles('open', [str(data / 'working.mb')])
        check('mb still opens in Maya', cmds.objExists('keepInScene')
              and cmds.keyframe('motionJoint.tx', query=True, valueChange=True) == [-5.0, -5.0])
        choose('exmerge')
        selectFile(widget, path)
        stage('PASS: modes can be switched from sidebar or top bar')
        widget.grab().save(str(output / 'fbx-settings.png'))
        if os.environ.get('QPE_FBX_NATIVE') == '1':
            stage('Native Windows input: mode menu and double-click')
            (output / 'native-ready.txt').write_text('ready', encoding='utf-8')
            import time
            deadline = time.monotonic() + 300
            while not (output / 'native-finished.txt').exists() and time.monotonic() < deadline:
                state = {'mode': widget.fbxOptions.mode.currentData(),
                         'scene': cmds.file(query=True, sceneName=True),
                         'keepInScene': cmds.objExists('keepInScene'),
                         'extraFromFbx': cmds.objExists('extraFromFbx'),
                         'keys': cmds.keyframe('motionJoint.tx', query=True, valueChange=True)}
                (output / 'native-state.json').write_text(json.dumps(state), encoding='utf-8')
                pause(200)
        result = {'status': 'passed', 'checks': checks, 'maya': cmds.about(version=True),
                  'input': 'Qt QTest / API; not native OS input', 'frames': len(captured)}
    except Exception:
        result = {'status': 'failed', 'checks': checks, 'traceback': traceback.format_exc()}
    finally:
        if timer:
            timer.stop()
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    finished(result)
