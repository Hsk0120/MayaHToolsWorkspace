"""静的QtでQPEを構築する。明示した場合だけ検証後に製品exeを配置する。"""

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

from build_static_qt import VERSION, compiler_environment


def main():
    """明示したQtでも再リンクできる、Maya非依存のCMake入口。"""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-prefix", type=Path, default=root / ".maya-output/static-qt" / VERSION / "install")
    parser.add_argument("--qt-source", type=Path, default=root / ".maya-output/static-qt" / VERSION / "sources" / f"qtbase-everywhere-src-{VERSION}")
    parser.add_argument("--build-dir", type=Path, default=root / ".maya-output/cpp-windows")
    parser.add_argument("--media-executable", type=Path, help="同梱する静的メディアhelper。変更版も指定できる")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--asan", action="store_true", help="開発専用AddressSanitizerビルド。配布には使わない")
    parser.add_argument("--product", action="store_true", help="製品名のexeを指定したビルド出力へ生成する")
    parser.add_argument("--install-project", action="store_true", help="回帰テスト後に直下へexeを配置する。起動中は失敗する")
    parser.add_argument("--clean", action="store_true", help="古い依存追跡で作られたオブジェクトを再構築する")
    args = parser.parse_args()
    if args.install_project and not args.product:
        parser.error("--install-projectには--productが必要です。")
    if args.install_project and args.asan:
        parser.error("AddressSanitizerビルドは製品へ配置できません。")
    cmake, ninja, env = compiler_environment()
    options = ["-DQPE_ENABLE_ASAN=" + ("ON" if args.asan else "OFF")]
    if args.media_executable:
        options.append(f"-DQPE_MEDIA_EXECUTABLE={args.media_executable.resolve()}")
    subprocess.run([str(cmake), "-S", str(root / "native"), "-B", str(args.build_dir), "-G", "Ninja",
                    f"-DCMAKE_MAKE_PROGRAM={ninja}", "-DCMAKE_BUILD_TYPE=Release",
                    f"-DCMAKE_PREFIX_PATH={args.qt_prefix.resolve()}", f"-DQPE_QT_SOURCE_DIR={args.qt_source.resolve()}",
                    "-DQPE_PRODUCT_BUILD=" + ("ON" if args.product else "OFF")] + options, env=env, check=True)
    subprocess.run([str(cmake), "--build", str(args.build_dir), "--parallel", "4"] + (["--clean-first"] if args.clean else []), env=env, check=True)
    if args.test or args.install_project:
        env["QPE_TEST_PYTHON"] = sys.executable
        subprocess.run([str(cmake.parent / "ctest.exe"), "--test-dir", str(args.build_dir), "--output-on-failure"], env=env, check=True)
    if args.install_project:
        target = root / "QuickPathExplorer.exe"
        if target.exists():
            backup = root / ".maya-output/product-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup.mkdir(parents=True)
            shutil.copy2(target, backup / target.name)
        staged = target.with_suffix(".exe.new")
        shutil.copy2(args.build_dir / "QuickPathExplorer.exe", staged)
        try:
            staged.replace(target)
        except PermissionError as error:
            staged.unlink(missing_ok=True)
            raise RuntimeError("Windows版QPEを終了してから、同じビルドコマンドを再実行してください。") from error
        print(f"配置: {target}")


if __name__ == "__main__":
    main()
