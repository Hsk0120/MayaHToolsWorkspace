"""専用GUIでサイクル画面とシーンパス取得の移行を検証する。"""

import datetime
import json
import os
from pathlib import Path
import sys
import traceback
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def main(output_dir, finished):
    """使い捨てGUIで検証し、実クリップボードには書き込まない。

    Args:
        output_dir (str | Path): 結果保存先。
        finished (Callable): 終了通知。
    """
    if os.environ.get("HLIB_DISPOSABLE_GUI") != "1":
        raise RuntimeError("専用の使い捨てGUIで実行してください。")
    import maya.cmds as cmds
    import test_htools_cycles_gui
    from HTools.rigging import copyCurrentScenePath
    result = {"status": "running", "checks": []}
    try:
        test_htools_cycles_gui.main()
        result["checks"].append("cycle_ui_report_error_recovery")
        with mock.patch.object(copyCurrentScenePath, "QApplication") as application:
            cmds.file(rename=str(Path(output_dir) / "test scene.ma"))
            copyCurrentScenePath.copy_current_scene_path()
            application.instance.return_value.clipboard.return_value.setText.assert_called_once_with(
                cmds.file(query=True, sceneName=True))
            result["checks"].append("scene_path")
            application.reset_mock()
            cmds.file(new=True, force=True)
            copyCurrentScenePath.copy_current_scene_path()
            application.instance.assert_not_called()
            result["checks"].append("unsaved_scene")
        result["status"] = "passed"
    except Exception:
        result.update(status="failed", error=traceback.format_exc())
    (Path(output_dir) / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    finished(result)


if __name__ == "__main__":
    from run_hlib_gui_versions import run_version
    output = ROOT / ".maya-output/htools-migration-gui" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result = run_version("2027", output, Path("C:/Program Files/Autodesk"), 180,
                         suite_path=Path(__file__).resolve(), environment={"HLIB_DISPOSABLE_GUI": "1"})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "passed" else 1)
