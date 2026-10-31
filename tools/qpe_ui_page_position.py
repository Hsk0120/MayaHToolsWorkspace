"""狭幅詳細ページの末端追従と手動祖先位置の保持を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished):
    """実際のMaya内QPEを広幅から狭幅へ切り替える。"""
    import qpeHost
    out = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'Project'
    leaf = root / 'Assets/Characters/Hero/Model/Work/Delivery'
    (leaf / 'Child').mkdir(parents=True, exist_ok=True)
    checks = []
    try:
        e = qpeHost.show(str(root))
        window = e._dockViewport.window()
        pause(800)
        window.resize(1700, 820)
        e.setBrowseRoot(str(root))
        e.navigate(str(leaf))
        e.sidebarButton.setChecked(False)
        e.inspectorButton.setChecked(True)
        pause(700)
        bar = e.columns.horizontalScrollBar()
        assert bar.maximum() == 0, bar.maximum()
        window.resize(600, 820)
        pause(400)
        assert abs(e._dockViewport.width() - 600) <= 8
        assert e.modern.inspectorPage
        e.inspectorButton.setChecked(False)
        pause(400)
        waitFor(lambda: e._resumeHorizontal is None)
        assert bar.maximum() > 0 and bar.value() == bar.maximum(), (bar.value(), bar.maximum())
        checks.append('All columns visible -> narrow detail -> return keeps right edge')
        for position in (0, bar.maximum() // 2):
            bar.setValue(position)
            e.inspectorButton.setChecked(True)
            pause(250)
            e.inspectorButton.setChecked(False)
            pause(400)
            waitFor(lambda: e._resumeHorizontal is None)
            assert bar.value() == position, (position, bar.value())
            e.columns.fitColumns()
            pause(200)
            assert bar.value() == position, (position, bar.value())
            checks.append('Manual position survives detail and redraw: ' + str(position))
        result = {'status': 'passed', 'checks': checks, 'input': 'Maya GUI Qt programmatic resize'}
        window.grab().save(str(out / 'result.png'))
    except Exception:
        result = {'status': 'failed', 'checks': checks, 'error': traceback.format_exc()}
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(result)
