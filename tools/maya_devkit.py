"""Mayaのインストール先から、ビルド用のローカルdevkitを生成する（Windows専用）。

Maya 2025 以降はdevkitが別配布で、インストール先には ``cmake/pluginEntry.cmake`` が無い。
また Maya 2022/2024 はQtのcmake/ヘッダ用zipが未展開で、展開には管理者権限が要る。
一方、ヘッダ・ライブラリ・moc・Qt用zipはインストール先に揃っているため、
``.maya-output/devkit/<年>/`` に ``DEVKIT_LOCATION`` として使える構成を生成する
（Program Files配下は書き換えない）。

生成物::

    cmake/   pluginEntry.cmake 等（インストール先に無い版は、あるうちで最新の版から流用）
    include/ lib/   インストール先へのジャンクション（Qt5系は lib を実体化して lib/cmake を展開）
    Qt/      Qt6系のみ。lib/cmake・include・mkspecs を展開し、bin はジャンクション
"""

import os
import re
import shutil
import zipfile
from pathlib import Path

try:
    import _winapi
except ImportError:  # Windows以外
    _winapi = None

ROOT = Path(__file__).resolve().parents[1]
DEVKIT_ROOT = ROOT / ".maya-output/devkit"
# 生成物の構成を変えたら上げる（古い生成物は自動で作り直される）。
LAYOUT_VERSION = "4"
CMAKE_FILES = ("pluginEntry.cmake", "devkit.cmake", "gpuCache.cmake", "mayald.cmake")


def qt_major(year):
    """int: そのMayaバージョンが使うQtのメジャーバージョン。"""
    return 5 if year <= 2024 else 6


def _junction(target, link):
    """link を target へのディレクトリジャンクションとして作る（既存なら作り直す）。"""
    link = Path(link)
    if link.exists() or link.is_symlink():
        os.rmdir(link)
    _winapi.CreateJunction(str(target), str(link))


def _hardlink_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _is_reparse_point(path):
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)
    except (OSError, AttributeError):
        return False


def _remove_tree(path):
    """ジャンクションは中身をたどらずリンクだけ外して、ディレクトリを削除する（インストール先を消さない）。"""
    path = Path(path)
    for entry in list(path.iterdir()):
        if _is_reparse_point(entry):
            os.rmdir(entry)
        elif entry.is_dir():
            _remove_tree(entry)
    if _is_reparse_point(path):
        os.rmdir(path)
    else:
        shutil.rmtree(path)


_IMPORT_REF = re.compile(r"\$\{(?:_IMPORT_PREFIX|PACKAGE_PREFIX_DIR)\}/(?:\./)?((?:bin|lib|libexec)/[^\"\s\)$]+)")


def _satisfy_qt6_imports(qt, install):
    """Qt6のcmake設定が参照する bin/lib のファイルを用意する。

    実物がインストール先にあればハードリンク、無ければ空のダミーを置く
    （moc等の実行に不要なツールまで存在チェックされるため）。
    """
    refs = set()
    for path in (qt / "lib/cmake").rglob("*.cmake"):
        refs.update(_IMPORT_REF.findall(path.read_text(encoding="utf-8", errors="replace")))
    for rel in sorted(refs):
        target = qt / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source = install / rel
        if source.is_file():
            _hardlink_or_copy(source, target)
        else:
            target.write_bytes(b"")


def _extract(zip_path, dest):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def _zip(directory, pattern):
    """Path | None: directory 内の pattern に一致する最初のzip。"""
    found = sorted(Path(directory).glob(pattern))
    return found[0] if found else None


def _patch_qt5_cmake(cmake_dir):
    """Qt5のcmake設定からDEBUG構成の参照を外す（MayaにはRelease版しか無いため）。

    MayaCinematicCameraHUD の tools/windows/fix_qt5_maya*.ps1 と同じ処理。
    """
    for path in Path(cmake_dir).rglob("*.cmake"):
        if not re.match(r"Qt5(Core|Gui|Widgets)", path.name):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        new = re.sub(r"(\r?\n)(\s*)(_populate[^\(]+\([^,\)]+,?\s*DEBUG[^\)]*\))", r"\1\2# \3", text)
        if path.name.endswith("Config.cmake"):
            new = re.sub(r"(\r?\n)(\s*)(include\(\$\{pluginTarget\}\))", r"\1\2# \3 # Plugins disabled", new)
        if new != text:
            path.write_text(new, encoding="utf-8", newline="")


def _cmake_source(year, install_root):
    """Path: pluginEntry.cmake を持つcmakeフォルダ（当該バージョン→新しい版の順に探す）。"""
    order = [year] + sorted((y for y in range(2022, 2031) if y != year), reverse=True)
    for y in order:
        path = Path(install_root) / ("Maya%d" % y) / "cmake"
        if (path / "pluginEntry.cmake").exists():
            return path
    raise RuntimeError("pluginEntry.cmake を持つMayaが見つかりません")


def install_dir(year, install_root):
    path = Path(install_root) / ("Maya%d" % year)
    return path if path.is_dir() else None


def ready_in_install(year, install_root):
    """Path | None: インストール先がそのままdevkitとして使える場合の場所。"""
    install = install_dir(year, install_root)
    if install is None or not (install / "cmake/pluginEntry.cmake").exists():
        return None
    if qt_major(year) == 6:
        return install if (install / "Qt/lib/cmake/Qt6").exists() else None
    return install if (install / "lib/cmake/Qt5/Qt5Config.cmake").exists() else None


def prepare(year, install_root, out_root=DEVKIT_ROOT, log=print):
    """Path: ビルドに使う DEVKIT_LOCATION を返す（必要なら生成する）。

    Raises:
        RuntimeError: Mayaがインストールされていない、または必要なzipが無い場合。
    """
    ready = ready_in_install(year, install_root)
    if ready is not None:
        return ready
    install = install_dir(year, install_root)
    if install is None:
        raise RuntimeError("Maya %d がインストールされていません: %s" % (year, install_root))
    if _winapi is None:
        raise RuntimeError("Windowsでのみ動作します")

    dest = Path(out_root) / str(year)
    stamp = dest / ".prepared"
    if stamp.exists() and stamp.read_text(encoding="utf-8") == LAYOUT_VERSION:
        return dest
    log("Maya %d: ローカルdevkitを生成します: %s" % (year, dest))
    if dest.exists():
        _remove_tree(dest)
    dest.mkdir(parents=True)

    cmake_dst = dest / "cmake"
    (cmake_dst / "modules").mkdir(parents=True)
    source = _cmake_source(year, install_root)
    for name in CMAKE_FILES:
        if (source / name).exists():
            shutil.copy2(source / name, cmake_dst / name)
    if (source / "modules").is_dir():
        shutil.copytree(source / "modules", cmake_dst / "modules", dirs_exist_ok=True)

    qt_cmake = _zip(install / "cmake", "qt_*-cmake.zip")
    qt_include = _zip(install / "include", "qt_*-include.zip")
    qt_mkspecs = _zip(install / "mkspecs", "qt_*-mkspecs.zip")
    if qt_cmake is None or qt_include is None:
        raise RuntimeError("Maya %d のインストール先にQt用zipが見つかりません" % year)

    if qt_major(year) == 6:
        qt = dest / "Qt"
        (qt / "lib").mkdir(parents=True)
        _extract(qt_cmake, qt / "lib/cmake")
        _extract(qt_include, qt / "include")
        if qt_mkspecs is not None:
            _extract(qt_mkspecs, qt / "mkspecs")
        for lib in (install / "lib").glob("Qt6*.lib"):
            _hardlink_or_copy(lib, qt / "lib" / lib.name)
        _satisfy_qt6_imports(qt, install)
        _junction(install / "include", dest / "include")
        _junction(install / "lib", dest / "lib")
    else:
        lib_dir, include_dir = dest / "lib", dest / "include"
        lib_dir.mkdir()
        include_dir.mkdir()
        for lib in (install / "lib").iterdir():
            if lib.is_file():
                _hardlink_or_copy(lib, lib_dir / lib.name)
        _extract(qt_cmake, lib_dir / "cmake")
        _patch_qt5_cmake(lib_dir / "cmake")
        for entry in (install / "include").iterdir():
            if entry.is_dir():
                _junction(entry, include_dir / entry.name)
        _extract(qt_include, include_dir)
        _junction(install / "bin", dest / "bin")
        if qt_mkspecs is not None:
            _extract(qt_mkspecs, dest / "mkspecs")
        elif (install / "mkspecs").is_dir():
            _junction(install / "mkspecs", dest / "mkspecs")

    stamp.write_text(LAYOUT_VERSION, encoding="utf-8")
    return dest
