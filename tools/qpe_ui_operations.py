"""操作別サイドバーの表示・設定保持・コマンド対象を専用Qt GUIで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
sys.path.insert(0, str(ROOT / 'tools'))


def main(output_dir, finished=None):
    """シーン更新を要求せず、実ウィジェットの入力と配置を検証・撮影する。"""
    from qpeQt import QtCore, QtGui, QtWidgets, QtTest
    from qpe_ui_maya import pause, selectFile
    from quickPathExplorer import Explorer
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output / 'settings.json')
    assets = output / 'Assets'
    assets.mkdir(exist_ok=True)
    for name in ('hero_walk.fbx', 'hero_rig.ma', 'notes.txt'):
        (assets / name).write_text('UI test fixture only; not a Maya scene', encoding='utf-8')
    frames = output / 'frames'
    frames.mkdir(exist_ok=True)
    widget = Explorer(maya=True)
    checks = []
    count = [0]
    timer = QtCore.QTimer(widget)

    def check(name, passed):
        """合否を記録し、不一致はその場で止める。"""
        checks.append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    def capture():
        """実ウィジェットを固定キャンバスに描画する。"""
        pix = QtGui.QPixmap(1280, 820)
        pix.fill(QtGui.QColor('#242424'))
        painter = QtGui.QPainter(pix)
        painter.drawPixmap(0, 0, widget.grab())
        painter.end()
        pix.save(str(frames / ('frame-%04d.png' % count[0])))
        count[0] += 1

    def stage(label):
        """操作を待って表示を採取する。"""
        caption.setText('Qt GUI verification | ' + label)
        pause(650)
        widget.grab().save(str(output / (label + '.png')))

    try:
        widget.setWindowTitle('QPE Sidebar UX verification')
        widget.resize(1280, 820)
        caption = QtWidgets.QLabel(widget)
        caption.setStyleSheet('background:#17363b;color:white;padding:8px;')
        widget.layout().insertWidget(0, caption)
        widget.show()
        widget.navigate(str(assets))
        selectFile(widget, assets / 'hero_walk.fbx')
        widget.inspectorButton.setChecked(True)
        pause(250)
        timer.timeout.connect(capture)
        timer.start(200)
        check('operation tabs', [widget.operationTabs.tabText(i) for i in range(4)] == ['Open', 'Import', 'Reference', 'Save'])
        check('details collapsed by default', widget.details.isHidden())
        check('sidebar stays compact', 280 <= widget.actionsPanel.width() <= 380)
        check('open settings and one action', widget.fbxOptions.isVisible() and widget.actionButtons['open'].isVisible()
              and not widget.actionButtons['import'].isVisible() and not widget.actionButtons['reference'].isVisible())
        check('open scene label', widget.actionButtons['open'].text() == 'Open Scene')
        stage('01-Open-Scene')
        widget.fbxOptions.mode.setCurrentIndex(widget.fbxOptions.mode.findData('exmerge'))
        check('animation update label', widget.actionButtons['open'].text() == 'Update Animation')
        stage('02-Update-Animation')
        calls = []
        widget.actionRequested.connect(lambda action: calls.append((action, widget.operationPaths())))
        QtTest.QTest.mouseClick(widget.actionButtons['open'], QtCore.Qt.LeftButton)
        check('update dispatch preserves open contract', calls[-1][0] == 'open' and calls[-1][1] == [str(assets / 'hero_walk.fbx').replace('\\', '/')])
        widget.operationTabs.setCurrentIndex(1)
        pause(100)
        fields = widget.readOptions.controls['import']
        check('import has no FBX open options', not widget.fbxOptions.isVisible() and fields['mode'].isVisible())
        check('advanced options collapsed', not fields['ignoreVersion'].isVisible())
        fields['mode'].setCurrentIndex(1)
        fields['name'].setText('shot:hero')
        stage('03-Import-Namespace')
        check('namespace visible and retained', fields['name'].isVisible() and widget.readOptions.fileArguments('import', str(assets / 'hero_rig.ma'))['namespace'] == ':shot:hero')
        QtTest.QTest.mouseClick(widget.actionButtons['import'], QtCore.Qt.LeftButton)
        check('import button dispatches import', calls[-1][0] == 'import')
        widget.readOptions.advancedToggles['import'].setChecked(True)
        pause(200)
        check('advanced expansion fits page', fields['ignoreVersion'].isVisible() and widget.actionButtons['import'].geometry().bottom() <= widget.operationTabs.currentWidget().height())
        stage('04-Import-Advanced')
        widget.operationTabs.setCurrentIndex(2)
        refs = widget.readOptions.controls['reference']
        refs['mode'].setCurrentIndex(1)
        refs['name'].setText('shot:heroRef')
        stage('05-Reference')
        QtTest.QTest.mouseClick(widget.actionButtons['reference'], QtCore.Qt.LeftButton)
        check('reference independent settings and dispatch', calls[-1][0] == 'reference' and fields['name'].text() == 'shot:hero')
        widget.operationTabs.setCurrentWidget(widget.savePanel)
        widget.fileName.setText('shot_animation_v002')
        stage('06-Save')
        check('save separates selected source', not widget.readTarget.isVisible() and not widget.detailsHeading.isVisible() and widget.fileName.isVisible())
        check('save default binary retained', widget.saveType.currentData() == 'mayaBinary' and widget.targetPath().endswith('.mb'))
        widget._showFbxSettings()
        pause(200)
        check('toolbar reveals correct page', widget.operationTabs.currentWidget() is widget.readPanel and widget.fbxOptions.isVisible())
        widget.detailsHeading.setChecked(True)
        stage('07-File-Details')
        check('details opt in', widget.details.isVisible() and widget.metadata.isVisible())
        widget.detailsHeading.setChecked(False)
        widths = widget.outer.sizes()
        widget.inspectorButton.setChecked(False)
        pause(150)
        widget.inspectorButton.setChecked(True)
        pause(150)
        check('sidebar toggle preserves width', abs(widget.outer.sizes()[2] - widths[2]) <= 2)
        selectFile(widget, assets / 'notes.txt')
        check('other file hides FBX options', widget.fbxOptions.isHidden() and widget.actionButtons['open'].text() == 'Open')
        widget.files.clearSelection()
        check('empty selection disables read actions', all(not widget.actionButtons[k].isEnabled() for k in ('open', 'import', 'reference')))
        selectFile(widget, assets / 'hero_walk.fbx')
        widget.resize(1000, 620)
        pause(200)
        check('narrow window keeps usable sidebar', widget.actionsPanel.width() <= 380 and widget.actionButtons['open'].width() > 200)
        widget.resize(1280, 820)
        stage('08-Ready')
        original_font, original_scale = widget.appearance.fontSize, widget.appearance.uiPercent
        widget.operationTabs.setCurrentIndex(1)
        widget.readOptions.advancedToggles['import'].setChecked(True)
        for scale in (150, 200):
            widget.appearance.apply(original_font, scale, save=False)
            pause(250)
            widget.inspectorScroll.ensureWidgetVisible(widget.actionButtons['import'])
            pause(150)
            button = widget.actionButtons['import']
            point = button.mapTo(widget.inspectorScroll.viewport(), button.rect().center())
            check('scaled action reachable ' + str(scale), widget.inspectorScroll.viewport().rect().contains(point))
            longest = fields['removeDuplicateNetworks']
            text_width = longest.fontMetrics().boundingRect(longest.text()).width()
            check('scaled option label fits ' + str(scale), longest.width() >= text_width + 18)
            widget.grab().save(str(output / ('scale-' + str(scale) + '.png')))
        widget.operationTabs.setCurrentIndex(2)
        pause(100)
        check('new operation starts at top', widget.inspectorScroll.verticalScrollBar().value() == 0)
        widget.appearance.apply(original_font, original_scale, save=False)
        widget._showFbxSettings()
        pause(250)
        if os.environ.get('QPE_SIDEBAR_NATIVE') == '1':
            import time
            (output / 'native-ready.txt').write_text('ready', encoding='utf-8')
            deadline = time.monotonic() + 180
            while not (output / 'native-finished.txt').exists() and time.monotonic() < deadline:
                pause(200)
        result = {'status': 'passed', 'checks': checks, 'input': 'Qt QTest/API, no native OS input or scene operations'}
    except Exception:
        result = {'status': 'failed', 'checks': checks, 'traceback': traceback.format_exc()}
        widget.grab().save(str(output / 'failure.png'))
    finally:
        timer.stop()
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(widget, QtCore.QEvent.DeferredDelete)
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    from qpeQt import QtWidgets
    app = QtWidgets.QApplication([])
    sys.exit(0 if main(sys.argv[1])['status'] == 'passed' else 1)
