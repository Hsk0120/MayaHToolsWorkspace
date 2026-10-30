"""専用MayaでQPEの視覚設計、狭幅、倍率と操作対象を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """ホスト設定を保持し、実ウィジェットの描画と操作結果を記録する。

    Args:
        output_dir (Path): 専用環境内の証拠保存先。
        finished (callable): 専用Maya実行器への終了通知。
    """
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'tools'))
    sys.path.insert(0, str(root / 'maya/inhouse/QuickPathExplorer/python'))
    from maya import cmds
    from qpeQt import QtCore, QtGui, QtWidgets, QtTest
    from qpe_ui_maya import pause, waitFor, selectFile
    from qpe_record_full import Recorder
    import qpeHost

    out = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    project = out / 'Project'
    work = project / 'Shots/seq010/shot020/Animation/Work'
    for path in (work, project / 'Assets/Characters', project / 'Textures', project / 'Exports'):
        path.mkdir(parents=True, exist_ok=True)
    for index in range(18):
        (work / ('shot020_animation_v%03d.ma' % index)).write_text('// display fixture', encoding='utf-8')
    fbx = work / 'walk_cycle.fbx'
    fbx.write_text('; display fixture; never import', encoding='utf-8')
    result = {'status': 'error', 'checks': [], 'input': 'Maya GUI / QtTest and Qt API, not OS input'}
    recorder = None
    try:
        palette = QtGui.QPalette(QtWidgets.QApplication.instance().palette())
        e = qpeHost.show(str(work))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1280, resizeHeight=860)
        e.setBrowseRoot(str(project))
        e.navigate(str(work))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 19)
        e.sidebarButton.setChecked(True)
        e.inspectorButton.setChecked(True)
        pause(400)
        selectFile(e, work / 'shot020_animation_v003.ma')
        e.outer.setSizes([180, 770, 300])
        if os.environ.get('QPE_FFMPEG'):
            os.environ['QPE_REVIEW_CHAPTER'] = 'visual-' + cmds.about(version=True)
            recorder = Recorder(e, out)

        def stage(code, title):
            """実際のQt描画を動画と静止画で保存する。"""
            pause(250)
            if recorder:
                recorder.step(code, title)
                recorder.hold()
            e.grab().save(str(out / (code + '-ui.png')))

        stage('01-open', 'Maya / compact layout / Open Scene')
        assert e.actionButtons['open'].text() == 'Open Scene'
        assert not e.newSceneButton.icon().isNull() and not e.saveAsButton.icon().isNull()
        assert not e.displayButton.isVisible() and not e.rootButton.isVisible()
        menu = QtWidgets.QMenu(e)
        e.modern.addNavigationMenu(menu)
        assert any(a.text() == 'Display settings…' for a in e.modern.navigationMenu.actions())
        result['checks'].append('Navigation icons and permanent settings menu available')
        e.operationTabs.setCurrentIndex(1)
        e.readOptions.controls['import']['mode'].setCurrentIndex(1)
        e.readOptions.controls['import']['name'].setText('hero')
        stage('02-import', 'Import / namespace and primary action')
        assert e.readOptions.fileArguments('import', str(work / 'shot020_animation_v003.ma'))['namespace'] == ':hero'
        e.operationTabs.setCurrentIndex(2)
        stage('03-reference', 'Reference / independent settings')
        assert e.readOptions.controls['reference']['mode'].currentIndex() == 0
        e.operationTabs.setCurrentWidget(e.readPanel)
        selectFile(e, fbx)
        e.fbxOptions.mode.setCurrentIndex(3)
        stage('04-fbx', 'FBX / Update animation only')
        assert e.actionButtons['open'].text() == 'Update Animation'
        # qpeHostへ接続済みの実処理を呼ばないため、ここでは設定のスナップショットを検証する。
        assert e.fbxOptions.snapshot()['mode'] == 'exmerge'
        result['checks'].append('Import namespace, Reference settings and FBX update mode stay independent')
        for width in (900, 720, 1280):
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=width)
            pause(450)
            e._operationTabChanged(e.operationTabs.currentIndex())
            pause(100)
            label = e.fbxOptions.description
            assert label.height() >= label.heightForWidth(label.width()), (width, label.size(), label.heightForWidth(label.width()))
            assert e.address.width() >= 100
            stage('05-width-' + str(width), 'Responsive layout / width ' + str(width))
        result['checks'].append('FBX description fits at 900/720/1280; address remains reachable')
        selectFile(e, work / 'shot020_animation_v003.ma')
        e.operationTabs.setCurrentWidget(e.savePanel)
        stage('06-save', 'Save / destination and Save As')
        for scale in (150, 200, 100):
            e.appearance.apply(12, scale, save=False)
            pause(350)
            assert e.files.property('qpeRowHeight') >= e.files.fontMetrics().height()
            assert e.actionButtons['saveAs'].height() >= e.actionButtons['saveAs'].fontMetrics().height()
        result['checks'].append('100/150/200 percent metrics keep text within rows and actions')
        e.operationTabs.setCurrentWidget(e.readPanel)
        selectFile(e, work / 'shot020_animation_v003.ma')
        for unused in range(3):
            QtTest.QTest.mouseClick(e.sidebarButton, QtCore.Qt.LeftButton)
            QtTest.QTest.mouseClick(e.inspectorButton, QtCore.Qt.LeftButton)
            pause(150)
        stage('07-browser', 'Browser / sidebars hidden')
        assert QtWidgets.QApplication.instance().palette() == palette
        result['checks'].append('Qt clicks toggle sidebars; application palette unchanged')
        if recorder:
            result['video'] = recorder.finish()
        result['status'] = 'passed'
    except Exception:
        if recorder:
            recorder.timer.stop()
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(result)
