"""Maya用の型スタブ(types-maya)を ``typings/maya`` に配置する。

Pylance/pyright が ``maya.cmds`` や ``maya.api.OpenMaya`` を解決できるようにするための、
開発環境の準備コマンド。MayaにはPythonソースの無い ``.pyd``/``.pyc`` しか無く、
ソースが無いとエディターは属性や引数を推定できない。

使い方::

    python tools/setup_maya_typings.py

``typings/`` はGit対象外。pipで ``types-maya``（MIT）を取得して配置し直すため、ネットワークが必要。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "typings" / "maya"
PACKAGE = "types-maya"


def main():
    with tempfile.TemporaryDirectory() as work:
        command = [sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", work, PACKAGE]
        if subprocess.run(command).returncode:
            print("pipによる %s の取得に失敗しました。" % PACKAGE)
            return 1
        source = Path(work) / "maya-stubs"
        if not source.is_dir():
            print("取得物に maya-stubs が見つかりません。")
            return 1
        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.parent.mkdir(exist_ok=True)
        shutil.copytree(source, DEST)
    print("配置しました: %s" % DEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
