"""独立プロセスでQPEの回帰テストを順番に実行し、結果を集約する。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


SUITES = ['open', 'audit', 'navigation', 'context', 'p0', 'finder', 'ux',
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
                    from run_mlib_gui_versions import run_version
                    suite = name if name.startswith('qpe_') else 'qpe_ui_'+name
                    outcome = run_version(args.maya, target, Path('C:/Program Files/Autodesk'), 240,
                                          shutdown_timeout=45, suite_path=root/'tools'/(suite+'.py'))
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
                process = subprocess.run([args.python, str(root/'tools'/('qpe_ui_'+name+'.py')),
                                          str(target)], cwd=str(root), stdout=log,
                                         stderr=subprocess.STDOUT, timeout=180)
                result_file = target/'result.json'
                result = json.loads(result_file.read_text(encoding='utf8')) if result_file.exists() else {}
                summary[name] = dict(exitCode=process.returncode, result=result)
            except subprocess.TimeoutExpired:
                summary[name] = dict(status='timeout')
        (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
        print(name, summary[name].get('exitCode', 'timeout'), flush=True)


if __name__ == '__main__':
    main()
