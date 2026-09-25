"""MayaのC++プラグインをバージョン別にビルドする（Windows専用）。

対象のプラグインリポジトリは、Mayaのdevkitが提供する ``cmake/pluginEntry.cmake`` を
``$ENV{DEVKIT_LOCATION}`` 経由で使い、``-DMAYA_VERSION=<年>`` を受け取る
CMakeLists.txt を持つこと（MayaCinematicCameraHUD と同じ構成）。

使い方::

    python tools/build_maya_plugin.py maya/inhouse/MayaCinematicCameraHUD --versions 2026
    python tools/build_maya_plugin.py maya/inhouse/MayaCinematicCameraHUD --list

ビルドディレクトリは ``.maya-output/plugin-build/`` 配下（Git対象外）に作るため、
プラグインのソースツリーを汚さない。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import maya_devkit  # noqa: E402

# Mayaバージョンに対応するMSVCプラットフォームツールセット。
# 2022/2024/2026 は MayaCinematicCameraHUD の実ビルドで確認済み。2023/2025/2027 は未確認の想定値。
TOOLSETS = {2022: "v142", 2023: "v142", 2024: "v143", 2025: "v143", 2026: "v145", 2027: "v145"}
VERIFIED = {2022, 2024, 2026}

GENERATORS = {18: "Visual Studio 18 2026", 17: "Visual Studio 17 2022", 16: "Visual Studio 16 2019"}
VSWHERE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"


def visual_studios():
    """list[dict]: 導入済みVisual Studio（新しい順）。path, major, toolsets を持つ。"""
    if not VSWHERE.exists():
        return []
    out = subprocess.run([str(VSWHERE), "-all", "-products", "*", "-format", "json", "-utf8"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    installs = []
    for item in json.loads(out or "[]"):
        path = Path(item["installationPath"])
        toolsets = {p.name for p in path.glob("MSBuild/Microsoft/VC/*/Platforms/x64/PlatformToolsets/*")}
        cmake = path / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
        installs.append({"path": path, "major": int(item["installationVersion"].split(".")[0]),
                         "toolsets": toolsets, "cmake": cmake if cmake.exists() else None})
    return sorted(installs, key=lambda i: i["major"], reverse=True)


def pick_vs(toolset):
    """指定ツールセットを持つ最新のVisual Studioを返す。無ければ None。"""
    for vs in visual_studios():
        if toolset in vs["toolsets"] and vs["cmake"] and vs["major"] in GENERATORS:
            return vs
    return None


def devkit_location(year, install_root, prepare=True):
    """Path | None: ビルドに使う DEVKIT_LOCATION。

    優先順: 環境変数 MAYA_DEVKIT_<年>（別途入手したdevkit）、そのままdevkitとして使えるインストール先、
    ローカル生成（tools/maya_devkit.py。prepare=False の場合は生成せず、生成済みかどうかだけ調べる）。
    """
    override = os.environ.get("MAYA_DEVKIT_%d" % year)
    if override and (Path(override) / "cmake/pluginEntry.cmake").exists():
        return Path(override)
    ready = maya_devkit.ready_in_install(year, install_root)
    if ready is not None:
        return ready
    if maya_devkit.install_dir(year, install_root) is None:
        return None
    generated = maya_devkit.DEVKIT_ROOT / str(year)
    stamp = generated / ".prepared"
    if stamp.exists() and stamp.read_text(encoding="utf-8") == maya_devkit.LAYOUT_VERSION:
        return generated
    return maya_devkit.prepare(year, install_root) if prepare else None


def run(cmd, env):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], env=env).returncode


def build(plugin, year, config, install_root, build_root):
    """1バージョン分をビルドする。(成功か, 生成した.mllのリスト) を返す。"""
    toolset = TOOLSETS[year]
    try:
        devkit = devkit_location(year, install_root)
    except RuntimeError as error:
        print("Maya %d: %s" % (year, error))
        return False, []
    if devkit is None:
        print("Maya %d: インストールされていません（%s）。" % (year, install_root))
        return False, []
    vs = pick_vs(toolset)
    if vs is None:
        print("Maya %d: ツールセット %s を持つVisual Studioが見つかりません。" % (year, toolset))
        return False, []
    if year not in VERIFIED:
        print("Maya %d: ツールセット %s は未検証の想定値です。" % (year, toolset))

    build_dir = build_root / plugin.name / str(year)
    env = dict(os.environ, DEVKIT_LOCATION=str(devkit).replace("\\", "/"))
    started = time.time()
    cmake = vs["cmake"]
    if run([cmake, "-S", plugin, "-B", build_dir, "-G", GENERATORS[vs["major"]], "-A", "x64",
            "-T", toolset, "-DMAYA_VERSION=%d" % year], env):
        return False, []
    if run([cmake, "--build", build_dir, "--config", config, "--parallel"], env):
        return False, []
    built = sorted(p for p in plugin.rglob("*.mll") if str(year) in p.parts and p.stat().st_mtime >= started - 1)
    return True, built


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plugin", type=Path, help="CMakeLists.txt を持つプラグインのフォルダ")
    parser.add_argument("--versions", type=int, nargs="+", choices=sorted(TOOLSETS), default=[2026])
    parser.add_argument("--config", default="Release")
    parser.add_argument("--install-root", default=r"C:\Program Files\Autodesk")
    parser.add_argument("--build-root", type=Path, default=ROOT / ".maya-output/plugin-build")
    parser.add_argument("--list", action="store_true", help="ビルドせず、環境の検出結果だけ表示する")
    args = parser.parse_args(argv)

    plugin = args.plugin.resolve()
    if not (plugin / "CMakeLists.txt").exists():
        print("CMakeLists.txt が見つかりません: %s" % plugin)
        return 2

    if args.list:
        for vs in visual_studios():
            print("Visual Studio %d: %s toolsets=%s cmake=%s" % (vs["major"], vs["path"], sorted(vs["toolsets"]), bool(vs["cmake"])))
        for year in sorted(TOOLSETS):
            devkit = devkit_location(year, args.install_root, prepare=False)
            installed = maya_devkit.install_dir(year, args.install_root) is not None
            vs = pick_vs(TOOLSETS[year])
            print("Maya %d: install=%s toolset=%s devkit=%s vs=%s" % (year, "あり" if installed else "なし", TOOLSETS[year], devkit or ("未生成(ビルド時に自動生成)" if installed else "なし"), vs["major"] if vs else "なし"))
        return 0

    failed = []
    for year in args.versions:
        print("==== Maya %d ====" % year)
        ok, built = build(plugin, year, args.config, args.install_root, args.build_root)
        for path in built:
            print("生成:", path)
        if not ok:
            failed.append(year)
    print("失敗: %s" % failed if failed else "全て成功")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
