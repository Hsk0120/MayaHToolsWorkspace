"""狭い詳細ペインでも保存・読込欄へスクロールで到達できることを検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """詳細欄の実寸とスクロール可能範囲を検査する。"""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    from qpeQt import QtCore, QtWidgets
    from qpe_ui_maya import pause
    import qpeHost

    out = Path(output_dir)
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    result = {"status": "error", "geometry": [], "checks": []}
    try:
        e = qpeHost.show(str(out))
        e.window().resize(620, 700)
        e.setInspectorVisible(True)
        pause(400)
        e.window().resize(620, 700)
        pause(400)
        for label, page in (("selected", e.readPanel), ("save", e.savePanel)):
            e.operationTabs.setCurrentWidget(page)
            e.outer.setSizes([0, 340, 240])
            pause(350)
            scroll = e.inspectorScroll
            bar = scroll.horizontalScrollBar()
            row = {"page": label, "panel": e.actionsPanel.width(),
                   "dockViewport": e._dockViewport.viewport().width(), "explorer": e.width(),
                   "viewport": scroll.viewport().width(), "body": scroll.widget().width(),
                   "overflow": bar.maximum(), "barVisible": bar.isVisible()}
            result["geometry"].append(row)
            e._dockViewport.viewport().grab().save(str(out / (label + ".png")))
            assert e.actionsPanel.width() <= 300, row
            assert e.search.width() >= 100, {"searchWidth": e.search.width(), "geometry": row}
            assert not e.folderLabel.isVisible()
            assert e.modern.button.text() == "View"
            if row["body"] > row["viewport"]:
                assert bar.isVisible() and bar.maximum() > 0, row
                bar.setValue(bar.maximum())
                pause(100)
                assert scroll.widget().x() < 0, row
            result["checks"].append(label + ": details fit or scroll, search remains at least 100px")
        e.setInspectorVisible(False)
        e.window().resize(1400, 850)
        pause(500)
        assert e.folderLabel.isVisible() and e.modern.button.text().startswith("View · ")
        result["checks"].append("Wide layout restores folder summary and full view label")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finished(result)
