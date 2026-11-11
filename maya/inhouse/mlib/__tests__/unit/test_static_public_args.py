"""Maya不要で、mlib・mlib_*の公開defの引数名にsnake_caseが無いことを検査する。

公開の独自引数はlowerCamelCase、Mayaのフラグと同じ名前はMayaの表記とする(2.1.0)。
先頭``_``の関数・メソッド・クラスと、関数内で定義した関数は内部実装なので対象外。
``*args``/``**kwargs``の名前も対象外。既存の通知契約・登録プロトコルは``ALLOWED``に理由付きで明示する。
"""

import ast
import functools
import os
from pathlib import Path
import re
import unittest

_INHOUSE_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES = ("mlib", "mlib_bifrost", "mlib_posedriverconnect")
_SKIPPED_DIRECTORIES = {"__tests__", "_docs", "__pycache__"}

#: snake_caseの引数を許可する公開def。キーは(パッケージからの相対パス, 修飾名)。
ALLOWED = {
    ("mlib/core/registry.py", "NodeRegistry.__init__"): "既存の登録プロトコル",
    ("mlib/core/registry.py", "NodeRegistry.register"): "既存の登録プロトコル",
    ("mlib/core/registry.py", "NodeRegistry.wrapper_class"): "既存の登録プロトコル",
    ("mlib/core/reload.py", "reload_package"): "既存の再読み込みプロトコル",
    ("mlib/core/attributeEdit.py", "extra_children"): "coreの内部編集基盤(__all__外)",
    ("mlib/core/attributeEdit.py", "validate_extra_attribute"): "coreの内部編集基盤(__all__外)",
    ("mlib/core/attributeEdit.py", "create_extra_attribute"): "coreの内部編集基盤(__all__外)",
    ("mlib/core/nodeEdit.py", "rename_node"): "coreの内部編集基盤(__all__外)",
    ("mlib/core/nodeEdit.py", "create_node"): "coreの内部編集基盤(__all__外)",
    ("mlib_bifrost/nodes/compound.py", "Compound.add_node"): "mlib_bifrostの既存VNN操作名(名前自体がsnake_case)",
}

_SNAKE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")


def _is_public(name):
    """名前が公開defか判定する。特殊メソッドは公開として扱う。"""
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def _parameter_names(function):
    """位置・キーワード引数の名前を返す。*args/**kwargsは含めない。"""
    arguments = function.args
    positional = list(getattr(arguments, "posonlyargs", [])) + list(arguments.args)
    return [argument.arg for argument in positional + list(arguments.kwonlyargs)]


def _iter_public_functions(tree):
    """モジュール直下と公開クラス(入れ子を含む)の公開defを(修飾名, ノード)で返す。"""
    pending = [(tree, "")]
    while pending:
        node, prefix = pending.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef) and _is_public(child.name):
                pending.append((child, prefix + child.name + "."))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(child.name):
                yield prefix + child.name, child
            elif isinstance(child, (ast.If, ast.Try, ast.With)):
                # 条件付き定義・try内の定義も同じ階層の公開defとして扱う。
                pending.append((child, prefix))


def _iter_source_files():
    """検査対象のPythonファイルを(相対パス, Path)で返す。"""
    for package in _PACKAGES:
        for directory, subdirectories, files in os.walk(str(_INHOUSE_ROOT / package)):
            # 文書のビルド環境(_docs/.venv)等を走査しないよう、除外フォルダーへ降りない。
            subdirectories[:] = sorted(name for name in subdirectories
                                       if name not in _SKIPPED_DIRECTORIES and not name.startswith("."))
            for filename in sorted(files):
                if filename.endswith(".py"):
                    path = Path(directory) / filename
                    yield path.relative_to(_INHOUSE_ROOT).as_posix(), path


@functools.lru_cache(maxsize=None)
def find_snake_case_arguments():
    """許可リスト外でsnake_caseの引数を持つ公開defを列挙する。

    Returns:
        tuple[tuple[str, ...], frozenset[tuple[str, str]]]: 違反の説明と、実際に使われた許可キー。
    """
    offenders = []
    used = set()
    for relative, path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for qualified, function in _iter_public_functions(tree):
            names = [name for name in _parameter_names(function) if not name.startswith("_") and _SNAKE.match(name)]
            if not names:
                continue
            key = (relative, qualified)
            if key in ALLOWED:
                used.add(key)
                continue
            offenders.append("%s:%d %s(%s)" % (relative, function.lineno, qualified, ", ".join(names)))
    return tuple(offenders), frozenset(used)


#: 3.0.0で廃止した独自メソッドの短縮名の別名。Mayaコマンドへフラグを渡す入口だけに許可する。
#: ``ws`` は12.2.0から ``worldSpace`` の短縮名として全メソッドで受ける(:func:`find_world_space_without_alias`)。
REMOVED_SHORT_ALIASES = frozenset(("idx", "src", "dst", "attrs"))

#: 短縮名を持ってよい公開def(Mayaコマンドのフラグをそのまま受ける入口)。
MAYA_FLAG_ENTRIES = {}


#: ``cmds/`` の作成関数が受けるMayaコマンドの短縮名(短縮名: 長名)。pymelのMayaコマンドのフラグ一覧で確かめた名前。
#: ``createNode``・``duplicate`` 等のフラグ群の入口は別に検査する。
CMDS_SHORT_FLAGS = {
    "createIkHandle": {"sj": "startJoint", "ee": "endJoint", "sol": "solver", "n": "name", "c": "curve"},
    "bindSkin": {"mi": "maximumInfluences"},
    "bakeResults": {"at": "attributes", "t": "time", "sb": "sampleBy"},
    "bakeDeformer": {"mi": "maxInfluences"},
    "createCurve": {"d": "degree", "n": "name"},
    "createCircle": {"r": "radius", "nr": "normal", "s": "sections", "d": "degree", "n": "name"},
    "createLocator": {"n": "name"},
    "createPolyCube": {"w": "width", "h": "height", "d": "depth", "n": "name"},
    "createPolySphere": {"r": "radius", "ax": "axis", "n": "name"},
    "createPolyCylinder": {"r": "radius", "h": "height", "ax": "axis", "n": "name"},
    "createPolyPlane": {"w": "width", "h": "height", "ax": "axis", "n": "name"},
    "createBlendShape": {"n": "name", "foc": "frontOfChain"},
    "createContainer": {"n": "name"},
    "createDagContainer": {"n": "name"},
    "createDagPose": {"n": "name", "bp": "bindPose"},
}

#: Mayaコマンドの ``p`` が parent 以外(point・position)を指すため、``p`` を持ってはいけない作成関数。
CMDS_WITHOUT_PARENT_SHORT = ("createCurve", "createLocator", "createJointChain")


def _cmds_function(name):
    """``mlib/cmds/<name>.py`` の同名の公開defを返す。"""
    path = _INHOUSE_ROOT / "mlib" / "cmds" / (name + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for qualified, function in _iter_public_functions(tree):
        if qualified == name:
            return function
    raise AssertionError(f"{name} is not defined in {path}")


@functools.lru_cache(maxsize=None)
def find_short_alias_arguments():
    """許可した入口の外で、廃止した短縮名の別名を引数に持つ公開defを列挙する。

    Returns:
        tuple[tuple[str, ...], frozenset[tuple[str, str]]]: 違反の説明と、実際に使われた許可キー。
    """
    offenders = []
    used = set()
    for relative, path in _iter_source_files():
        if "/core/" in relative:
            # coreの内部編集基盤はsnake_caseの内部引数wsを維持する。
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for qualified, function in _iter_public_functions(tree):
            names = sorted(REMOVED_SHORT_ALIASES & set(_parameter_names(function)))
            # 演算子(>>・<<・//)の相手は位置でだけ渡すため対象外。
            if not names or qualified.rsplit(".", 1)[-1].startswith("__"):
                continue
            key = (relative, qualified)
            if key in MAYA_FLAG_ENTRIES:
                used.add(key)
                continue
            offenders.append("%s:%d %s(%s)" % (relative, function.lineno, qualified, ", ".join(names)))
    return tuple(offenders), frozenset(used)


@functools.lru_cache(maxsize=None)
def find_world_space_without_alias():
    """``worldSpace`` を引数に持つが、短縮名 ``ws`` を持たない公開defを列挙する。

    Returns:
        tuple[str, ...]: 違反の説明。
    """
    offenders = []
    for relative, path in _iter_source_files():
        if "/core/" in relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for qualified, function in _iter_public_functions(tree):
            names = set(_parameter_names(function))
            if "worldSpace" in names and "ws" not in names:
                offenders.append("%s:%d %s" % (relative, function.lineno, qualified))
    return tuple(offenders)


class PublicArgumentNameTest(unittest.TestCase):
    """公開defの引数名はlowerCamelCase、またはMayaのフラグと同じ表記。"""

    def test_packages_exist(self):
        """検査対象のパッケージが見つかり、0件の素通りにならない。"""
        for package in _PACKAGES:
            with self.subTest(package=package):
                files = [relative for relative, _ in _iter_source_files() if relative.startswith(package + "/")]
                self.assertTrue(any(relative.endswith("__init__.py") for relative in files), package)

    def test_no_snake_case_public_arguments(self):
        """許可リスト外の公開defにsnake_caseの引数が無い。"""
        offenders, _ = find_snake_case_arguments()
        self.assertEqual(list(offenders), [], "snake_case public arguments:\n" + "\n".join(offenders))

    def test_no_removed_short_aliases(self):
        """独自メソッドは短縮名の別名(idx・src・dst・attrs)を持たない。"""
        offenders, used = find_short_alias_arguments()
        self.assertEqual(list(offenders), [], "short alias arguments:\n" + "\n".join(offenders))
        self.assertEqual(sorted(set(MAYA_FLAG_ENTRIES) - used), [])

    def test_world_space_has_short_alias(self):
        """worldSpace を受ける公開defは、短縮名 ws も受ける(12.2.0)。"""
        offenders = find_world_space_without_alias()
        self.assertEqual(list(offenders), [], "worldSpace without ws:\n" + "\n".join(offenders))

    def test_cmds_creators_accept_maya_short_flags(self):
        """cmds の作成関数は、専用引数に当たるMayaの短縮名を keyword-only で受け、docstringに載せる。"""
        for name, pairs in sorted(CMDS_SHORT_FLAGS.items()):
            function = _cmds_function(name)
            keyword_only = {argument.arg for argument in function.args.kwonlyargs}
            names = set(_parameter_names(function))
            docstring = ast.get_docstring(function) or ""
            source = ast.unparse(function) if hasattr(ast, "unparse") else None
            for short, long in sorted(pairs.items()):
                with self.subTest(function=name, short=short):
                    self.assertIn(long, names)
                    self.assertIn(short, keyword_only)
                    self.assertIn("%s (" % short, docstring)
                    self.assertIn("%sの短縮名" % long, docstring)
                    if source is not None:
                        self.assertIn("_pick_alias(%s, %s, '%s', '%s'" % (long, short, long, short), source)

    def test_cmds_creators_do_not_alias_parent_as_p(self):
        """Mayaの p が point・position の作成関数は、parent の短縮名 p を持たない。"""
        for name in CMDS_WITHOUT_PARENT_SHORT:
            with self.subTest(function=name):
                self.assertNotIn("p", _parameter_names(_cmds_function(name)))

    def test_allowlist_has_no_stale_entries(self):
        """許可リストの全行が現存し、実際にsnake_caseの引数を持つ。"""
        _, used = find_snake_case_arguments()
        self.assertEqual(sorted(set(ALLOWED) - used), [])

    def test_detects_snake_case_argument(self):
        """検出規則が公開defのsnake_caseを拾い、内部defと*args/**kwargsを除く。"""
        source = (
            "def publicFunc(value, old_name=None, *extra_args, **extra_kwargs):\n    pass\n"
            "def _internal(old_name):\n    pass\n"
            "class Item:\n"
            "    def method(self, newName, other_name=1):\n"
            "        def nested(inner_name):\n            pass\n"
            "class _Hidden:\n    def method(self, old_name):\n        pass\n"
        )
        found = {qualified: [name for name in _parameter_names(function) if _SNAKE.match(name)]
                 for qualified, function in _iter_public_functions(ast.parse(source))}
        self.assertEqual(found, {"publicFunc": ["old_name"], "Item.method": ["other_name"]})


if __name__ == "__main__":
    unittest.main()
