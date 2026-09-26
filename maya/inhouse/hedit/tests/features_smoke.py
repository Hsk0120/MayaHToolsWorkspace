"""実際のQt操作でMEL、Explorer、検索置換、タブ移動を確認する。"""
from pathlib import Path


def check(window, directory, QtCore, QtGui, QtWidgets, QtTest):
    """現在のMayaに対して安全なコードと一時ファイルで機能を検証する。"""
    from maya import cmds, mel
    from hedit import startup

    def wait(ms=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction
    def action(text):
        return next(a for a in window.findChildren(action_type) if a.text() == text)

    tabs = window.findChild(QtWidgets.QTabWidget)
    initial = tabs.count()
    action('New MEL tab').trigger()
    code = tabs.currentWidget()
    assert code.property('language') == 'mel'
    code.setPlainText('global int $heditMelProbe; $heditMelProbe = 73; print("hedit MEL executed\\n");')
    action('Run all').trigger()
    assert mel.eval('$heditMelProbe = $heditMelProbe;') == 73
    code.setPlainText('print("comment test");')
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Slash, QtCore.Qt.ControlModifier)
    assert code.toPlainText().startswith('// ')
    mode = window.findChild(QtWidgets.QComboBox, 'languageMode')
    mode.setCurrentIndex(0); mode.activated.emit(0)
    assert code.property('language') == 'python'
    code.setPlainText('h1 h22')
    action('Replace…').trigger()
    window.findChild(QtWidgets.QLineEdit, 'findText').setText(r'h(\d+)')
    window.findChild(QtWidgets.QLineEdit, 'replaceText').setText('$1_$$')
    window.findChild(QtWidgets.QCheckBox, 'searchRegex').setChecked(True)
    window.findChild(QtWidgets.QPushButton, 'replaceAll').click()
    assert code.toPlainText() == '1_$ 22_$'
    code.undo(); assert code.toPlainText() == 'h1 h22'
    window.findChild(QtWidgets.QWidget, 'findBar').hide()
    window.findChild(QtWidgets.QCheckBox, 'searchRegex').setChecked(False)

    # Pythonの非アクティブタブと、アクティブなMELタブは診断しない。
    from hedit import analysis
    analyze = analysis.analyze
    calls = []
    analysis.analyze = lambda source: (calls.append(source), analyze(source))[1]
    static_action = next(a for a in window.findChildren(action_type) if a.objectName() == 'option_staticAnalysis')
    old_static = static_action.isChecked()
    try:
        static_action.setChecked(True)
        wait(950)
        calls.clear()
        action('New MEL tab').trigger()
        code.setPlainText('inactive_python = ???')
        wait(950)
        assert not calls
        tabs.setCurrentWidget(code)
        wait(950)
        assert calls == ['inactive_python = ???']
    finally:
        static_action.setChecked(old_static)
        analysis.analyze = analyze

    # ファイルダイアログも実際に選択する。テスト用の非ネイティブ表示だけを指定する。
    app = QtWidgets.QApplication.instance()
    old = app.testAttribute(QtCore.Qt.AA_DontUseNativeDialogs)
    app.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
    root = Path(directory) / 'explorer-fixture'; root.mkdir()
    (root / 'sample.py').write_text('fixture = 42\n', encoding='utf-8')
    second = root / 'nested'; second.mkdir()
    (second / 'sample.mel').write_text('print("fixture");\n', encoding='utf-8')
    def choose(label, path):
        touched = []
        def accept():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QFileDialog):
                dialog.setDirectory(str(path if path.is_dir() else path.parent))
                if not path.is_dir():
                    dialog.findChild(QtWidgets.QLineEdit, 'fileNameEdit').setText(str(path))
                    dialog.accept()
                else:
                    dialog.done(QtWidgets.QDialog.Accepted)
                touched.append(True)
            elif isinstance(dialog, QtWidgets.QDialog):
                dialog.reject()
        QtCore.QTimer.singleShot(200, accept)
        def timeout():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QDialog):
                dialog.reject()
        watchdog = QtCore.QTimer(window)
        watchdog.setSingleShot(True); watchdog.timeout.connect(timeout); watchdog.start(5000)
        action(label).trigger()
        watchdog.stop(); watchdog.deleteLater()
        assert touched, label
        wait()
    try:
        choose('Open folder…', root)
        choose('Add folder…', second)
        tree = window.findChild(QtWidgets.QTreeWidget, 'explorerTree')
        assert tree.topLevelItemCount() == 3
        choose('Open…', root / 'sample.py')
        assert tabs.currentWidget().toPlainText() == 'fixture = 42\n', (tabs.currentWidget().toPlainText(), tabs.currentWidget().property('path'))
        assert tree.topLevelItem(0).childCount() >= 1
        choose('Open…', second / 'sample.mel')
        assert tabs.currentWidget().property('language') == 'mel'
        action('Replace…').trigger()
        window.grab().save(str(Path(directory) / 'search-explorer-mel.png'))
        window.findChild(QtWidgets.QWidget, 'findBar').hide()
    finally:
        app.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, old)
    sidebar = next(a for a in window.findChildren(action_type) if a.objectName() == 'toggleExplorer')
    sidebar.trigger(); assert window.findChild(QtWidgets.QDockWidget, 'explorerDock').isHidden()
    sidebar.trigger(); assert not window.findChild(QtWidgets.QDockWidget, 'explorerDock').isHidden()
    for _ in range(25):
        action('New Python tab').trigger()
    bar = tabs.tabBar()
    assert bar.usesScrollButtons()
    assert any(button.isVisible() for button in bar.findChildren(QtWidgets.QToolButton))
    before = tabs.currentIndex()
    event = QtGui.QWheelEvent(QtCore.QPointF(20, 10), QtCore.QPointF(bar.mapToGlobal(QtCore.QPoint(20, 10))),
                             QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.NoButton,
                             QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
    app.sendEvent(bar, event)
    assert tabs.currentIndex() == before - 1
    while tabs.count() > initial:
        tabs.setCurrentIndex(tabs.count() - 1); tabs.currentWidget().document().setModified(False)
        action('Close tab').trigger()
    wait()
    startup.install_menu()
    assert cmds.menuItem(startup.MENU, exists=True)
    assert 'hedit.show()' in cmds.menuItem(startup.MENU, query=True, command=True)
    assert Path(cmds.menuItem(startup.MENU, query=True, image=True)).is_file()
    window.grab().save(str(Path(directory) / 'features.png'))
