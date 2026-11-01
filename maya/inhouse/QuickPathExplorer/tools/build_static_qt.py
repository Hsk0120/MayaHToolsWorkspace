"""検証済みハッシュのQtソースから、QPE専用の静的Qtを構築する。

開発用Pythonだけを使用する。完成アプリケーションはPythonを必要としない。
元ソースアーカイブと構成記録は再リンク用資料として保持する。
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from build_maya_plugin import visual_studios


VERSION = "6.8.3"
SOURCES = {
    "qtbase": "56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80",
    "qtsvg": "35eb516460f00f264eb504baa253432384351cf23fb9980a5857190e8deef438",
}
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    """ファイルのSHA256を固定メモリで求める。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_tree(module, root, archives=None):
    """公式アーカイブを検証して安全に展開し、再利用する。"""
    name = f"{module}-everywhere-src-{VERSION}"
    archive = root / "sources" / f"{name}.tar.xz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() and archives is not None:
        supplied = archives / archive.name
        if not supplied.is_file() or digest(supplied) != SOURCES[module]:
            raise ValueError(f"対応するQtソースがありません、またはハッシュ不一致です: {supplied}")
        shutil.copy2(supplied, archive)
    if not archive.exists():
        url = f"https://download.qt.io/archive/qt/6.8/{VERSION}/submodules/{archive.name}"
        print(f"Downloading {url}", flush=True)
        temporary = archive.with_suffix(".partial")
        # Windowsの証明書ストアを使うcurl。証明書検証は無効化しない。
        curl = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/curl.exe"
        subprocess.run([str(curl), "--fail", "--location", "--retry", "2", "--output", str(temporary), url], check=True)
        if digest(temporary) != SOURCES[module]:
            raise ValueError(f"Qt source checksum mismatch: {temporary}")
        temporary.replace(archive)
    if digest(archive) != SOURCES[module]:
        raise ValueError(f"Qt source checksum mismatch: {archive}")
    source = archive.parent / name
    marker = source / ".qpe-extracted"
    if not marker.exists():
        # Python 3.12のdataフィルターで絶対パス、外部へのリンク等を拒否する。
        with tarfile.open(archive, "r:xz") as package:
            package.extractall(archive.parent, filter="data")
        marker.write_text(SOURCES[module], encoding="utf-8")
    return source


def compiler_environment():
    """VSのx64/v143環境を子プロセス内だけで取得する。"""
    installations = [vs for vs in visual_studios() if "v143" in vs["toolsets"]]
    if not installations:
        raise RuntimeError("Visual Studioのv143ツールセットが必要です。")
    vs = installations[0]
    setup = vs["path"] / "Common7/Tools/VsDevCmd.bat"
    # 任意のユーザー文字列をコマンドへ混ぜず、vswhereで得たパスだけを使う。
    command = f'call "{setup}" -no_logo -arch=x64 -host_arch=x64 -vcvars_ver=14.44 >nul && set'
    bootstrap = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    # 親Maya/PythonのDLLや、引用符が壊れた既存PATHをVS設定へ引き継がない。
    bootstrap["PATH"] = os.pathsep.join(str(p) for p in (windows / "System32", windows, windows / "System32/Wbem"))
    result = subprocess.run('cmd.exe /d /s /c "' + command + '"',
                            capture_output=True, text=True, encoding="mbcs", errors="replace", check=True, env=bootstrap)
    env = os.environ.copy()
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            env[key] = value
    cmake = vs["cmake"]
    ninja = cmake.parent.parent.parent / "Ninja/ninja.exe"
    if not ninja.exists():
        raise RuntimeError(f"Ninjaがありません: {ninja}")
    for name in ("PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "CMAKE_PREFIX_PATH"):
        env.pop(name, None)
    env["PATH"] = str(ninja.parent) + os.pathsep + str(cmake.parent) + os.pathsep + env["PATH"]
    # 英語MUIが導入済みなら英語にする。QPE側CMakeは実出力も検出する。
    env["VSLANG"] = "1033"
    return cmake, ninja, env


def build(root, jobs, configure_only=False, archives=None):
    """QtBase/QtSvgを静的CRTで構築し、再ビルドに必要な条件を記録する。"""
    cmake, ninja, env = compiler_environment()
    prefix = root / "install"
    manifest = {"qtVersion": VERSION, "sourceSha256": SOURCES, "commands": [],
                "compiler": env.get("VCToolsVersion"), "windowsSdk": env.get("WindowsSDKVersion"),
                "prefix": str(prefix), "complete": False}
    root.mkdir(parents=True, exist_ok=True)
    for module in SOURCES:
        source = source_tree(module, root, archives)
        output = root / "build" / module
        command = [str(cmake), "-S", str(source), "-B", str(output), "-G", "Ninja",
                   f"-DCMAKE_MAKE_PROGRAM={ninja}", "-DCMAKE_BUILD_TYPE=Release",
                   f"-DCMAKE_INSTALL_PREFIX={prefix}", f"-DCMAKE_PREFIX_PATH={prefix}",
                   "-DBUILD_SHARED_LIBS=OFF", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
                   "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TESTS=OFF"]
        if module == "qtbase":
            command += ["-DFEATURE_static_runtime=ON", "-DINPUT_opengl=no", "-DFEATURE_dbus=OFF",
                        "-DFEATURE_sql=OFF", "-DFEATURE_network=OFF"]
        manifest["commands"].append(command)
        (root / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        subprocess.run(command, env=env, check=True)
        if configure_only:
            break  # QtSvgの構成はQtBaseのinstall完了後に実施する。
        subprocess.run([str(cmake), "--build", str(output), "--parallel", str(jobs)], env=env, check=True)
        subprocess.run([str(cmake), "--install", str(output)], env=env, check=True)
    manifest["complete"] = not configure_only
    (root / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(prefix, flush=True)


def main():
    """専用出力先だけを使い、システムQtやMayaを変更しない。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--configure-only", action="store_true")
    parser.add_argument("--source-archives", type=Path, help="同梱Qtソースを使用し、ダウンロードしない")
    parser.add_argument("--work-root", type=Path, default=ROOT / ".maya-output/static-qt" / VERSION,
                        help="Qtのソース・ビルド・SDK作成先。深い配置では短い絶対パスを指定する")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    build(args.work_root.resolve(), args.jobs, args.configure_only, args.source_archives)


if __name__ == "__main__":
    main()
