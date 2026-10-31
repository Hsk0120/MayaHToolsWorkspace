"""Maya不要のQuickPathExplorer配布フォルダーを隔離環境で作る。"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main():
    """ワークスペース内の専用venvと生成先だけを使用する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-project', action='store_true',
                        help='Copy the executable and _internal into the QuickPathExplorer project folder')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = root / 'maya/inhouse/QuickPathExplorer'
    build = root / '.maya-output/qpe-standalone-build'
    environment = build / 'venv'
    if not (environment / 'Scripts/python.exe').exists():
        venv.EnvBuilder(with_pip=True).create(str(environment))
    python = environment / 'Scripts/python.exe'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(project / 'requirements.txt'), 'pyinstaller>=6,<7'], check=True)
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_PLUGIN_PATH', 'MAYA_LOCATION'):
        env.pop(key, None)
    # 他アプリの同名ICU DLLを収集しないよう、Windows標準と専用Pythonだけを探索する。
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    env['PATH'] = os.pathsep.join((str(environment / 'Scripts'), str(windows / 'System32'), str(windows)))
    subprocess.run([str(python), '-m', 'PyInstaller', '--clean', '--noconfirm', '--windowed', '--onedir',
                    '--name', 'QuickPathExplorer', '--distpath', str(build / 'dist'),
                    '--workpath', str(build / 'work'), '--specpath', str(build),
                    '--paths', str(project / 'python'), '--add-data', str(project / 'icons') + os.pathsep + 'icons',
                    '--collect-all', 'imageio_ffmpeg', str(project / 'python/quickPathExplorer.py')],
                   check=True, env=env)
    distribution = build / 'dist/QuickPathExplorer'
    if args.install_project:
        # PyInstallerの出力先をソース直下にすると--noconfirmでソースまで削除される。
        # ビルドは隔離先で完了させ、生成したruntimeとexeだけを配置する。
        shutil.copytree(distribution / '_internal', project / '_internal', dirs_exist_ok=True)
        shutil.copy2(distribution / 'QuickPathExplorer.exe', project / 'QuickPathExplorer.exe')
        print(project / 'QuickPathExplorer.exe')
    else:
        print(distribution / 'QuickPathExplorer.exe')


if __name__ == '__main__':
    main()
