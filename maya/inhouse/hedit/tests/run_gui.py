"""専用のMaya GUIで実行する。セキュリティ確認の自動承認はしない。"""
import datetime
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_hlib_gui_versions import run_version

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', nargs='?', default='2027', choices=['2022', '2024', '2025', '2026', '2027'])
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--shutdown-timeout', type=int, default=30)
    parser.add_argument('--suite', choices=['gui_smoke.py', 'completion_output_smoke.py', 'formatting_spelling_smoke.py', 'output_format_smoke.py'], default='gui_smoke.py')
    args = parser.parse_args()
    if args.timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error('timeouts must be positive')
    directory = ROOT / '.maya-output/hedit-gui' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    modules = directory.with_name(directory.name + '-modules')
    modules.mkdir(parents=True)
    definition = (ROOT / 'maya/modules/hedit.mod').read_text(encoding='ascii')
    definition = definition.replace('../inhouse/hedit', PROJECT.as_posix())
    (modules / 'hedit.mod').write_text(definition, encoding='utf-8')
    print('GUI evidence: ' + str(directory), flush=True)
    result = run_version(args.version, directory,
                         Path('C:/Program Files/Autodesk'), args.timeout, shutdown_timeout=args.shutdown_timeout,
                         suite_path=PROJECT / 'tests' / args.suite,
                         environment={'MAYA_MODULE_PATH': str(modules)})
    # GUI処理の成功を、終了時の停止によって見失わない。終了異常は非ゼロで通知する。
    suite_path = directory / 'result.json'
    if suite_path.exists():
        result['suite'] = json.loads(suite_path.read_text(encoding='utf-8'))
    (directory / 'run-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    sys.exit(0 if result['status'] == 'passed' else 1)
