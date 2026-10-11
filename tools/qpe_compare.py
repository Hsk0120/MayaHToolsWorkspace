"""同一データでQuickPathExplorerの単体EXE/PythonとMaya内を比較する。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'maya/inhouse/QuickPathExplorer'
MAYA = Path('C:/Program Files/Autodesk/Maya2027')
sys.path.insert(0, str(PROJECT / 'python'))
from qpeMetrics import memory


def prepare(directory):
    """計測用の小・中・大フォルダーと12段階の階層を作る。

    Args:
        directory (Path): この実行だけの生成先。

    Returns:
        Path: 共通シナリオJSON。
    """
    data = directory / 'data'
    cases = []
    for count in (100, 1000, 10000):
        folder = data / ('files_' + str(count))
        folder.mkdir(parents=True)
        for index in range(count):
            (folder / ('asset_{:05d}.ma'.format(index))).write_text('// benchmark placeholder\n', encoding='utf-8')
        cases.append(dict(name='load_' + str(count), path=folder.as_posix(), count=count))
    deep = data / 'deep'
    deep.mkdir()
    cases.append(dict(name='deep_root', path=deep.as_posix(), count=1))
    for level in range(12):
        deep /= 'level_{:02d}'.format(level)
        deep.mkdir()
        (deep / 'leaf.txt').write_text('fixture', encoding='utf-8')
        cases.append(dict(name='depth_{:02d}'.format(level), path=deep.as_posix(), count=2 if level < 11 else 1, mode='select'))
    for count in (100, 1000, 10000):
        cases.append(dict(name='revisit_' + str(count), path=(data / ('files_' + str(count))).as_posix(), count=count))
    check = data / '日本語 folder'
    (check / 'subfolder').mkdir(parents=True)
    (check / '日本語 scene.ma').write_text('// fixture only\n', encoding='utf-8')
    (check / 'image.txt').write_text('fixture', encoding='utf-8')
    config = directory / 'config.json'
    config.write_text(json.dumps(dict(cases=cases, check_path=check.as_posix()), ensure_ascii=False), encoding='utf-8')
    return config


def main():
    """交互順で単体計測し、専用Maya GUIでも同じケースを実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--skip-maya', action='store_true')
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    directory = ROOT / '.maya-output/qpe' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    directory.mkdir(parents=True)
    config = prepare(directory)
    env = os.environ.copy()
    env['PATH'] = str(MAYA / 'bin') + os.pathsep + env['PATH']
    env['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(MAYA / 'plugins/platforms')
    exe = ROOT / '.maya-output/plugin-build/QuickPathExplorer/2027/Release/QuickPathExplorer.exe'
    results = []
    print('Evidence: ' + str(directory), flush=True)
    for round_index in range(args.rounds):
        for language in (('cpp', 'python') if round_index % 2 == 0 else ('python', 'cpp')):
            output = directory / ('standalone_{}_{}.json'.format(language, round_index))
            ready = output.with_suffix('.ready')
            command = [str(exe)] if language == 'cpp' else [str(MAYA / 'bin/mayapy.exe'), str(PROJECT / 'python/qpePrototype.py')]
            command += ['--bench', str(config), str(output), str(ready)]
            start = time.perf_counter()
            with output.with_suffix('.log').open('w') as log:
                process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                startup = None
                peak_memory = 0
                while process.poll() is None:
                    try:
                        peak_memory = max(peak_memory, memory(int(process._handle))['peak_working_set_mib'])
                    except OSError:
                        pass
                    if startup is None and ready.exists():
                        startup = (time.perf_counter() - start) * 1000
                    if time.perf_counter() - start > 180:
                        process.kill()
                        process.wait()
                        raise TimeoutError(str(output))
                    time.sleep(.005)
            if process.returncode or not output.exists():
                raise RuntimeError('Failed: {} (exit {}). {}'.format(output, process.returncode,
                    output.with_suffix('.log').read_text(errors='replace')))
            result = json.loads(output.read_text())
            result.update(host='standalone', round=round_index, startup_ms=startup, peak_working_set_mib=peak_memory)
            results.append(result)
            (directory / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(language, round_index, result['passed'], 'startup_ms', startup, flush=True)
    if not args.skip_maya:
        from run_mlib_gui_versions import run_version
        maya_result = run_version('2027', directory / 'maya', MAYA.parent, 240, shutdown_timeout=60,
            suite_path=ROOT / 'tools/qpe_maya_suite.py',
            environment={'QPE_CONFIG': str(config), 'QPE_ROUNDS': str(args.rounds)})
        (directory / 'maya-run.json').write_text(json.dumps(maya_result, indent=2), encoding='utf-8')
        print('Maya:', maya_result['status'], flush=True)
        if maya_result['status'] != 'passed':
            raise RuntimeError(maya_result)
        results.extend(maya_result['measurements'])
    summary = []
    for host in ('standalone', 'maya'):
        for language in ('cpp', 'python'):
            subset = [r for r in results if r['host'] == host and r['implementation'] == language]
            if not subset:
                continue
            metrics = {}
            for name in [c['name'] for c in subset[0]['cases']]:
                values = [c['ms'] for r in subset for c in r['cases'] if c['name'] == name]
                metrics[name] = dict(median_ms=statistics.median(values), min_ms=min(values), max_ms=max(values))
            startup = [r['startup_ms'] for r in subset if r.get('startup_ms') is not None]
            summary.append(dict(host=host, implementation=language, rounds=len(subset),
                startup_median_ms=statistics.median(startup) if startup else None, metrics=metrics))
    (directory / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
