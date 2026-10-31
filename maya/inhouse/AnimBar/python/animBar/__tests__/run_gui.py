"""使い捨ての Maya GUI を起動して :mod:`guiCheck` を実行する(mlib の runGui の仕組みを使う)。

使い方::

    python maya\\inhouse\\AnimBar\\python\\animBar\\__tests__\\run_gui.py --versions 2025 2027
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MLIB_TESTS = HERE.parents[3] / "mlib" / "__tests__"


def main():
    """バージョンごとに使い捨てのGUIでバーを確かめる。

    Returns:
        int: 終了コード(全部成功で0)。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", nargs="+", default=["2027"])
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    sys.path.insert(0, str(MLIB_TESTS))
    import runGui
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    install_root = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Autodesk"
    code = 0
    for version in args.versions:
        directory = HERE / "_output" / stamp / version
        result = runGui.run_version(version, directory, install_root, args.timeout, suite_path=HERE / "guiCheck.py")
        detail = directory / "result.json"
        checks = json.loads(detail.read_text(encoding="utf-8")) if detail.is_file() else {}
        print(version, result.get("status"), json.dumps(checks.get("checks", {})), checks.get("error", "")[:2000])
        if result.get("status") != "passed":
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
