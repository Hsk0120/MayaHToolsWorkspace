"""専用Mayaを終了・再起動して復元を確認する。"""
import datetime
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_mlib_gui_versions import run_version

directory = ROOT / '.maya-output/mce-session' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
modules = directory / 'modules'
modules.mkdir(parents=True)
definition = (ROOT / 'maya/modules/MayaCodeEditor.mod').read_text(encoding='ascii').replace('../inhouse/MayaCodeEditor', PROJECT.as_posix())
(modules / 'MayaCodeEditor.mod').write_text(definition, encoding='utf-8')
results = []
for version in sys.argv[1:] or ['2024', '2027']:
    for stage in ('write', 'read'):
        outcome = run_version(version, directory / version / stage, Path('C:/Program Files/Autodesk'), 120,
                              shutdown_timeout=60, suite_path=PROJECT / 'tests/session_smoke.py',
                              environment={'MAYA_MODULE_PATH': str(modules), 'MCE_TEST_COMMANDS': '1', 'MCE_SESSION_STAGE': stage,
                                           'MCE_SESSION_FILE': str(directory / version / 'tabs.json')})
        results.append(outcome)
        print(json.dumps(outcome), flush=True)
        if outcome['status'] != 'passed':
            break
(directory / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(directory)
sys.exit(0 if all(r['status'] == 'passed' for r in results) else 1)
