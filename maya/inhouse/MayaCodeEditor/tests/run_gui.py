"""専用のMaya GUIで実行する。セキュリティ確認の自動承認はしない。"""
import datetime
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "maya/inhouse/mlib/__tests__"))
from runGui import run_version

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', nargs='?', default='2027', choices=['2022', '2023', '2024', '2025', '2026', '2027'])
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--shutdown-timeout', type=int, default=30)
    parser.add_argument('--manual-focus', action='store_true', help='検索テスト開始前に、専用画面の開始ボタンをクリックして前面化する')
    parser.add_argument('--suite', choices=['output_appearance_smoke.py', 'execution_undo_smoke.py', 'search_navigation_smoke.py', 'editing_selection_smoke.py', 'language_smoke.py', 'recovery_failure_smoke.py', 'gui_smoke.py', 'completion_output_smoke.py', 'completion_scope_smoke.py', 'formatting_spelling_smoke.py', 'output_format_smoke.py', 'output_fallback_smoke.py', 'vscode_features_smoke.py', 'perf_smoke.py', 'dock_resize_smoke.py', 'restore_order_smoke.py'], default='gui_smoke.py')
    args = parser.parse_args()
    if args.timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error('timeouts must be positive')
    if args.manual_focus and args.suite != 'search_navigation_smoke.py':
        parser.error('--manual-focus requires search_navigation_smoke.py')
    directory = ROOT / '.maya-output/mce-gui' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    modules = directory.with_name(directory.name + '-modules')
    modules.mkdir(parents=True)
    definition = (ROOT / 'maya/modules/MayaCodeEditor.mod').read_text(encoding='ascii')
    definition = definition.replace('../inhouse/MayaCodeEditor', PROJECT.as_posix())
    (modules / 'MayaCodeEditor.mod').write_text(definition, encoding='utf-8')
    print('GUI evidence: ' + str(directory), flush=True)
    result = run_version(args.version, directory,
                         Path('C:/Program Files/Autodesk'), args.timeout, shutdown_timeout=args.shutdown_timeout,
                         suite_path=PROJECT / 'tests' / args.suite,
                         environment={'MAYA_MODULE_PATH': str(modules), 'MCE_TEST_COMMANDS': '1', 'MCE_PROJECT_ROOT': str(directory), 'MCE_LANGUAGE_TRACE': str(directory / 'language.jsonl'), 'MCE_TEST_MANUAL_FOCUS': '1' if args.manual_focus else '0'})
    # GUI処理の成功を、終了時の停止によって見失わない。終了異常は非ゼロで通知する。
    suite_path = directory / 'result.json'
    if suite_path.exists():
        result['suite'] = json.loads(suite_path.read_text(encoding='utf-8'))
    (directory / 'run-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2), flush=True)
    sys.exit(0 if result['status'] == 'passed' else 1)
