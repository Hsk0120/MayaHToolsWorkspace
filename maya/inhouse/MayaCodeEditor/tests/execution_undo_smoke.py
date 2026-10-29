"""専用Maya GUIでコード実行後のシーンUndoを検査する。ユーザーシーンでは実行しない。"""
import json
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """標準実行とMCEのRun allを比べ、履歴・状態・Undo/Redoを確認する。

    Args:
        output_dir (str): 専用prefsで起動したGUIの証拠保存先。
        finished (callable): ランナーへの完了通知。
    """
    # Maya GUIとそのQt版が必要なため、専用ランナーから呼ばれてからimportする。
    from maya import cmds, mel
    from maya.api import OpenMaya as om
    import __main__
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import gui_host

    directory = Path(output_dir)
    result = {"status": "error", "maya": cmds.about(version=True), "input": "Qt QAction and Maya commands; not OS input", "checks": []}

    def exercise():
        """Mayaの遅延実行へ制御を返しながら比較を進める。"""
        recording = None
        frame = [0]
        label = ["Preparing scene Undo verification"]
        command_callback = None
        command_trace = []
        try:
            cmds.loadPlugin("mayaCodeEditor", quiet=True)
            cmds.mayaCodeEditor(show=True)
            window = gui_host.editor()
            window.resize(1180, 780)
            code = window.findChild(QtWidgets.QTabWidget).currentWidget()
            toolbar = window.findChild(QtWidgets.QToolBar)
            run_all = next(a for a in toolbar.actions() if a.text() == "Run all")
            mode = window.findChild(QtWidgets.QComboBox, "languageMode")
            output = window.findChild(QtWidgets.QPlainTextEdit, "output")
            yield 10000  # 新規prefsでの標準プラグイン初回ロードを試験操作と分離する。
            frames = directory / "recording"
            frames.mkdir(exist_ok=True)

            def capture():
                """所有するMCEの描画と、その時点で確認したシーン状態を録画する。"""
                canvas = QtGui.QPixmap(1200, 850)
                canvas.fill(QtGui.QColor("#202124"))
                painter = QtGui.QPainter(canvas)
                painter.setPen(QtGui.QColor("#eeeeee"))
                font = painter.font()
                font.setPixelSize(19)
                painter.setFont(font)
                painter.drawText(16, 26, "Maya " + result["maya"] + " | Qt actions + Maya scene Undo/Redo")
                painter.drawText(16, 54, label[0])
                painter.drawPixmap(10, 70, window.grab().scaled(1180, 770, QtCore.Qt.KeepAspectRatio))
                painter.end()
                canvas.save(str(frames / ("%05d.png" % frame[0])))
                frame[0] += 1

            recording = QtCore.QTimer(window)
            recording.timeout.connect(capture)
            recording.start(200)
            cmds.file(new=True, force=True)
            mel.eval("ScriptEditor;")
            native = next(name for name in cmds.lsUI(type="cmdScrollFieldExecuter") or []
                          if cmds.cmdScrollFieldExecuter(name, query=True, sourceType=True) == "python")
            # 標準Script Editorを比較した後もMCEの所有ウィンドウだけを撮影する。
            window.show()
            cmds.createNode("transform", name="mceUndoWarmup")
            yield -1
            yield 2000
            yield -1
            result["plugins_before_checks"] = cmds.pluginInfo(query=True, listPlugins=True) or []
            def trace_command(command, *unused):
                """専用シーンで遅延実行されたコマンドを診断用に記録する。"""
                if len(command_trace) < 3000:
                    command_trace.append(str(command)[:4096])
            command_callback = om.MCommandMessage.addCommandCallback(trace_command)
            cases = [
                ("cmds create", "python", "from maya import cmds\ncmds.createNode('transform', name='mceUndoTarget')", "create"),
                ("mlib create", "python", "import mlib\nmlib.createNode('transform', name='mceUndoTarget')", "create"),
                ("mlib plug set", "python", "import mlib\nmlib.getNode('mceUndoTarget').getPlug('translateX').set(7)", "set"),
                ("nested mlib chunk", "python", "import mlib\nfrom mlib.decorator import undoChunk\nwith undoChunk('mceNested'):\n    mlib.createNode('transform', name='mceUndoTarget')\n    mlib.createNode('transform', name='mceUndoSecond')", "nested"),
                ("partial change before exception", "python", "from maya import cmds\ncmds.createNode('transform', name='mceUndoTarget')\nraise ValueError('intentional execution undo test')", "create"),
                ("MEL create", "mel", 'createNode transform -n "mceUndoTarget";', "create"),
            ]
            for index, (name, language, source, kind) in enumerate(cases):
                hosts = ("mce", "native") if language == "python" else ("mce",)
                if name == "mlib create":
                    hosts += ("mce_saved", "mce_selection")
                for host in hosts:
                    cmds.undoInfo(state=True)
                    cmds.file(new=True, force=True)
                    yield 500  # 新規シーンの遅延初期化・Undo履歴初期化が終わってから試験を始める。
                    if kind == "set":
                        cmds.createNode("transform", name="mceUndoTarget")
                    cmds.flushUndo()
                    cmds.createNode("transform", name="mceUndoSentinel")
                    prefix = "from maya import cmds\n__mce_undo_inside = cmds.undoInfo(query=True, state=True)\n" if language == "python" else ""
                    source_run = prefix + source
                    __main__.__mce_undo_inside = None
                    code.setPlainText(source_run)
                    code.setProperty("path", "")
                    if host == "mce_saved":
                        path = directory / "saved.py"
                        path.write_text(source_run, encoding="utf-8")
                        code.setProperty("path", str(path))
                    if host == "mce_selection":
                        code.setPlainText(source_run + "\nraise AssertionError('Unselected code must not run')")
                        selected = code.textCursor()
                        selected.setPosition(0)
                        selected.setPosition(len(source_run), QtGui.QTextCursor.KeepAnchor)
                        code.setTextCursor(selected)
                    mode.setCurrentIndex(1 if language == "mel" else 0)
                    mode.activated.emit(mode.currentIndex())
                    if host == "native":
                        cmds.cmdScrollFieldExecuter(native, edit=True, text=source_run)
                        cmds.setFocus(native)
                        mel.eval('evalDeferred "cmdScrollFieldExecuter -e -execute ' + native + '";')
                        yield -1  # Mayaの実行待ちキューが空になってから採取する。
                    elif host == "mce_selection":
                        action_type = getattr(QtWidgets, "QAction", None) or QtGui.QAction
                        next(a for a in window.findChildren(action_type) if a.text() == "Run selection / script").trigger()
                    else:
                        run_all.trigger()
                    entry = {"name": name, "host": host, "state_after": cmds.undoInfo(query=True, state=True),
                             "undo_name": cmds.undoInfo(query=True, undoName=True), "created": cmds.objExists("mceUndoTarget")}
                    if language == "python":
                        entry["state_inside"] = getattr(__main__, "__mce_undo_inside", None)
                    entry["before_undo"] = cmds.getAttr("mceUndoTarget.translateX") if kind == "set" else entry["created"]
                    result["checks"].append(entry)
                    label[0] = host + " | " + name + " | Executed: " + str(entry["before_undo"])
                    yield 500
                    cmds.undo()
                    command_trace.append("=== AFTER UNDO ===")
                    entry["after_undo"] = cmds.getAttr("mceUndoTarget.translateX") if kind == "set" and cmds.objExists("mceUndoTarget") else cmds.objExists("mceUndoTarget")
                    entry["sentinel_kept"] = cmds.objExists("mceUndoSentinel")
                    entry["nested_removed"] = not cmds.objExists("mceUndoSecond")
                    label[0] = host + " | " + name + " | Undo: " + str(entry["after_undo"])
                    yield 500
                    cmds.redo()
                    command_trace.append("=== AFTER REDO ===")
                    entry["after_redo"] = cmds.getAttr("mceUndoTarget.translateX") if kind == "set" and cmds.objExists("mceUndoTarget") else cmds.objExists("mceUndoTarget")
                    entry["passed"] = (entry["state_after"] and entry.get("state_inside", True)
                                       and entry["before_undo"] == (7 if kind == "set" else True)
                                       and entry["after_undo"] == (0 if kind == "set" else False)
                                       and entry["after_redo"] == (7 if kind == "set" else True)
                                       and entry["sentinel_kept"] and entry["nested_removed"])
                    label[0] = host + " | " + name + " | Redo: " + str(entry["after_redo"]) + " | " + ("PASS" if entry["passed"] else "FAIL")
                    output.appendPlainText("SCENE UNDO CHECK " + json.dumps(entry, ensure_ascii=False))
                    yield 400
                    window.grab().save(str(directory / ("undo-%02d-%s.png" % (index, host))))
            # 利用者がUndoを無効化している場合に、MCEが勝手に有効化しないこと。
            cmds.file(new=True, force=True)
            yield 500
            cmds.flushUndo()
            cmds.undoInfo(stateWithoutFlush=False)
            mode.setCurrentIndex(0)
            mode.activated.emit(0)
            code.setPlainText("from maya import cmds\n__mce_undo_disabled = cmds.undoInfo(query=True, state=True)\ncmds.createNode('transform', name='mceDisabledTarget')")
            run_all.trigger()
            disabled = {"name": "disabled preference preserved", "state_inside": getattr(__main__, "__mce_undo_disabled", None),
                        "state_after": cmds.undoInfo(query=True, state=True), "queue_empty": cmds.undoInfo(query=True, undoQueueEmpty=True)}
            disabled["passed"] = disabled["state_inside"] is False and disabled["state_after"] is False and disabled["queue_empty"]
            result["checks"].append(disabled)
            result["status"] = "passed" if all(item["passed"] for item in result["checks"]) else "failed"
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            if recording is not None:
                recording.stop()
            if command_callback is not None:
                om.MMessage.removeCallback(command_callback)
            (directory / "commands.json").write_text(json.dumps(command_trace, ensure_ascii=False, indent=2), encoding="utf-8")
            result["frames"] = frame[0]
            cmds.undoInfo(state=True)
            (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            finished(result)

    sequence = exercise()

    def advance():
        """標準Script Editorの実行がMayaのidleで完了してから次へ進む。"""
        try:
            delay = next(sequence)
        except StopIteration:
            return
        if delay < 0:
            cmds.evalDeferred(advance, lowestPriority=True)
        else:
            QtCore.QTimer.singleShot(delay, advance)

    advance()
