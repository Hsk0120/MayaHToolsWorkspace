"""検証スクリプトの隣にある標準モジュールとの名前衝突を実行せず調べる。"""
import sys
import sysconfig
from pathlib import Path


def find_shadowing(directory, stdlib_directories=()):
    """Python検索パス先頭へ置くフォルダーだけを検査する。

    Args:
        directory (Path): 検証スクリプトの親フォルダー。
        stdlib_directories (Iterable[Path]): 対象Mayaの標準ライブラリの配置。

    Returns:
        list[Path]: 標準モジュールを隠すファイル。対象をimportすることはない。
    """
    directory = Path(directory).resolve()
    names = set(sys.builtin_module_names)
    names.update(getattr(sys, "stdlib_module_names", ()))
    roots = [Path(sysconfig.get_path("stdlib"))] + [Path(p) for p in stdlib_directories]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.suffix in (".py", ".pyc", ".pyd"):
                names.add(path.name.split(".")[0])
            elif path.is_dir() and (path / "__init__.py").is_file():
                names.add(path.name)
    matches = []
    for name in sorted(names):
        for relative in (name + ".py", name + ".pyc", name + ".pyd",
                         name + "/__init__.py", name + "/__init__.pyc"):
            candidate = directory / relative
            if candidate.is_file():
                matches.append(candidate)
    return matches


def require_safe_imports(directory, stdlib_directories=()):
    """衝突があればMaya起動前に拒否し、問題のファイル名を示す。"""
    matches = find_shadowing(directory, stdlib_directories)
    if matches:
        raise ValueError("Test directory shadows Python standard modules; rename these files: "
                         + ", ".join(str(path) for path in matches))
