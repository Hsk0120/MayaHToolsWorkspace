"""固定の配布mllから既存QPE回帰を専用Mayaで実行する。"""
import argparse
import json
from pathlib import Path
import sys


def main():
    """ユーザーMayaを使わず、試験用prefsと配布物で各スイートを実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--version', default='2027', choices=['2022', '2023', '2024', '2025', '2026', '2027'])
    parser.add_argument('--suites', nargs='+', default=['qpe_native_smoke'])
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    if not out.is_relative_to(root / '.maya-output'):
        raise ValueError('Native verification output must be inside .maya-output')
    out.mkdir(parents=True, exist_ok=True)
    project = root / 'maya/inhouse/QuickPathExplorer'
    plugin = project / 'release/plug-ins/windows' / args.version / 'quickPathExplorer.mll'
    if not plugin.is_file():
        raise FileNotFoundError(plugin)
    # MCEと同様、配布物の固定パスをモジュールから参照する。信頼設定は変更しない。
    # 旧Python版のuserSetupを読まず、外部.pyなしの埋込実装を検査する。
    modules = out / 'modules'
    modules.mkdir(exist_ok=True)
    module_text = (root / 'maya/modules/QuickPathExplorer.mod').read_text(encoding='utf-8')
    (modules / 'QuickPathExplorer.mod').write_text(
        module_text.replace('../inhouse/QuickPathExplorer', project.as_posix()), encoding='utf-8')
    sys.path.insert(0, str(root / 'maya/inhouse/mlib/__tests__'))
    from runGui import run_version
    summary = {}
    for name in args.suites:
        suite = Path(name).resolve() if name.endswith('.py') else root / 'tools' / (name + '.py')
        key = suite.stem
        bootstrap = out / ('bootstrap_' + key + '.py')
        bootstrap.write_text(
            "import os, sys, runpy\nfrom maya import cmds\n"
            "os.environ['QPE_SETTINGS_FILE'] = {!r}\n"
            "cmds.loadPlugin('quickPathExplorer')\n"
            "assert cmds.pluginInfo('quickPathExplorer', query=True, path=True).replace('\\\\', '/') == {!r}\n"
            "import qpeNative\nassert qpeNative.available()\n"
            "sys.path.insert(0, {!r})\n"
            "main = runpy.run_path({!r})['main']\n".format(
                str(out / key / 'settings.json'), plugin.as_posix(), str(root / 'tools'), str(suite)), encoding='utf-8')
        try:
            result = run_version(args.version, out / key, Path('C:/Program Files/Autodesk'), args.timeout,
                                 shutdown_timeout=45, suite_path=bootstrap,
                                 environment={'MAYA_MODULE_PATH': str(modules)})
        except OSError as error:
            # 後始末に失敗しても証拠と結果を残し、次のMayaを重複起動しない。
            result = dict(status='failed', error=str(error), evidence=str(out / key))
        summary[key] = result
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(key, result['status'], flush=True)
        if result['status'] != 'passed':
            break
    return 0 if all(row['status'] == 'passed' for row in summary.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
