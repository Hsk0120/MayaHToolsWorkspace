"""ビルド済みMaya各版を隔離環境で検証する。生成物は.maya-outputへ保存。"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_hlib_tests import isolated_environment
from _maya_test_process import stop_owned_process


def run(command, env, directory, name, timeout=120):
    """コマンドを実行し、出力を ``<name>.log`` に保存して表示する。

    Args:
        command (list): 実行するコマンドと引数。
        env (dict): 環境変数。
        directory (Path): ログの出力先。
        name (str): ログの名前。
        timeout (int): 待つ秒数。超えたらプロセスを止めて -1 を返す。

    Returns:
        int: 終了コード(0 なら成功)。
    """
    with (directory / (name + '.log')).open('wb') as output:
        process = subprocess.Popen([str(value) for value in command], env=env, cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_owned_process(process)
            code = -1
    print((directory / (name + '.log')).read_text(encoding='utf-8', errors='replace'), flush=True)
    return code


def main():
    """引数の各版(省略時は全5版)で、単体テスト・standalone・offscreen の UI テストを順に実行する。

    Returns:
        int: すべて成功なら 0、それ以外は 1。
    """
    results = []
    output = ROOT / '.maya-output/hedit-tests' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True)
    for version in (sys.argv[1:] or ['2022', '2024', '2025', '2026', '2027']):
        directory = output / version; directory.mkdir()
        executable = Path('C:/Program Files/Autodesk/Maya' + version + '/bin/mayapy.exe')
        env = isolated_environment(executable, directory)
        env['MAYA_MODULE_PATH'] = str(ROOT / 'maya/modules')
        # scripts/はuserSetup.py(起動時のloadPlugin('hedit')だけ)を含む。
        # hedit.*本体(src/python/)はhedit.mllに同梱され、loadPlugin時にsys.modulesへ展開する。
        env['PYTHONPATH'] += os.pathsep + str(PROJECT / 'scripts')
        unit = run([executable, PROJECT / 'tests/test_completion.py'], env, directory, 'unit')
        # 保存先の決定(C++のhedit -sessionPath)は、隔離したMaya設定フォルダーで確かめる。
        unit = unit or run([executable, PROJECT / 'tests/test_session_path.py'], env, directory, 'session_path')
        # C++の宣言の抽出が、以前のPython(ast)と同じ結果になるかを実在のファイルで突き合わせる。
        unit = unit or run([executable, PROJECT / 'tests/test_declarations_parity.py'], env, directory, 'declarations', timeout=300)
        config = directory / 'configuration.json'
        maya = run([executable, PROJECT / 'tests/maya_smoke.py', config], env, directory, 'maya')
        ui = None
        if maya == 0:
            env['QT_QPA_PLATFORM'] = 'offscreen'
            env['QT_PLUGIN_PATH'] = str(executable.parent.parent / 'plugins')
            env['QT_QPA_FONTDIR'] = str(Path(os.environ['WINDIR']) / 'Fonts')
            smoke = ROOT / '.maya-output/plugin-build/hedit' / version / 'Release/hedit_ui_smoke.exe'
            ui = run([smoke, config, directory / 'editor.png'], env, directory, 'ui', timeout=40)
        results.append({'version': version, 'unit': unit, 'maya': maya, 'ui': ui})
    (output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(str(output), flush=True)
    return 0 if all(row['unit'] == row['maya'] == row['ui'] == 0 for row in results) else 1


if __name__ == '__main__':
    sys.exit(main())
