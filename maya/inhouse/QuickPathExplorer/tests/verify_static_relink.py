"""専用QtのqVersionを変更し、再リンク版だけに変更が現れることを実行検証する。"""

import difflib
import json
import os
from pathlib import Path
import subprocess
import sys

# 検証用ビルド入口だけを読み込む。製品モジュールはimportしない。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_static_qt import VERSION, compiler_environment


def main():
    """Qt専用出力内だけを変更し、例外時も元のソースとSDKへ戻す。"""
    root = Path(__file__).resolve().parents[1]
    sdk = root / ".maya-output/static-qt" / VERSION
    source = sdk / "sources" / f"qtbase-everywhere-src-{VERSION}"
    file = source / "src/corelib/global/qlibraryinfo.cpp"
    if not file.resolve().is_relative_to((root / ".maya-output/static-qt").resolve()):
        raise ValueError("専用Qtソース以外は変更しません。")
    original = file.read_bytes()
    before = original.decode("utf-8")
    marker = "return QT_VERSION_STR;"
    if before.count(marker) != 1:
        raise ValueError("予期しないQtソースです。変更前に停止します。")
    after = before.replace(marker, 'return QT_VERSION_STR "-qpe-relink-check";')
    evidence = root / ".maya-output/relink-proof"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "qt-version.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/src/corelib/global/qlibraryinfo.cpp", tofile="b/src/corelib/global/qlibraryinfo.cpp")), encoding="utf-8")
    cmake, _, env = compiler_environment()
    env["VSLANG"] = "1033"
    altered = evidence / "qt-modified"
    try:
        file.write_text(after, encoding="utf-8", newline="")
        subprocess.run([str(cmake), "--build", str(sdk / "build/qtbase"), "--target", "Core", "--parallel", "4"], env=env, check=True)
        for module in ("qtbase", "qtsvg"):
            subprocess.run([str(cmake), "--install", str(sdk / "build" / module), "--prefix", str(altered)], env=env, check=True)
        subprocess.run([sys.executable, str(root / "tools/build_cpp_windows.py"), "--qt-prefix", str(altered),
                        "--qt-source", str(source), "--build-dir", str(evidence / "app")], env=env, check=True)
        fixture = evidence / "fixture"
        fixture.mkdir(exist_ok=True)
        result = evidence / "modified-smoke.json"
        clean = env.copy()
        windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
        clean["PATH"] = str(windows / "System32") + os.pathsep + str(windows)
        subprocess.run([str(evidence / "app/QuickPathExplorerNative.exe"), str(fixture), "--smoke", str(result)], env=clean, check=True, timeout=30)
        report = json.loads(result.read_text(encoding="utf-8"))
        if not report.get("passed") or report.get("qt") != VERSION + "-qpe-relink-check":
            raise RuntimeError(f"変更したQtとの再リンクを確認できません: {report}")
        print("Modified Qt relink: PASS", flush=True)
    finally:
        file.write_bytes(original)
        subprocess.run([str(cmake), "--build", str(sdk / "build/qtbase"), "--target", "Core", "--parallel", "4"], env=env, check=True)
        subprocess.run([str(cmake), "--install", str(sdk / "build/qtbase")], env=env, check=True)


if __name__ == "__main__":
    main()
