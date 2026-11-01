"""QPE単体リポジトリのC++ビルド入口へ委譲するワークスペース用コマンド。"""

from pathlib import Path
import subprocess
import sys


def main():
    """旧PyInstaller版を生成せず、静的Qt製品を同じ引数で構築する。"""
    project = Path(__file__).resolve().parents[1] / "maya/inhouse/QuickPathExplorer"
    return subprocess.call([
        sys.executable, str(project / "tools/build_cpp_windows.py"),
        "--product", "--test", *sys.argv[1:],
    ])


if __name__ == "__main__":
    sys.exit(main())
