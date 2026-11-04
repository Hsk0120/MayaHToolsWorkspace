"""静的exeと対応ソースを明示した範囲から集める。ZIPは作成しない。"""

import argparse
import json
from pathlib import Path
import shutil

from build_static_qt import digest
from collect_distribution_sources import collect


def main():
    """作業出力を含めず、ライセンスと再ビルド可能なソースを同時に用意する。"""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="cpp-relink-kit")
    parser.add_argument("--exe", type=Path, default=root / ".maya-output/cpp-windows/QuickPathExplorer.exe")
    args = parser.parse_args()
    if Path(args.name).name != args.name or args.name in (".", ".."):
        parser.error("--nameには単一のフォルダー名を指定してください。")
    destination = root / ".maya-output" / args.name
    if destination.exists():
        raise FileExistsError(f"既存のキットは上書きしません: {destination}")
    if not args.exe.is_file():
        raise FileNotFoundError(args.exe)
    collect(root)
    source = destination / "QuickPathExplorer"
    # 製品コードと再ビルド素材だけを明示する。過去キットを入れ子に取り込まない。
    for folder in ("native", "maya-native", "icons", "scripts", "docs", "src/core", "src/browser", "src/standalone", "src/maya", "third_party", "tests/media"):
        shutil.copytree(root / folder, source / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "_build"))
    files = ("src/native_browser.cpp", "src/native_browser.h", "src/product.h", "tests/cpp_migration_test.cpp",
             "tests/native_maya_smoke.py", "tests/native_maya_restart.py", "tests/native_maya_gui.py", "tests/test_startup.py", "tests/verify_static_relink.py", "BUILDING.md", "LICENSE", ".vsconfig",
             "CMakeLists.txt", "build_windows.cmd", "build_maya.cmd", "generate_projects.cmd", "check_environment.cmd", "QuickPathExplorer.mod",
             "README.md", "ORGANIZER_GUIDE.md", "VERIFICATION.md", "P0_MANUAL_TESTS.txt", "launch_cpp.bat", ".gitignore", ".gitattributes",
             "tools/build_static_qt.py", "tools/build_native_media.py", "tools/build_cpp_windows.py",
             "tools/build_maya_plugin.py", "tools/maya_devkit.py", "tools/collect_distribution_sources.py",
             "tools/prepare_cpp_relink.py")
    for name in files:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    shutil.copy2(args.exe, source / "QuickPathExplorer.exe")
    (destination / "RELINK.txt").write_text("""QuickPathExplorer ソース・再リンク資料

QuickPathExplorer/QuickPathExplorer.exe と対応する全QPEソース、QtBase/QtSvg/FFmpegの
対応ソースアーカイブ、ライセンス、構成記録、SBOMを含みます。ZIP化していません。
QPE独自コードはMITです。third_party/NOTICES.txtと各依存物のライセンスを参照してください。
Qt/FFmpegを変更し、QPEを再ビルド・再リンクし、その変更をデバッグできます。
再リンク版を実行するための署名・秘密鍵・アクティベーションはありません。

QuickPathExplorerフォルダーで実行:
  py -3.12 tools/build_static_qt.py --source-archives third_party/sources --jobs 4
  py -3.12 tools/build_native_media.py --source-archives third_party/sources --jobs 4
  py -3.12 tools/build_cpp_windows.py --product --test

Visual Studio C++ v143/14.44、Windows SDK、CMake/Ninja、Python 3.12、Git for Windowsが必要です。
Python/Git/makeは開発専用です。make開発ツールは初回ビルド時にMSYS2公式配布から取得します。
Qtソースは .maya-output/static-qt/6.8.3/sources に展開されます。
改変したQtを同じ構成で構築した後、別のQt SDKへ再リンクできます:
  py -3.12 tools/build_cpp_windows.py --product --qt-prefix D:/QtModified/install --qt-source D:/QtModified/qtbase --build-dir .maya-output/relinked --test

FFmpegソースは .maya-output/native-media に展開されます。変更後のビルド結果は
QPE_FFMPEG またはQPE設定のFFmpeg欄で指定可能です。埋め込む場合はnative/CMakeLists.txtの
QPE_MEDIA_EXECUTABLEへ変更版exeを指定してQPEを再リンクしてください。
Maya版は対象MayaのSDK/Qtへリンクする別ビルドです。Windows用の静的QtをMayaへ持ち込みません。
詳しい構成と導入手順はBUILDING.mdを参照してください。
""", encoding="utf-8")
    checksums = {p.relative_to(destination).as_posix(): digest(p)
                 for p in sorted(destination.rglob("*")) if p.is_file()}
    (destination / "SHA256.json").write_text(json.dumps(checksums, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
