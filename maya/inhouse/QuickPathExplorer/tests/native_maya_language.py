"""専用Maya GUIで言語切替・ドック・内部IDと他UIへの非干渉を検証する。"""

import json
import os
from pathlib import Path
import runpy
import time


def main(output_dir, request):
    """専用prefsを持つハーネスから呼ぶ。実OS入力とは区別する。

    Args:
        output_dir: .maya-output内の専用出力先。
        request: phaseと配置を指定する検証要求。

    Returns:
        検査値・環境・合否を持つ辞書。失敗はAssertionErrorで中断する。
    """
    phase = request.get("phase", "cycle")
    if phase not in ("show", "cycle", "multiFilePrompt", "smoke", "bottomDock", "sharedTabs", "resize", "diagnoseDock", "prepareInput", "inputSnapshot", "dpi"):
        raise ValueError("Unsupported language validation phase")
    from maya import cmds, OpenMayaUI
    try:
        from PySide6 import QtCore, QtWidgets
        from shiboken6 import isValid, wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtWidgets
        from shiboken2 import isValid, wrapInstance

    out = Path(output_dir).resolve()
    settings_path = Path(os.environ.get("QPE_SETTINGS_FILE", "")).resolve()
    if ".maya-output" not in out.parts or Path(os.environ.get("QPE_LANGUAGE_VALIDATION", "")).resolve() != out:
        raise RuntimeError("Dedicated language validation environment required")
    if settings_path.parent != out:
        raise ValueError("Settings must stay inside the dedicated output directory")
    prefs_root = Path(os.environ.get("MAYA_APP_DIR", "")).resolve()
    if ".maya-output" not in prefs_root.parts:
        raise RuntimeError("Dedicated Maya prefs under .maya-output are required")
    try:
        Path(cmds.internalVar(userPrefDir=True)).resolve().relative_to(prefs_root)
    except ValueError:
        raise RuntimeError("The running Maya is not using the dedicated prefs")
    app = QtWidgets.QApplication.instance()
    year = cmds.about(version=True)[:4]
    root = Path(__file__).resolve().parents[1]
    control = "QuickPathExplorerWorkspaceControl"
    plugin = root / "release/plug-ins/windows" / year / "quickPathExplorer.mll"
    if request.get("phase") in ("smoke", "bottomDock", "sharedTabs", "resize"):
        phase = request["phase"]
        suite_out = out / "persistent-suites" / (phase + "-" + str(int(time.time())))
        suite_out.mkdir(parents=True)
        original_settings = os.environ["QPE_SETTINGS_FILE"]
        try:
            os.environ["QPE_TEST_PRODUCT"] = "1"
            os.environ["QPE_NATIVE_KEEP_LOADED"] = "1"
            if phase == "smoke":
                if request.get("fbx"):
                    (suite_out.parent / "fbx.request").write_text("FBX", encoding="utf-8")
                return runpy.run_path(str(Path(__file__).with_name("native_maya_smoke.py")))["main"](suite_out)
            return runpy.run_path(str(Path(__file__).with_name("native_maya_gui.py")))["main"](suite_out, {"phase": phase})
        finally:
            os.environ["QPE_SETTINGS_FILE"] = original_settings
    fixture = out / "fixture"
    fixture.mkdir(exist_ok=True)
    (fixture / "Open.txt").write_text("Keep user text", encoding="utf-8")
    (fixture / "日本語フォルダー").mkdir(exist_ok=True)

    def settle(milliseconds=150):
        """Qtの配送を待ち、Mayaの遅延生成を完了させる。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def browser():
        """破棄前のPySideラッパーを保持せず毎回取得する。"""
        matches = [w for w in app.allWidgets() if isValid(w) and w.objectName() == "qpeNativeWindow"]
        if len(matches) != 1:
            raise AssertionError("Expected exactly one QPE browser")
        return matches[0]

    def wait_ready():
        """ファイル列挙の完了を、GUIイベントを維持して待つ。"""
        limit = time.monotonic() + 20
        while time.monotonic() < limit:
            widget = browser()
            files = widget.findChild(QtWidgets.QTreeView, "files")
            if any(files.model().index(row, 0).data() == "Open.txt" for row in range(files.model().rowCount())):
                return
            settle(50)
        raise AssertionError("Dedicated file enumeration timed out")

    if phase == "inputSnapshot":
        # 入力後のフィルターを変えずに観測する。Open.txtが絞り込まれて消えても待機しない。
        current = browser()
        return {"passed": True, "maya": year, "filter": current.findChild(QtWidgets.QLineEdit, "fileFilter").text(),
                "address": current.findChild(QtWidgets.QLineEdit, "address").text(), "path": cmds.quickPathExplorer("-status"),
                "scene": cmds.file(query=True, sceneName=True), "file_rows": current.findChild(QtWidgets.QTreeView, "files").model().rowCount(),
                "dock_height": cmds.workspaceControl(control, query=True, height=True),
                "floating": cmds.workspaceControl(control, query=True, floating=True)}
    if not cmds.pluginInfo("quickPathExplorer", query=True, loaded=True):
        cmds.loadPlugin(plugin.as_posix(), quiet=True)
    cmds.quickPathExplorer("-path", fixture.as_posix())
    # シーンやユーザー設定は専用環境だけ。絞り込み入力の検証後でも次のケースを開始できる。
    # C++専用クラスのPySide親ラッパーを、子への呼び出しが終わるまで保持する。
    # 一時的な親ラッパーが先に解放されると、生存中のC++の子まで無効化される。
    current = browser()
    current.findChild(QtWidgets.QLineEdit, "fileFilter").clear()
    wait_ready()
    if request.get("phase") == "show":
        return {"passed": True, "maya": year, "pid": os.getpid(), "phase": "show"}
    if request.get("phase") == "prepareInput":
        # データ準備だけをQtで行い、この後の文字入力はWindowsの実入力で検証する。
        for index in range(60):
            (fixture / ("素材_" + str(index + 1).zfill(2))).mkdir(exist_ok=True)
            (fixture / ("メモ_" + str(index + 1).zfill(2) + ".txt")).write_text("入力確認", encoding="utf-8")
        cmds.quickPathExplorer("-refresh")
        cmds.workspaceControl(control, edit=True, floating=True, resizeWidth=1100, resizeHeight=760)
        settle(1000)
        current = browser()
        surfaces = [widget for widget in app.topLevelWidgets() if isValid(widget) and widget.objectName() != "MayaWindow" and widget.isAncestorOf(current)]
        assert len(surfaces) == 1
        surfaces[0].move(app.primaryScreen().availableGeometry().topLeft() + QtCore.QPoint(40, 80))
        settle(300)
        return {"passed": True, "maya": year, "pid": os.getpid(), "evidence": "Qt setup only; OS input follows"}
    if phase == "dpi":
        screens = [{"name": screen.name(), "geometry": [screen.geometry().x(), screen.geometry().y(), screen.geometry().width(), screen.geometry().height()],
                    "dpr": screen.devicePixelRatio(), "logical_dpi": screen.logicalDotsPerInch()} for screen in app.screens()]
        cmds.workspaceControl(control, edit=True, floating=True)
        settle(500)
        current = browser()
        surfaces = [widget for widget in app.topLevelWidgets() if isValid(widget) and widget.objectName() != "MayaWindow" and widget.isAncestorOf(current)]
        assert len(surfaces) == 1
        surface = surfaces[0]
        records = []
        for index, screen in enumerate(app.screens()):
            surface.move(screen.availableGeometry().topLeft() + QtCore.QPoint(40, 80))
            surface.resize(1050, 700)
            settle(1000)
            current = browser()
            assert current.width() > 900 and current.height() > 500
            files = current.findChild(QtWidgets.QTreeView, "files")
            assert files.isVisible()
            assert current.findChild(QtWidgets.QLineEdit, "address").height() >= current.fontMetrics().height()
            records.append({"screen": surface.screen().name(), "dpr": surface.devicePixelRatioF(),
                            "font_height": current.fontMetrics().height(), "size": [current.width(), current.height()]})
            surface.grab().save(str(out / ("dpi-" + str(index) + ".png")))
        assert len(set(record["screen"] for record in records)) == len(app.screens())
        return {"passed": True, "maya": year, "screens": screens, "records": records,
                "evidence": "real monitor transition by Qt move; not physical mouse drag"}
    if request.get("phase") == "diagnoseDock":
        item = wrapInstance(int(OpenMayaUI.MQtUtil.findControl(control)), QtWidgets.QWidget)
        rows = []
        for widget in app.allWidgets():
            if not isValid(widget) or not isinstance(widget, QtWidgets.QSplitter) or widget.orientation() != QtCore.Qt.Vertical:
                continue
            for index in range(widget.count()):
                row = widget.widget(index)
                if isValid(row) and (row == item or row.isAncestorOf(item)):
                    rows.append({"name": widget.objectName(), "visible": widget.isVisible(), "size": [widget.width(), widget.height()],
                                 "row": row.objectName(), "row_visible": row.isVisible(), "index": index,
                                 "row_size": [row.width(), row.height()], "sizes": widget.sizes()})
        result = {"passed": True, "query_height": cmds.workspaceControl(control, query=True, height=True),
                  "floating": cmds.workspaceControl(control, query=True, floating=True),
                  "control": {"name": item.objectName(), "class": item.metaObject().className(), "height": item.height(), "visible": item.isVisible()},
                  "candidates": rows}
        browser().grab().save(str(out / "dock-current.png"))
        return result
    if request.get("phase") == "multiFilePrompt":
        cmds.file(new=True, force=True)
        cmds.createNode("transform", name="qpeMultiFixture")
        for name in ("first.mb", "second.mb"):
            cmds.file(rename=(fixture / name).as_posix())
            cmds.file(save=True, type="mayaBinary")
        cmds.file(new=True, force=True)
        prompts = []
        for language in ("en", "ja"):
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["uiLanguage"] = language
            settings_path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
            cmds.quickPathExplorer()
            wait_ready()
            current = browser()
            files = current.findChild(QtWidgets.QTreeView, "files")
            limit = time.monotonic() + 10
            while files.model().rowCount() < 3 and time.monotonic() < limit:
                settle(50)
            files.selectionModel().clearSelection()
            for row in range(files.model().rowCount()):
                index = files.model().index(row, 0)
                if index.data() in ("first.mb", "second.mb"):
                    files.selectionModel().select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
            assert len(files.selectionModel().selectedRows()) == 2
            inspector = current.findChild(QtWidgets.QWidget, "inspector")
            for action, tab in (("import", 1), ("reference", 2)):
                inspector.findChild(QtWidgets.QTabWidget, "readOptions").setCurrentIndex(tab)
                seen = []

                def cancel_prompt():
                    """実際に開いたQPEの確認をCancelし本文を記録する。"""
                    dialog = app.activeModalWidget()
                    if isinstance(dialog, QtWidgets.QMessageBox):
                        seen.append(dialog.text())
                        dialog.button(QtWidgets.QMessageBox.Cancel).click()

                timer = QtCore.QTimer()
                timer.timeout.connect(cancel_prompt)
                timer.start(25)
                try:
                    inspector.findChild(QtWidgets.QPushButton, action).click()
                finally:
                    timer.stop()
                expected = (("2 個のファイルを読み込みますか？" if action == "import" else "2 個のファイルのリファレンスを作成しますか？")
                            if language == "ja" else ("Import 2 files?" if action == "import" else "Reference 2 files?"))
                assert seen == [expected], (seen, expected)
                assert cmds.file(query=True, sceneName=True) == ""
                assert not cmds.objExists("qpeMultiFixture")
                prompts.append({"language": language, "action": action, "text": seen[0], "cancel_preserved_scene": True})
        return {"passed": True, "maya": year, "pid": os.getpid(), "prompts": prompts,
                "evidence": "Maya GUI Qt programmatic; real dialog Cancel, not OS input"}

    palette = app.palette().cacheKey()
    locale = QtCore.QLocale().name()
    scene = cmds.file(query=True, sceneName=True)
    undo = cmds.undoInfo(query=True, state=True)
    panels = sorted(cmds.getPanel(type="modelPanel"))
    foreign = QtWidgets.QLineEdit("Open")
    foreign.setObjectName("qpeLanguageForeignInput")
    result = {"passed": False, "maya": year, "pid": os.getpid(), "qt": QtCore.qVersion(),
              "evidence": "Maya GUI Qt programmatic operations; not OS input", "cycles": []}

    def host_unchanged():
        """Mayaの他画面・シーン・UndoとQPE外の入力を検査する。"""
        assert app.palette().cacheKey() == palette
        assert QtCore.QLocale().name() == locale
        assert foreign.text() == "Open"
        assert cmds.file(query=True, sceneName=True) == scene
        assert cmds.undoInfo(query=True, state=True) == undo
        assert sorted(cmds.getPanel(type="modelPanel")) == panels

    def dock_widget():
        """所有権はMayaへ残し、現在のworkspaceControlを参照する。"""
        return wrapInstance(int(OpenMayaUI.MQtUtil.findControl(control)), QtWidgets.QWidget)

    try:
        for placement in request.get("placements", ["right", "bottom", "floating", "shared"]):
            sibling = "QPELanguageSiblingControl"
            if placement == "floating":
                cmds.workspaceControl(control, edit=True, floating=True)
            elif placement == "shared":
                cmds.workspaceControl(sibling, label="QPE language sibling", retain=False,
                                      dockToMainWindow=("right", False))
                layout = cmds.columnLayout(parent=sibling)
                field = cmds.textField(parent=layout, text="Keep sibling input")
                cmds.workspaceControl(control, edit=True, tabToControl=(sibling, -1))
            else:
                cmds.workspaceControl(control, edit=True, dockToMainWindow=(placement, False))
            settle(1700)
            pointer = int(OpenMayaUI.MQtUtil.findControl(control))
            floating = cmds.workspaceControl(control, query=True, floating=True)
            for language in ("en", "ja", "en", "ja"):
                # 表示文字ではなく、保存した言語キーを変更して実際の再表示経路を通す。
                cmds.workspaceControl(control, edit=True, close=True)
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                settings["uiLanguage"] = language
                settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
                cmds.quickPathExplorer()
                wait_ready()
                settle(100)
                current = browser()
                assert current.property("uiLanguage") == language
                assert int(OpenMayaUI.MQtUtil.findControl(control)) == pointer, "workspaceControl was recreated"
                assert cmds.workspaceControl(control, query=True, floating=True) == floating
                files = current.findChild(QtWidgets.QTreeView, "files")
                assert files.model().headerData(0, QtCore.Qt.Horizontal) == ("名前" if language == "ja" else "Name")
                assert cmds.quickPathExplorer("-status").replace("\\", "/") == fixture.as_posix()
                inspector = current.findChild(QtWidgets.QWidget, "inspector")
                assert inspector.findChild(QtWidgets.QComboBox, "import_mode").itemData(0) == "file"
                assert inspector.findChild(QtWidgets.QComboBox, "reference_mode").itemData(1) == "custom"
                assert inspector.findChild(QtWidgets.QComboBox, "fbx_mode").itemData(3) == "exmerge"
                if placement == "shared":
                    shared = [w for w in app.allWidgets() if isValid(w) and isinstance(w, QtWidgets.QTabWidget)
                              and w.count() > 1 and w.isAncestorOf(dock_widget())
                              and w.isAncestorOf(wrapInstance(int(OpenMayaUI.MQtUtil.findControl(sibling)), QtWidgets.QWidget))]
                    assert shared, "Language switch detached shared tab"
                    assert cmds.textField(field, query=True, text=True) == "Keep sibling input"
                host_unchanged()
                result["cycles"].append({"placement": placement, "language": language, "passed": True})
            if placement == "bottom":
                # Qtの実splitterを縮める。親部品のminimumSizeは変更しない。
                item = dock_widget()
                matches = []
                for widget in app.allWidgets():
                    if not isValid(widget) or not isinstance(widget, QtWidgets.QSplitter) or not widget.isVisible() or widget.orientation() != QtCore.Qt.Vertical:
                        continue
                    for index in range(widget.count()):
                        row = widget.widget(index)
                        if isValid(row) and row.isVisible() and (row == item or row.isAncestorOf(item)):
                            matches.append((widget, row, index))
                assert matches
                result["bottom_candidates"] = [{"name": widget.objectName(), "visible": widget.isVisible(),
                                                "size": [widget.width(), widget.height()], "index": index,
                                                "row": row.objectName(), "row_visible": row.isVisible(),
                                                "row_size": [row.width(), row.height()]} for widget, row, index in matches]
                splitter, row, index = min(matches, key=lambda value: value[0].width() * value[0].height())
                assert index > 0
                for height in (100, 400, 100):
                    sizes = splitter.sizes()
                    target = height + row.height() - item.height()
                    delta = target - sizes[index]
                    if delta <= 0:
                        sizes[index - 1] -= delta
                    else:
                        # 大きなタイムラインのあるprefsでも検証できるよう、実際に余裕がある隣接行から借りる。
                        # 親の最小寸法を書き換えたり、最小寸法のMainPaneを負数へ縮めたりしない。
                        donors = sorted((i for i in range(len(sizes)) if i != index),
                                        key=lambda i: sizes[i] - max(splitter.widget(i).minimumHeight(), splitter.widget(i).minimumSizeHint().height()), reverse=True)
                        remaining = delta
                        for donor in donors:
                            minimum = max(splitter.widget(donor).minimumHeight(), splitter.widget(donor).minimumSizeHint().height(), 0)
                            take = min(remaining, max(0, sizes[donor] - minimum))
                            sizes[donor] -= take
                            remaining -= take
                        assert remaining == 0, "Dedicated Maya window has insufficient free height"
                    sizes[index] = target
                    splitter.setSizes(sizes)
                    settle(1000)
                    geometry = {"requested": height, "actual": item.height(), "splitter": splitter.sizes(),
                                "minimum": item.minimumHeight(), "hint": item.minimumSizeHint().height(),
                                "row_minimum": row.minimumHeight(), "row_hint": row.minimumSizeHint().height()}
                    result.setdefault("bottom_geometry", []).append(geometry)
                    (out / "bottom-language-geometry.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                    assert item.height() <= 130 if height == 100 else item.height() >= 300, geometry
                result["bottom_resize"] = True
            browser().grab().save(str(out / ("language-" + placement + ".png")))
            if placement == "shared":
                cmds.workspaceControl(control, edit=True, floating=True)
                cmds.deleteUI(sibling)
        result["passed"] = True
        return result
    finally:
        foreign.deleteLater()
