"""run_hlib_gui_versionsの専用Mayaに渡すGUIスイート。"""
import json
from pathlib import Path
import traceback
import time


def main(output_dir, finished):
    from maya import cmds, mel
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    def wait_events(milliseconds):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    directory = Path(output_dir)
    result = {'status': 'error', 'checks': []}
    try:
        from maya.api import OpenMaya as om
        om.MGlobal.displayInfo('hedit_before_open_history_probe')
        import hedit
        # GUIランナーは全userSetupを抑止するので、.mod内の実ファイルを明示実行する。
        import runpy
        runpy.run_path(str(Path(hedit.__file__).resolve().parents[1] / 'userSetup.py'))
        wait_events(200)
        assert cmds.pluginInfo('hedit', query=True, loaded=True)
        from hedit import startup
        assert cmds.menuItem(startup.MENU, exists=True)
        result['checks'].append('user_setup_autoload_and_menu')
        host = hedit.show()
        window = host.editor
        assert window.isVisible()
        wait_events(100)
        initial_output=window.findChild(QtWidgets.QPlainTextEdit, 'output')
        assert initial_output.toPlainText().count('hedit_before_open_history_probe') == 1, initial_output.toPlainText()
        from maya import OpenMaya as om1
        om1.MGlobal.executeCommand('about -version;', True, False)
        wait_events(80)
        assert '// Result: {}'.format(cmds.about(version=True)) in initial_output.toPlainText(), initial_output.toPlainText()
        result['checks'].append('initial_maya_history_and_result_format')
        result['checks'].append('window_visible')
        from hedit import docking
        split = window.findChild(QtWidgets.QSplitter, 'editorSplitter')
        assert split.widget(0).objectName() == 'outputPanel'
        assert isinstance(split.widget(1), QtWidgets.QTabWidget)
        cmds.workspaceControl(docking.CONTROL, edit=True, dockToMainWindow=('bottom', False))
        assert not cmds.workspaceControl(docking.CONTROL, query=True, floating=True)
        cmds.workspaceControl(docking.CONTROL, edit=True, floating=True)
        assert cmds.workspaceControl(docking.CONTROL, query=True, floating=True)
        cmds.workspaceControl(docking.CONTROL, edit=True, close=True)
        assert hedit.show() is host
        window = host.editor
        assert window.isVisible()
        result['checks'].append('output_above_code_dock_float_reopen')
        # 明示再起動を繰り返しても本文と一つのホストを維持する。
        import importlib
        tabs_probe = window.findChild(QtWidgets.QTabWidget)
        tabs_probe.currentWidget().setPlainText('unsaved_reopen_probe = 42')
        original_host = docking.getCppPointer(host)[0]
        class CloseProbe(QtCore.QObject):
            def __init__(self):
                super(CloseProbe, self).__init__(); self.count = 0
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.Close:
                    self.count += 1
                return False
        close_probe = CloseProbe()
        window.installEventFilter(close_probe)
        for i in range(3):
            if i == 1:
                importlib.reload(docking)
                docking._host = None  # Python参照喪失も実際のQt所有ツリーから回収する。
            reopened = hedit.show()
            assert docking.getCppPointer(reopened)[0] == original_host
            assert reopened.isVisible() and reopened.editor.isVisible()
            # Qt5ではreparent/再表示後にPython側ラッパーが無効化されるため再取得する。
            window = reopened.editor
            tabs_probe = window.findChild(QtWidgets.QTabWidget)
            assert tabs_probe.currentWidget().toPlainText() == 'unsaved_reopen_probe = 42'
            visible_hosts = [w for w in QtWidgets.QApplication.allWidgets()
                             if w.objectName() == 'heditDock' and w.isVisible()]
            assert len(visible_hosts) == 1
        assert close_probe.count == 3, close_probe.count
        window.removeEventFilter(close_probe)
        split = window.findChild(QtWidgets.QSplitter, 'editorSplitter')
        result['checks'].append('single_host_reopen_reload_preserves_unsaved_text')
        code = window.findChild(QtWidgets.QPlainTextEdit, 'codeEditor')
        toolbar = window.findChild(QtWidgets.QToolBar, 'scriptToolbar')
        assert toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly
        assert all(not item.icon().isNull() for item in toolbar.actions() if not item.isSeparator() and not toolbar.widgetForAction(item).inherits("QComboBox"))
        by_name = {item.text(): item for item in toolbar.actions()}
        by_name['Show output only'].trigger()
        assert split.widget(1).isHidden() and not split.widget(0).isHidden()
        by_name['Show input only'].trigger()
        assert split.widget(0).isHidden() and not split.widget(1).isHidden()
        by_name['Show input and output'].trigger()
        code.setPlainText('restore_after_clear = 42')
        by_name['Clear input'].trigger()
        assert not code.toPlainText()
        code.undo()
        assert code.toPlainText() == 'restore_after_clear = 42'
        result['checks'].append('icon_toolbar_layout_and_clear_input_undo')
        code.setPlainText('# Dark+ palette\nclass Controller:\n    def create(self, name="control"):\n        size = 1.0\n        return name\n')
        visual_output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        visual_output.setPlainText('Maya / hedit output\n[Transform(\'control\')]\n')
        from maya.api import OpenMaya as om
        om.MGlobal.displayInfo('color_info')
        om.MGlobal.displayWarning('color_warning_first\ncolor_warning_second')
        om.MGlobal.displayError('color_error_first\ncolor_error_second')
        print('color_plain_after_error')
        wait_events(80)
        for marker, expected in (('color_info', '#9cdcfe'), ('color_warning_first', '#ffff00'),
                                 ('color_warning_second', '#ffff00'), ('color_error_first', '#ff0000'),
                                 ('color_error_second', '#ff0000'), ('color_plain_after_error', '#d4d4d4')):
            position = visual_output.toPlainText().index(marker)
            cursor = visual_output.textCursor()
            cursor.setPosition(position)
            cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor)
            assert cursor.charFormat().foreground().color().name() == expected, marker
        result['checks'].append('typed_output_colors_multiline_and_normal_reset')
        # 専用のシーンを開く最中に、イベントループへ戻る前の描画を検証する。
        class PaintProbe(QtCore.QObject):
            def __init__(self):
                super(PaintProbe,self).__init__(); self.count=0
            def eventFilter(self,obj,event):
                if event.type()==QtCore.QEvent.Paint: self.count+=1
                return False
        paint_probe=PaintProbe(); visual_output.viewport().installEventFilter(paint_probe)
        probe_results=[]
        def scene_log_probe(*unused):
            for i in range(3):
                time.sleep(.04)  # Qtイベント処理は呼ばず、読み込み側を占有する。
                previous_paints=paint_probe.count
                marker='hedit_during_scene_open_%d' % i
                om.MGlobal.displayInfo(marker)
                probe_results.append((marker in visual_output.toPlainText(),paint_probe.count>previous_paints))
        scene_path=(directory/'realtime-log.ma').resolve().as_posix()
        scene_callback=None
        try:
            cmds.file(new=True,force=True)
            cmds.file(rename=scene_path); cmds.file(save=True,type='mayaAscii',force=True)
            cmds.file(new=True,force=True); probe_results[:]=[]
            scene_callback=om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeOpen,scene_log_probe)
            (directory/'scene-log-stage.txt').write_text('opening',encoding='utf-8')
            cmds.file(scene_path,open=True,force=True,prompt=False)
            (directory/'scene-log-stage.txt').write_text(repr(probe_results),encoding='utf-8')
            assert len(probe_results)==3 and all(text and painted for text,painted in probe_results), probe_results
            result['checks'].append('scene_open_logs_painted_before_return')
        finally:
            visual_output.viewport().removeEventFilter(paint_probe)
            if scene_callback is not None: om.MMessage.removeCallback(scene_callback)
            cmds.file(new=True,force=True)
        mode=window.findChild(QtWidgets.QComboBox,'outputMode')
        mode.setCurrentText('Errors only')
        assert 'color_error_first' in visual_output.toPlainText() and 'color_warning_first' not in visual_output.toPlainText()
        mode.setCurrentText('Warnings + Errors')
        assert 'color_warning_first' in visual_output.toPlainText() and 'color_plain_after_error' not in visual_output.toPlainText()
        mode.setCurrentText('Output only')
        assert 'color_plain_after_error' in visual_output.toPlainText()
        mode.setCurrentText('Normal')
        assert 'color_warning_first' in visual_output.toPlainText() and 'color_error_first' in visual_output.toPlainText()
        assert mode.parentWidget()==toolbar
        assert window.findChild(QtWidgets.QPushButton,'saveOutput') is None
        assert window.findChild(QtWidgets.QPushButton,'clearOutputButton') is None
        action_type=getattr(QtWidgets,'QAction',None) or QtGui.QAction
        next(a for a in window.findChildren(action_type) if a.text()=='Find…').trigger()
        find_bar=window.findChild(QtWidgets.QWidget,'findBar')
        assert find_bar.parentWidget() == split.widget(1)
        assert find_bar.y() >= split.widget(1).tabBar().height()
        assert abs(find_bar.geometry().right()-(split.widget(1).width()-7)) <= 2
        window.findChild(QtWidgets.QLineEdit,'findText').setText('Controller')
        wait_events(50)
        window.grab().save(str(directory / 'output-modes-search.png'))
        find_bar.hide()
        result['checks'].append('find_overlay_at_editor_top_right')
        by_name['Clear output'].trigger()
        mode.setCurrentIndex(3); mode.setCurrentIndex(0)
        assert not visual_output.toPlainText()
        result['checks'].append('output_modes_toolbar_restore_clear')
        assert window.grab().save(str(directory / 'maya-dark-plus.png'))
        import importlib.util
        selection_spec = importlib.util.spec_from_file_location('hedit_output_selection', str(Path(__file__).with_name('output_selection_smoke.py')))
        selection_tests = importlib.util.module_from_spec(selection_spec)
        selection_spec.loader.exec_module(selection_tests)
        selection_tests.check(visual_output, QtCore, QtGui, QtWidgets, QtTest)
        result['checks'].append('output_selection_copy_append_scroll_readonly')
        visual_output.clear()
        # Ctrl+Gはフォーカス中の欄だけを移動し、取消時は位置を保つ。
        for target in (code, visual_output):
            QtWidgets.QApplication.setActiveWindow(window.window())
            window.window().activateWindow()
            target.setPlainText('\n'.join('line %s' % i for i in range(1, 121)))
            target.moveCursor(QtGui.QTextCursor.Start)
            target.setFocus()
            for accept in (True, False):
                QtTest.QTest.keyClick(target, QtCore.Qt.Key_G, QtCore.Qt.ControlModifier)
                wait_events(30)
                entry = window.findChild(QtWidgets.QLineEdit, 'lineJump')
                assert entry and entry.isVisible(), (target.objectName(), accept, repr(entry), repr(QtWidgets.QApplication.focusWidget()))
                entry.setText('100' if accept else '20')
                QtTest.QTest.keyClick(entry, QtCore.Qt.Key_Return if accept else QtCore.Qt.Key_Escape)
                wait_events(120)
                assert not window.findChild(QtWidgets.QLineEdit, 'lineJump'), 'Line entry did not close'
                assert target.textCursor().blockNumber() == 99
                if accept:
                    assert target.hasFocus(), target.objectName()
                # Maya 2024はEsc後にビューポートへフォーカスを移す。
                target.setFocus()
            assert target.verticalScrollBar().value() > 0
        result['checks'].append('ctrl_g_code_output_jump_cancel_focus')
        feature_spec = importlib.util.spec_from_file_location('hedit_features', str(Path(__file__).with_name('features_smoke.py')))
        features = importlib.util.module_from_spec(feature_spec)
        feature_spec.loader.exec_module(features)
        features.check(window, directory, QtCore, QtGui, QtWidgets, QtTest)
        result['checks'].append('mel_explorer_regex_groups_scroll_tabs_menu')
        visual_output.clear()
        code.setPlainText('import maya.cmds as cmds\nprint(cmds.about(version=True))')
        # Qt6でQActionはQtGuiへ移動しているため、ツールバー上から取得する。
        toolbar = window.findChild(QtWidgets.QToolBar)
        next(action for action in toolbar.actions() if action.text() == 'Run all').trigger()
        assert str(cmds.about(version=True)) in window.findChild(QtWidgets.QPlainTextEdit, 'output').toPlainText()
        result['checks'].append('execute_in_maya')
        # 実際の標準Script Editorの入力欄と出力欄で双方向を確認する。
        mel.eval('ScriptEditor;')
        reporters = cmds.lsUI(type='cmdScrollFieldReporter') or []
        executers = [name for name in (cmds.lsUI(type='cmdScrollFieldExecuter') or [])
                     if cmds.cmdScrollFieldExecuter(name, query=True, sourceType=True) == 'python']
        assert reporters and executers, 'Native Script Editor controls missing'
        native = executers[0]
        assert cmds.cmdScrollFieldExecuter(native, query=True, sourceType=True) == 'python'
        output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        run_all = next(action for action in toolbar.actions() if action.text() == 'Run all')
        code.setPlainText('hedit_shared_value = 2718\nprint("hedit" + "_outgoing_日本語")')
        run_all.trigger()
        wait_events(80)
        native_text = '\n'.join(cmds.cmdScrollFieldReporter(name, query=True, text=True) for name in reporters)
        assert 'hedit_outgoing_日本語' in native_text, repr(native_text)
        assert output.toPlainText().splitlines().count('hedit_outgoing_日本語') == 1, output.toPlainText()
        result['checks'].append('hedit_to_native_once')
        cmds.cmdScrollFieldExecuter(native, edit=True, text='print("Native" + "_incoming", hedit_shared_value)')
        assert 'Native' in cmds.cmdScrollFieldExecuter(native, query=True, text=True)
        def after_native():
            nonlocal code
            try:
                wait_events(80)
                assert output.toPlainText().splitlines().count('Native_incoming 2718') == 1, (output.toPlainText(), [cmds.cmdScrollFieldReporter(n, query=True, text=True) for n in reporters])
                result['checks'].append('native_to_hedit_once_shared_namespace')
                import importlib.util
                spec = importlib.util.spec_from_file_location('shortcut_smoke', Path(__file__).with_name('shortcut_smoke.py'))
                shortcuts = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(shortcuts)
                window.window().activateWindow()
                code.setFocus()
                wait_events(100)
                shortcuts.check(window, QtCore, QtGui, QtWidgets, QtTest)
                option_spec = importlib.util.spec_from_file_location('hedit_options_smoke', str(Path(__file__).with_name('options_smoke.py')))
                option_tests = importlib.util.module_from_spec(option_spec)
                option_spec.loader.exec_module(option_tests)
                option_tests.check(window, directory, QtCore, QtGui, QtWidgets, QtTest)
                search_spec = importlib.util.spec_from_file_location('hedit_search_smoke', str(Path(__file__).with_name('search_smoke.py')))
                search_tests = importlib.util.module_from_spec(search_spec)
                search_spec.loader.exec_module(search_tests)
                search_tests.check(window, QtCore, QtGui, QtWidgets, QtTest)
                result['checks'].append('search_modes_safe_replace_undo_zoom')
                result['checks'].append('preferences_edit_completion_save_persistence')
                result['checks'].append('vscode_shortcuts_edit_undo_search_replace_tabs')
                cmds.warning('hedit_native_warning')
                code.setPlainText('raise ValueError("hedit_shared_error")')
                run_all.trigger()
                wait_events(80)
                assert 'hedit_native_warning' in output.toPlainText()
                assert 'ValueError' in output.toPlainText() and 'hedit_shared_error' in output.toPlainText()
                assert any('hedit_shared_error' in cmds.cmdScrollFieldReporter(name, query=True, text=True) for name in reporters)
                result['checks'].append('shared_warning_and_error')
                assert window.grab().save(str(directory / 'shared-output.png'))
                # 後続の選択実行テストは履歴から切り離す。
                native_before = [cmds.cmdScrollFieldReporter(n, query=True, text=True) for n in reporters]
                menu_checks = []
                def clear_from_menu():
                    menu = QtWidgets.QApplication.activePopupWidget()
                    if isinstance(menu, QtWidgets.QMenu):
                        action = next((a for a in menu.actions() if a.objectName() == 'clearOutputAction'), None)
                        if action:
                            action.trigger()
                            menu_checks.append(True)
                        menu.close()
                QtCore.QTimer.singleShot(50, clear_from_menu)
                event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, QtCore.QPoint(20, 20), output.viewport().mapToGlobal(QtCore.QPoint(20, 20)))
                QtWidgets.QApplication.sendEvent(output.viewport(), event)
                assert menu_checks and not output.toPlainText()
                assert native_before == [cmds.cmdScrollFieldReporter(n, query=True, text=True) for n in reporters]
                result['checks'].append('right_click_clear_local_output')
                code.document().setModified(False)

                # 新しいタブで実際にキー入力し、Ctrl+Spaceなしの自動補完を確認する。
                next(a for a in window.findChildren(QtGui.QAction if hasattr(QtGui, 'QAction') else QtWidgets.QAction)
                     if a.text() == 'New Python tab').trigger()
                code = window.findChild(QtWidgets.QTabWidget).currentWidget()
                code.setPlainText('import maya.cmds as cmds\n')
                cursor = code.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                code.setTextCursor(cursor)
                window.activateWindow()
                code.setFocus()
                QtTest.QTest.keyClicks(code, 'cmds.')
                deadline = time.monotonic() + 20

                def finish():
                    try:
                        def stage(name):
                            (directory / 'finish-stage.txt').write_text(name, encoding='utf-8')
                        stage('close')
                        code.document().setModified(False)
                        assert window.close()
                        stage('unload')
                        cmds.unloadPlugin('hedit')
                        assert not cmds.workspaceControl(docking.CONTROL, exists=True)
                        result['checks'].append('close_and_unload')
                        # 保存されたuiScriptからの再構築経路を同じGUI内で検証する。
                        stage('restore_control')
                        cmds.workspaceControl(docking.CONTROL, label='hedit', floating=True,
                                              retain=True, loadImmediately=True,
                                              uiScript='import hedit; hedit.restore()')
                        wait_events(80)
                        stage('restore_show')
                        restored = hedit.show()
                        assert restored.editor.isVisible()
                        assert len([w for w in QtWidgets.QApplication.allWidgets() if w.objectName() == 'hedit']) == 1
                        stage('restore_unload')
                        cmds.unloadPlugin('hedit')
                        assert not cmds.workspaceControl(docking.CONTROL, exists=True)
                        result['checks'].append('workspace_ui_script_restore_and_unload')
                    except Exception:
                        result['status'] = 'error'
                        result['error'] = traceback.format_exc()
                    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                    finished(result)

                def complete():
                    try:
                        completer = code.findChild(QtWidgets.QCompleter)
                        if completer.popup().isVisible() and completer.completionCount():
                            model = completer.completionModel()
                            rows = [row for row in range(model.rowCount()) if model.index(row, 0).data() == 'createNode']
                            assert model.rowCount() > 0, 'No dot completion candidates'
                            result['checks'].append('completion_visible')
                            assert window.grab().save(str(directory / 'hedit-gui.png'))
                            assert completer.popup().grab().save(str(directory / 'completion.png'))
                            chosen = model.index(0, 0).data()
                            completer.popup().setCurrentIndex(model.index(0, 0))
                            event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
                            QtWidgets.QApplication.sendEvent(completer.popup(), event)
                            assert code.toPlainText().endswith('cmds.' + chosen), code.toPlainText()
                            result['checks'].append('completion_enter_insertion')
                            wait_events(200)
                            assert not completer.popup().isVisible(), 'Completion reopened after accepting'
                            # 同名の候補を確定しても、次のEnterは改行になる。
                            import sys
                            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
                            code.setPlainText('import hlib')
                            code.moveCursor(QtGui.QTextCursor.End); code.setFocus()
                            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
                            wait_events(700)
                            model=completer.completionModel()
                            row=next(i for i in range(model.rowCount()) if model.index(i,0).data()=='hlib')
                            completer.popup().setCurrentIndex(model.index(row,0))
                            QtTest.QTest.keyClick(completer.popup(), QtCore.Qt.Key_Return)
                            wait_events(200)
                            assert not completer.popup().isVisible()
                            code.setFocus(); QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
                            assert code.toPlainText()=='import hlib\n', repr(code.toPlainText())
                            result['checks'].append('completion_accept_then_enter_newline')
                            import hlib
                            code.setPlainText('import hlib\nhlib.nodes.')
                            code.moveCursor(QtGui.QTextCursor.End); code.setFocus()
                            wait_events(700)
                            model = completer.completionModel()
                            names = [model.index(i,0).data() for i in range(model.rowCount())]
                            assert completer.popup().isVisible(), 'hlib.nodes popup not visible'
                            assert {'Node','Joint','SkinCluster','Transform'}.issubset(names), names
                            result['checks'].append('hlib_nodes_subpackage_classes_visible')
                            window.grab().save(str(directory / 'hlib-nodes-completion.png'))
                            completer.popup().hide()
                            # 選択実行では未選択の例外を実行しないことも確認。
                            code.setPlainText('print("selection_passed")\nraise RuntimeError("must not run")')
                            cursor = code.textCursor()
                            cursor.movePosition(QtGui.QTextCursor.Start)
                            cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
                            code.setTextCursor(cursor)
                            next(a for a in toolbar.actions() if 'Run selection' in a.text()).trigger()
                            text = window.findChild(QtWidgets.QPlainTextEdit, 'output').toPlainText()
                            assert 'selection_passed' in text and 'RuntimeError' not in text, text
                            # 実キーで選択範囲だけが1回実行され、コードと選択が保持される。
                            import __main__
                            __main__._hedit_selected_runs = 0
                            sample = '_hedit_selected_runs += 1\nprint("keyboard_selection")\nraise RuntimeError("unselected_must_not_run")'
                            code.setPlainText(sample)
                            cursor = code.textCursor()
                            cursor.setPosition(0)
                            cursor.setPosition(sample.index('raise'), QtGui.QTextCursor.KeepAnchor)
                            code.setTextCursor(cursor)
                            code.setFocus()
                            for key, mods in ((QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier),
                                              (QtCore.Qt.Key_Enter, QtCore.Qt.ControlModifier | QtCore.Qt.KeypadModifier),
                                              (QtCore.Qt.Key_Enter, QtCore.Qt.KeypadModifier)):
                                before = __main__._hedit_selected_runs
                                QtTest.QTest.keyClick(code, key, mods)
                                assert __main__._hedit_selected_runs == before + 1
                                assert code.toPlainText() == sample and code.textCursor().hasSelection()
                            code.setPlainText('_hedit_selected_runs += 10\n_hedit_selected_runs += 20')
                            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier)
                            assert __main__._hedit_selected_runs == 33
                            code.setPlainText('')
                            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
                            assert code.toPlainText() == '\n'
                            del __main__._hedit_selected_runs
                            result['checks'].append('keyboard_selection_and_full_execution_enter_variants')
                            result['checks'].append('selection_execution')
                            result['status'] = 'passed'
                            finish()
                            return
                        if time.monotonic() >= deadline:
                            raise RuntimeError('GUI completion did not become visible within 20 seconds')
                        QtCore.QTimer.singleShot(200, complete)
                    except Exception:
                        result['error'] = traceback.format_exc()
                        finish()
                QtCore.QTimer.singleShot(500, complete)
            except Exception:
                result['error'] = traceback.format_exc()
                (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                finished(result)
        def run_native():
            cmds.setFocus(native)
            mel.eval('evalDeferred "cmdScrollFieldExecuter -e -execute ' + native + '";')
            cmds.evalDeferred(after_native, lowestPriority=True)
        QtCore.QTimer.singleShot(500, run_native)
    except Exception:
        result['error'] = traceback.format_exc()
        (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        finished(result)
