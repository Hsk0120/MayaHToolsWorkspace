"""各ツールの ``byMlib/`` に置いた mlib 版のファイルを、元のモジュールの代わりに読み込む。

mlib の使い方の事例を増やすため、``maya/inhouse/<ツール>/`` のファイルの mlib 版を、元のファイルを変えずに
``maya/inhouse/<ツール>/byMlib/<元と同じ相対パス>`` に置く。この仕組みは、元のテストをそのまま mlib 版に
対して流すためのもの。

``install(roots)`` を呼ぶと、``roots`` のどれかの下にあるモジュールを import するとき、
``<root>/byMlib/<同じ相対パス>`` にファイルがあればそちらを同じモジュール名で読み込む。
無ければ元のファイルを読み込む(mlib 版は、変える必要があるファイルだけを置けばよい)。
パッケージの ``__init__.py`` を差し替えても、子のモジュールは元のフォルダーから探し、そこでまた差し替えを確かめる。

使い方(mayapy で、テストの入口のスクリプトを mlib 版で動かす):

    mayapy tools/by_mlib.py <ツールのフォルダー> [<ツールのフォルダー> ...] -- <スクリプト> [引数 ...]

例: ``mayapy tools/by_mlib.py maya/inhouse/AnimBar -- maya/inhouse/AnimBar/__tests__/run_tests.py``

mlib は ``maya.standalone.initialize()`` の前に import できない。初期化の前に import する元のテストは、
``--standalone`` を付けると、スクリプトを動かす前に初期化する
(例: ``mayapy tools/by_mlib.py maya/inhouse/SimpleCloth --standalone -- maya/inhouse/SimpleCloth/tests/test_simpleCloth.py``)。

子のプロセス(mayapy を別に起動するテストの入口など)にも同じ差し替えを効かせるため、
環境変数 ``BY_MLIB_ROOTS``(``os.pathsep`` 区切り)に対象のフォルダーを入れ、``PYTHONPATH`` の先頭に
このファイルのあるフォルダーの ``by_mlib_site`` を足す(その中の ``sitecustomize.py`` が ``install`` を呼ぶ)。
"""

import argparse
import importlib.abc
import importlib.machinery
import importlib.util
import os
import runpy
import sys
from pathlib import Path

ENVIRONMENT_KEY = "BY_MLIB_ROOTS"
FOLDER_NAME = "byMlib"
SITE_FOLDER = Path(__file__).resolve().parent / "by_mlib_site"
#: mlib と各ツールを置いたフォルダー。素の mayapy では import の検索パスに入っていないので足す。
INHOUSE_FOLDER = Path(__file__).resolve().parents[1] / "maya" / "inhouse"


class ByMlibFinder(importlib.abc.MetaPathFinder):
    """元のモジュールの場所を探し、``byMlib/`` に同じ相対パスのファイルがあればそちらを返す。"""

    def __init__(self, roots):
        self.roots = [Path(root).resolve() for root in roots]
        #: 差し替えたモジュール名と、読み込んだファイル(どれが mlib 版で動いたかを確かめるため)。
        self.replaced = {}

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002 引数は import の仕組みが決める
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not spec.origin or not spec.has_location:
            return None
        origin = Path(spec.origin).resolve()
        for root in self.roots:
            try:
                relative = origin.relative_to(root)
            except ValueError:
                continue
            if relative.parts and relative.parts[0] == FOLDER_NAME:
                return None
            candidate = root / FOLDER_NAME / relative
            if not candidate.is_file():
                return None
            replaced = importlib.util.spec_from_file_location(fullname, str(candidate), submodule_search_locations=spec.submodule_search_locations)
            self.replaced[fullname] = str(candidate)
            return replaced
        return None


def install(roots=None):
    """差し替えを有効にする。

    Args:
        roots (Iterable[str] | None): ツールのフォルダー。None なら環境変数 ``BY_MLIB_ROOTS`` から読む。

    Returns:
        ByMlibFinder | None: 入れた差し替え。対象が無ければ None。
    """
    if roots is None:
        roots = [item for item in os.environ.get(ENVIRONMENT_KEY, "").split(os.pathsep) if item]
    roots = list(roots)
    if not roots:
        return None
    for finder in sys.meta_path:
        if isinstance(finder, ByMlibFinder):
            return finder
    finder = ByMlibFinder(roots)
    sys.meta_path.insert(0, finder)
    return finder


def main(argv=None):
    """``--`` の前のツールのフォルダーで差し替えを入れ、``--`` の後のスクリプトを ``__main__`` として動かす。

    Args:
        argv (list[str] | None): 引数。None なら ``sys.argv[1:]``。

    Returns:
        int: スクリプトが ``SystemExit`` で返した終了コード(無ければ 0)。
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        raise SystemExit("使い方: by_mlib.py <ツールのフォルダー> ... -- <スクリプト> [引数 ...]")
    split = argv.index("--")
    parser = argparse.ArgumentParser(description="byMlib/ の mlib 版でスクリプトを動かす")
    parser.add_argument("roots", nargs="+")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="スクリプトの前に maya.standalone を初期化する(mlib は初期化の前に import できないため、初期化の前に import する元のテストで使う)",
    )
    options = parser.parse_args(argv[:split])
    script, *arguments = argv[split + 1 :]
    roots = [str(Path(root).resolve()) for root in options.roots]
    # 子のプロセスにも効くように、環境変数と sitecustomize の場所を渡す。
    os.environ[ENVIRONMENT_KEY] = os.pathsep.join(roots)
    os.environ["PYTHONPATH"] = os.pathsep.join(item for item in (str(SITE_FOLDER), str(INHOUSE_FOLDER), os.environ.get("PYTHONPATH", "")) if item)
    if str(INHOUSE_FOLDER) not in sys.path:
        sys.path.insert(0, str(INHOUSE_FOLDER))
    install(roots)
    if options.standalone:
        # mayapy の中だけで使う。Maya が無い Python では import に失敗する。
        import maya.standalone

        maya.standalone.initialize()
    sys.argv = [script, *arguments]
    sys.path.insert(0, str(Path(script).resolve().parent))
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
