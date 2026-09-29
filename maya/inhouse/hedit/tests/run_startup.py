"""専用設定のMayaを起動し直して、プラグインのロードだけで画面が復元されることを検証する。

版ごとに、右ドックで保存する3段階(write・read・closed)と、フローティングのまま保存する2段階
(float_write・float_read)を、それぞれ別の専用設定フォルダーで行う(計5回起動)。
中身の検証は ``startup_smoke.py``。引数で版を指定する(省略時は2024と2027)。
"""
import datetime
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_hlib_gui_versions import run_version

directory = ROOT / '.maya-output/hedit-startup' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
modules = directory / 'modules'
modules.mkdir(parents=True)
definition = (ROOT / 'maya/modules/hedit.mod').read_text(encoding='ascii').replace('../inhouse/hedit', PROJECT.as_posix())
(modules / 'hedit.mod').write_text(definition, encoding='utf-8')
results = []
for version in sys.argv[1:] or ['2024', '2027']:
    # 右ドックで保存する3段階と、フローティングのまま保存する2段階を、別の専用設定フォルダーで行う。
    for first, stages in (('write', ('write', 'read', 'closed')), ('float_write', ('float_write', 'float_read'))):
        for stage in stages:
            outcome = run_version(version, directory / version / stage, Path('C:/Program Files/Autodesk'), 120,
                                  shutdown_timeout=60, suite_path=PROJECT / 'tests/startup_smoke.py',
                                  environment={'MAYA_MODULE_PATH': str(modules), 'HEDIT_SESSION_STAGE': stage,
                                               'MAYA_APP_DIR': str(directory / version / first / 'maya_app'),
                                               'HEDIT_SESSION_FILE': str(directory / version / first / 'tabs.json')})
            results.append(outcome)
            print(json.dumps(outcome), flush=True)
            if outcome['status'] != 'passed':
                break
(directory / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(directory)
sys.exit(0 if all(r['status'] == 'passed' for r in results) else 1)
