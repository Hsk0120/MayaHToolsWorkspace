"""検証スクリプトの親フォルダーを、対象Mayaのimport前に静的検査する。"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
from support.importSafety import find_shadowing


def main():
    """対象ファイルを実行せず、標準モジュールとの衝突があれば終了コード1を返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--stdlib", type=Path, action="append", default=[],
                        help="Target Maya Python/Lib (or Python37/Lib); repeatable")
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error("directory must exist")
    matches = find_shadowing(args.directory, args.stdlib)
    for path in matches:
        print("Standard library name collision: " + str(path))
    if not matches:
        print("No standard library name collisions: " + str(args.directory.resolve()))
    return 1 if matches else 0


if __name__ == "__main__":
    sys.exit(main())
