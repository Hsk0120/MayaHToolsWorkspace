"""独立プロセスでQPEの回帰テストを順番に実行し、結果を集約する。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


SUITES = ['open', 'audit', 'navigation', 'context', 'p0', 'finder', 'shortcuts', 'ux',
          'inspector', 'theme', 'tabs', 'sidebars', 'organizer', 'advanced', 'productivity', 'performance', 'scene']


def main():
    """GUIのフォーカスが競合しないよう、各スイートを個別に起動する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--maya', choices=['2022', '2027'])
    parser.add_argument('--suites', nargs='+', default=SUITES)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name in args.suites:
        target = out/name
        if not args.maya:
            target.mkdir(exist_ok=True)
        with ((out/(name+'.log')) if args.maya else (target/'process.log')).open('w', encoding='utf8') as log:
            try:
                if args.maya:
                    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
                    from runGui import run_version
                    suite = name if name.startswith('qpe_') else 'qpe_ui_'+name
                    # runpyはスイートの親フォルダーをsys.pathへ追加しない。
                    # 隔離Mayaでも同じtools内の共通補助を読めるようにする。
                    bootstrap = out / ('bootstrap_' + name + '.py')
                    bootstrap.write_text(
                        'import runpy\nimport sys\n'
                        'sys.path.insert(0, {!r})\n'
                        'main = runpy.run_path({!r})["main"]\n'.format(
                            str(root / 'tools'), str(root / 'tools' / (suite + '.py'))),
                        encoding='utf-8')
                    outcome = run_version(args.maya, target, Path('C:/Program Files/Autodesk'), 240,
                                          shutdown_timeout=45, suite_path=bootstrap)
                    summary[name] = outcome
                    dumps = [str(path) for path in target.rglob('*.dmp')]
                    outcome['crashDumps'] = dumps
                    if dumps:
                        outcome['status'] = 'failed'
                        outcome['shutdownError'] = 'Maya generated a crash dump despite test completion'
                    log.write(json.dumps(outcome, ensure_ascii=False, indent=2))
                    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
                    print(name, outcome['status'], flush=True)
                    continue
                with tempfile.TemporaryDirectory(prefix='working-', dir=str(target)) as working:
                    process = subprocess.run([args.python, str(root/'tools'/('qpe_ui_'+name+'.py')),
                                              str(target)], cwd=working, stdout=log,
                                             stderr=subprocess.STDOUT, timeout=180)
                result_file = target/'result.json'
                result = json.loads(result_file.read_text(encoding='utf8')) if result_file.exists() else {}
                summary[name] = dict(exitCode=process.returncode, result=result)
            except subprocess.TimeoutExpired:
                summary[name] = dict(status='timeout')
        (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
        print(name, summary[name].get('exitCode', 'timeout'), flush=True)
    if args.maya:
        return 0 if all(row.get('status') == 'passed' for row in summary.values()) else 1
    return 0 if all(row.get('exitCode') == 0 and row.get('result', {}).get('status') == 'passed'
                    for row in summary.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
