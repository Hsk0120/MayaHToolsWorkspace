"""mlib の docstring から型スタブ(.pyi)を生成し、各 ``.py`` の隣へ置く。

mlib の公開関数・メソッドは型注釈を持たず、型は Google 形式の docstring
(``Args:`` の ``name (type):`` と ``Returns:``/``Yields:`` の先頭の ``type:``)にだけ書かれている。
Pylance/pyright は docstring を型として読まないため、そのままでは ``mlib.ls()`` などの
戻り値の型が分からず、補完・引数ヒントが出ない。このスクリプトは docstring の型を
注釈として書き出したスタブを作り、エディターに型を伝える。Pylance は ``.py`` の隣の ``.pyi`` を
設定なしで優先して読むため、mlib のフォルダーだけを開いた場合や、別のプロジェクトから mlib を
import した場合も補完が効く。

- 本体の ``.py`` は読むだけで変更しない。Python は実行時に ``.pyi`` を読まないため、Maya 2022
  (Python 3.7)の動作にも影響しない。スタブは Git で管理し、docstring の型を変えたら作り直して
  一緒にコミットする(``__tests__/unit/test_static_stub_generation.py`` が古いスタブを検出する)。
- 内容が変わったファイルだけを書き換え、元の ``.py`` が無くなったスタブ(先頭行が生成の印のもの)を削除する。
- 引数で戻り値の型が変わる ``ls``・``createNode``・``getConnections`` 等は、引数ごとの戻り値を
  ``@overload`` で補う。
  ``ls(type=...)`` の型名とクラスの対応は ``nodes/__init__.py`` の ``_WRAPPER_CLASSES`` から読む。
- docstring の型がPythonの型の式として読めない、または名前を解決できない場合は、その注釈を省く
  (エディター上は型不明になる)。``--report`` で一覧を表示する。

使い方::

    python tools/generate_mlib_stubs.py            # スタブを作り直す
    python tools/generate_mlib_stubs.py --report   # 省いた注釈も表示する
    python tools/generate_mlib_stubs.py --check    # 現在のスタブが最新かだけを確かめる(古ければ終了コード1)

通常のPython 3.9以降で動き、Mayaは不要。
"""

import argparse
import ast
import builtins
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "maya" / "inhouse" / "mlib"
DEST = SOURCE
PACKAGE = "mlib"
SKIP_DIRS = {"__tests__", "_docs", "__pycache__"}
# 生成したスタブの先頭行。この印で始まる .pyi だけを、元の .py が無くなったときに削除する。
HEADER_MARK = "# tools/generate_mlib_stubs.py が"
HEADER = HEADER_MARK + " mlib の docstring から生成した型スタブ。直接編集しない。\n"

# スタブへ残すデコレーター。ほかの(Undo等の)デコレーターは引数と戻り値を変えないため省く。
KEPT_DECORATORS = {"property", "staticmethod", "classmethod", "dataclass", "total_ordering"}
CONTEXT_MANAGERS = {"contextmanager", "contextlib.contextmanager"}
TYPING_NAMES = {"Any", "Callable", "ContextManager", "Dict", "Generator", "Iterable", "Iterator",
                "Hashable", "List", "Literal", "Mapping", "NoReturn", "Optional", "Sequence", "Set", "TextIO",
                "Tuple", "Type", "Union"}
# モジュール名を付けずに書かれた標準ライブラリの型と、型の式で使うモジュールのimport。
QUALIFIED = {"NotImplementedType": "types.NotImplementedType", "Match": "re.Match"}
MODULE_IMPORTS = {"types": "import types", "re": "import re", "contextlib": "import contextlib",
                  "om2": "import maya.api.OpenMaya as om2"}
# docstring で使われる、型名ではない慣用の呼び方の読み替え。
ALIASES = {"module": "ModuleType", "callable": "Callable[..., Any]", "function": "Callable[..., Any]",
           "iterable": "Iterable[Any]", "sequence": "Sequence[Any]", "any": "Any"}
GENERIC_ALIASES = {"iterable": "Iterable", "sequence": "Sequence"}
# docstring の型を置き換える型。ContextDecorator は with に使える型として扱われない。
REPLACEMENTS = {"contextlib.ContextDecorator": "ContextDecorator"}
# 基底クラスへスタブだけで足すメンバー。mlib.getNode() 等は実際の型の派生クラス(Joint等)を返すが
# 型は基底の Node になるため、派生クラスのメソッドを使うと「属性が無い」と警告される。
# 未定義の属性を Any とみなし、基底クラスのメソッドの補完は残したまま、その警告を出さない。
LENIENT_GETATTR = "def __getattr__(self, name: str) -> Any: ..."
LENIENT_MEMBERS = {
    "Object": {"__getattr__": LENIENT_GETATTR},
    "Node": {"__getattr__": LENIENT_GETATTR},
    "Component": {"__getattr__": LENIENT_GETATTR},
    # getPlug() はマルチ・コンパウンドアトリビュートでも Plug 型になるため、[] と for も受け付ける。
    "Plug": {"__getattr__": LENIENT_GETATTR,
             "__getitem__": "def __getitem__(self, key: int | str) -> Plug: ...",
             "__iter__": "def __iter__(self) -> Iterator[Plug]: ..."},
}
# 置き換え先の型の定義。生成先の mlib/_stubtypes.pyi に書き出す(実行時には存在しないモジュール)。
STUB_TYPES = '''# tools/generate_mlib_stubs.py が生成した、スタブだけで使う補助の型。実行時には存在しない。
import contextlib
from typing import Any, Callable, Generic, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])
_T = TypeVar("_T")


class ContextDecorator(contextlib.ContextDecorator, contextlib.AbstractContextManager[Any]):
    """with とデコレーターの両方に使えるコンテキスト。"""

    def __call__(self, func: _F) -> _F: ...


class GeneratorContextManager(contextlib.ContextDecorator, contextlib.AbstractContextManager[_T], Generic[_T]):
    """contextlib.contextmanager が返す、with とデコレーターの両方に使えるコンテキスト。"""

    def __enter__(self) -> _T: ...

    def __call__(self, func: _F) -> _F: ...
'''
BUILTIN_NAMES = set(dir(builtins))
SECTION = re.compile(r"^(\s*)(Args|Arguments|Returns|Yields|Raises|Note|Notes|Example|Examples"
                     r"|Attributes|Warning|Warnings|See Also|Todo):\s*$")
ARG_LINE = re.compile(r"^\s*(\*{0,2}[A-Za-z_]\w*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*:")


def _section_lines(doc, names):
    """docstring の指定セクション(Args等)の本文行を返す。

    Args:
        doc (str): ``inspect.cleandoc`` 済みの docstring。
        names (set[str]): 対象セクション名。

    Returns:
        list[str]: セクション見出しの次の行から、次の見出しの前までの行。無ければ空リスト。
    """
    lines = doc.splitlines()
    result, inside, indent = [], False, 0
    for line in lines:
        match = SECTION.match(line)
        if match:
            inside, indent = match.group(2) in names, len(match.group(1))
            continue
        if inside:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            result.append(line)
    return result


def _arg_types(doc):
    """``Args:`` の ``name (type):`` から引数名と型の文字列の対応を返す。

    Args:
        doc (str): docstring。

    Returns:
        dict[str, str]: ``*`` を除いた引数名から型の文字列への対応。
    """
    types = {}
    for line in _section_lines(doc, {"Args", "Arguments"}):
        match = ARG_LINE.match(line)
        if match:
            text = re.sub(r",\s*optional\s*$", "", match.group(2).strip())
            types.setdefault(match.group(1).lstrip("*"), text)
    return types


def _first_entry_type(lines):
    """セクション本文の最初の項目 ``type: 説明`` から型の文字列を返す。

    Args:
        lines (list[str]): セクションの本文行。

    Returns:
        str | None: 型の文字列。見つからなければNone。
    """
    for line in lines:
        if line.strip():
            match = re.match(r"^\s*(.+?):(\s|$)", line)
            return match.group(1).strip() if match else None
    return None


def _return_type(doc, is_property=False):
    """docstring から戻り値の型の文字列を返す。

    ``Returns:`` が無いプロパティは、Google 形式の先頭行 ``type: 説明`` を使う。
    ``Yields:`` はジェネレーターとして ``Iterator[...]`` に包む。

    Args:
        doc (str): docstring。
        is_property (bool): プロパティの getter か。

    Returns:
        str | None: 型の文字列。見つからなければNone。
    """
    text = _first_entry_type(_section_lines(doc, {"Returns"}))
    if text:
        return text
    text = _first_entry_type(_section_lines(doc, {"Yields"}))
    if text:
        return "Iterator[%s]" % text
    if is_property:
        return _first_entry_type(doc.splitlines()[:1])
    return None


def _is_accessor(node):
    """property の setter・deleter の定義(同じ名前の2つ目の def)かを返す。

    Args:
        node (ast.FunctionDef | ast.AsyncFunctionDef): 関数の定義。

    Returns:
        bool: ``@x.setter``・``@x.deleter`` が付いていればTrue。
    """
    return any(ast.unparse(d).endswith((".setter", ".deleter")) for d in node.decorator_list)


class _TypeChecker(ast.NodeVisitor):
    """型の式に許される構文かを調べ、使っている名前を集める。"""

    ALLOWED = (ast.Expression, ast.Name, ast.Attribute, ast.Subscript, ast.Tuple, ast.List,
               ast.BinOp, ast.BitOr, ast.Load, ast.Index if hasattr(ast, "Index") else ast.Load)

    def __init__(self):
        self.names = set()
        self.ok = True

    def generic_visit(self, node):
        if isinstance(node, ast.Constant):
            # None・...・Literal の値だけを許す。
            if not (node.value is None or node.value is Ellipsis or isinstance(node.value, (str, int, bool))):
                self.ok = False
            return
        if not isinstance(node, self.ALLOWED):
            self.ok = False
            return
        if isinstance(node, ast.BinOp) and not isinstance(node.op, ast.BitOr):
            self.ok = False
            return
        if isinstance(node, ast.Name):
            self.names.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                self.names.add(root.id)
                return
            self.ok = False
            return
        super().generic_visit(node)


class ModuleStub:
    """1モジュール分のスタブを組み立てる。

    Args:
        name (str): ``mlib.nodes.node`` のようなモジュールの完全名。
        path (Path): 元の ``.py``。
        index (dict[str, str]): クラス名から定義モジュールの完全名への対応。
        overloads (dict[str, Callable]): ``Class.method`` 等の修飾名からオーバーロードの生成関数。
    """

    def __init__(self, name, path, index, overloads, collections=None):
        self.name = name
        self.path = path
        self.source = path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)
        self.index = index
        self.overloads = overloads
        self.collections = collections or {}
        self.bound = set()
        self.variables = set()
        self.imports = []
        self.extra_imports = {}
        self.typing = set()
        self.unresolved = []
        self.is_package = path.name == "__init__.py"

    # --- 名前と型 ---------------------------------------------------------------

    def _collect_bound(self):
        """モジュール直下で定義・importされる名前を集める。"""
        for stmt in self._top_level(self.tree.body):
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                for alias in stmt.names:
                    self.bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.bound.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self.bound.add(target.id)
                        if self._namedtuple_fields(stmt.value) is None:
                            self.variables.add(target.id)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                self.bound.add(stmt.target.id)
                self.variables.add(stmt.target.id)

    @staticmethod
    def _top_level(body):
        """モジュール直下の文を、``if``・``try`` の中も含めて順に返す。

        Args:
            body (list[ast.stmt]): 文の列。

        Yields:
            ast.stmt: 関数・クラスの中を除く文。
        """
        for stmt in body:
            if isinstance(stmt, ast.If):
                yield from ModuleStub._top_level(stmt.body)
                yield from ModuleStub._top_level(stmt.orelse)
            elif isinstance(stmt, ast.Try):
                yield from ModuleStub._top_level(stmt.body)
                for handler in stmt.handlers:
                    yield from ModuleStub._top_level(handler.body)
            else:
                yield stmt

    def _resolve_name(self, name):
        """型の式に出てくる名前を、スタブの中で使えるようにする。

        Args:
            name (str): 名前。

        Returns:
            bool: 使える(またはimportを追加した)ならTrue。
        """
        if name in self.variables:
            # 変数は型の式に使えない。
            return False
        if name in self.bound or name in BUILTIN_NAMES:
            return True
        if name in TYPING_NAMES:
            self.typing.add(name)
            return True
        if name == "ModuleType":
            self.extra_imports["ModuleType"] = "from types import ModuleType"
            return True
        if name == "ContextDecorator":
            self.extra_imports[name] = "from mlib._stubtypes import ContextDecorator"
            return True
        if name in MODULE_IMPORTS:
            self.extra_imports[name] = MODULE_IMPORTS[name]
            return True
        module = self.index.get(name)
        if module:
            if module != self.name:
                self.extra_imports[name] = "from %s import %s" % (module, name)
            return True
        return False

    def annotation(self, text, where):
        """docstring の型の文字列を、スタブの注釈として使える文字列にする。

        Args:
            text (str | None): docstring の型の文字列。
            where (str): 省いた場合の報告に使う場所の名前。

        Returns:
            str | None: 注釈の文字列。使えなければNone。
        """
        if not text:
            return None
        text = ALIASES.get(text) or text
        for word, replacement in ALIASES.items():
            text = re.sub(r"(?<![\w.])%s(?![\w.\[])" % word, replacement, text)
        for word, replacement in GENERIC_ALIASES.items():
            text = re.sub(r"(?<![\w.])%s\[" % word, replacement + "[", text)
        for word, replacement in REPLACEMENTS.items():
            text = text.replace(word, replacement)
        for word, replacement in QUALIFIED.items():
            text = re.sub(r"(?<![\w.])%s(?![\w])" % word, replacement, text)
        # OpenMayaのクラスは om2.MObject のように書くが、MObject とだけ書かれた場合も補う。
        text = re.sub(r"(?<![\w.])(M[A-Z]\w+)", lambda m: m.group(1) if m.group(1) in self.bound
                      else "om2." + m.group(1), text)
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError:
            self.unresolved.append((where, text, "syntax"))
            return None
        checker = _TypeChecker()
        checker.visit(tree)
        if not checker.ok:
            self.unresolved.append((where, text, "not a type expression"))
            return None
        missing = sorted(name for name in checker.names if not self._resolve_name(name))
        if missing:
            self.unresolved.append((where, text, "unknown " + ", ".join(missing)))
            return None
        return text

    # --- 出力 -------------------------------------------------------------------

    def _docstring(self, node, indent):
        """定義の docstring を元のソースのまま書き出す行を返す。

        Args:
            node (ast.AST): モジュール・クラス・関数。
            indent (str): 書き出す字下げ。

        Returns:
            list[str]: docstring の行。無ければ空リスト。
        """
        body = getattr(node, "body", None)
        if not (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            return []
        segment = ast.get_source_segment(self.source, body[0].value)
        return [indent + segment] if segment else []

    def _params(self, args, doc_types, qualname, overrides=None, kwonly_from=None):
        """引数リストを注釈付きの文字列にする。

        Args:
            args (ast.arguments): 元の引数。
            doc_types (dict[str, str]): docstring の引数の型。
            qualname (str): 報告用の修飾名。
            overrides (dict[str, tuple[str, bool]] | None): 引数名から(注釈, 既定値を持つか)。
            kwonly_from (str | None): この引数以降をキーワード専用にする。

        Returns:
            str: ``self, name: str = ...`` のような引数リスト。
        """
        overrides = overrides or {}
        positional = list(args.posonlyargs) + list(args.args)
        defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
        parts = []

        def render(arg, has_default):
            if arg.arg in overrides:
                note, has_default = overrides[arg.arg]
            elif arg.annotation is not None:
                note = ast.unparse(arg.annotation)
            elif arg.arg in ("self", "cls"):
                note = None
            else:
                note = self.annotation(doc_types.get(arg.arg), "%s(%s)" % (qualname, arg.arg))
            text = arg.arg + (": " + note if note else "")
            if has_default:
                text += " = ..." if note else "=..."
            return text

        kwonly_started = False
        for position, (arg, default) in enumerate(zip(positional, defaults)):
            if kwonly_from and arg.arg == kwonly_from and not args.vararg:
                parts.append("*")
                kwonly_started = True
            if kwonly_started:
                parts.append(render(arg, default is not None))
                continue
            parts.append(render(arg, default is not None))
            if args.posonlyargs and position == len(args.posonlyargs) - 1:
                parts.append("/")
        if args.vararg:
            note = args.vararg.annotation and ast.unparse(args.vararg.annotation)
            note = note or self.annotation(doc_types.get(args.vararg.arg), "%s(*%s)" % (qualname, args.vararg.arg))
            parts.append("*" + args.vararg.arg + (": " + note if note else ""))
        elif args.kwonlyargs and not kwonly_started:
            parts.append("*")
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            parts.append(render(arg, default is not None))
        if args.kwarg:
            note = args.kwarg.annotation and ast.unparse(args.kwarg.annotation)
            note = note or self.annotation(doc_types.get(args.kwarg.arg), "%s(**%s)" % (qualname, args.kwarg.arg))
            parts.append("**" + args.kwarg.arg + (": " + note if note else ""))
        return ", ".join(parts)

    def _function(self, node, indent, qualname, in_class):
        """関数・メソッドのスタブ行を返す。

        Args:
            node (ast.FunctionDef | ast.AsyncFunctionDef): 元の定義。
            indent (str): 字下げ。
            qualname (str): ``Class.method`` のような修飾名。
            in_class (bool): クラスの中の定義か。

        Returns:
            list[str]: スタブの行。
        """
        doc = ast.get_docstring(node) or ""
        decorators, is_property, is_context = [], False, False
        for decorator in node.decorator_list:
            text = ast.unparse(decorator)
            if text in CONTEXT_MANAGERS:
                is_context = True
            elif text in KEPT_DECORATORS or text.endswith((".setter", ".deleter")):
                decorators.append(text)
                is_property = is_property or text == "property"
        lines = []
        for variant in self.overloads.get("%s:%s" % (self.name, qualname), lambda stub, fn: [])(self, node):
            self.typing.update({"Literal"})
            self.extra_imports["overload"] = "from typing import overload"
            lines += [indent + "@overload", indent + variant]
        if lines:
            lines.append(indent + "@overload")
        lines += [indent + "@" + text for text in decorators]
        returns = ast.unparse(node.returns) if node.returns is not None else None
        if returns is None:
            override = self.overloads.get("%s:%s#return" % (self.name, qualname))
            returns = override(self, node) if override else self.annotation(
                _return_type(doc, is_property), qualname + "(return)")
            if returns and re.fullmatch(r"object( \| None)?", returns):
                # docstring の object は「任意の値」の意味。戻り値を object にすると、受け取った値を
                # float や str として使うたびに警告になるため Any にする。
                self.typing.add("Any")
                returns = "Any"
        if is_context:
            # contextmanager の戻り値は with にもデコレーターにも使える(ContextDecorator)。
            returns = "GeneratorContextManager[%s]" % (returns[len("Iterator["):-1] if returns and returns.startswith(
                "Iterator[") else "Any")
            self.typing.add("Any")
            self.extra_imports["GeneratorContextManager"] = "from mlib._stubtypes import GeneratorContextManager"
        if returns is None and node.name == "__init__":
            returns = "None"
        if in_class and node.name == "__new__":
            # docstring は基底の型(Node等)で書かれているため、Joint(...) 等の構築結果が基底の型にならないよう
            # 呼び出したクラス自身を返すとする。
            self.extra_imports["Self"] = "from typing_extensions import Self"
            returns = "Self"
        keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        signature = "%s %s(%s)%s:" % (keyword, node.name, self._params(node.args, _arg_types(doc), qualname),
                                      " -> " + returns if returns else "")
        docstring = self._docstring(node, indent + "    ")
        if docstring:
            lines += [indent + signature] + docstring + [indent + "    ..."]
        else:
            lines.append(indent + signature + " ...")
        return lines

    def _value_type(self, value):
        """代入の右辺から、スタブで使う変数の型を推定する。

        Args:
            value (ast.expr): 右辺。

        Returns:
            str: 型の文字列。分からなければ ``Any``。
        """
        if isinstance(value, ast.Constant):
            return "None" if value.value is None else type(value.value).__name__
        literal = {ast.List: "list", ast.Tuple: "tuple", ast.Dict: "dict", ast.Set: "set",
                   ast.ListComp: "list", ast.DictComp: "dict", ast.SetComp: "set"}
        for kind, text in literal.items():
            if isinstance(value, kind):
                return text
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            name = value.func.id
            if name in ("frozenset", "set", "dict", "list", "tuple", "str", "int", "float"):
                return name
            if name[:1].isupper() and self._resolve_name(name):
                return name
        self.typing.add("Any")
        return "Any"

    def _class(self, node, indent, prefix=""):
        """クラスのスタブ行を返す。

        Args:
            node (ast.ClassDef): 元の定義。
            indent (str): 字下げ。
            prefix (str): 入れ子のクラスの修飾名の前置き。

        Returns:
            list[str]: スタブの行。
        """
        qualname = prefix + node.name
        lines = ["@" + ast.unparse(d) for d in node.decorator_list if ast.unparse(d) in KEPT_DECORATORS]
        lines = [indent + line for line in lines]
        bases = [ast.unparse(base) for base in node.bases] + [ast.unparse(k) for k in node.keywords]
        lines.append(indent + "class %s%s:" % (node.name, "(%s)" % ", ".join(bases) if bases else ""))
        inner = indent + "    "
        body = self._docstring(node, inner)
        defined = set()
        item = self.collections.get(node.name)
        if item:
            # コレクションの要素の型を補う(docstring は Node・Component 等の基底型で書かれている)。
            self.typing.update({"Iterator"})
            self.extra_imports["overload"] = "from typing import overload"
            self._resolve_name(item)
            body += [inner + "def __iter__(self) -> Iterator[%s]: ..." % item,
                     inner + "@overload", inner + "def __getitem__(self, index: int) -> %s: ..." % item,
                     inner + "@overload", inner + "def __getitem__(self, index: slice) -> %s: ..." % node.name]
            defined.update({"__iter__", "__getitem__"})
        for stmt in node.body:
            if (isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in defined
                    and not _is_accessor(stmt)):
                continue
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__call__" and "type" in bases:
                # メタクラスの __call__ に戻り値の型があると、pyright は Container(...) 等の構築結果を
                # その型(Object)とみなす。省けば各クラスの __new__・__init__ から型を求める。
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body += self._function(stmt, inner, qualname + "." + stmt.name, True)
                defined.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                body += self._class(stmt, inner, qualname + ".")
                defined.add(stmt.name)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                body.append(inner + "%s: %s" % (stmt.target.id, ast.unparse(stmt.annotation))
                            + (" = ..." if stmt.value is not None else ""))
                defined.add(stmt.target.id)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id not in defined:
                        body.append(inner + "%s: %s" % (target.id, self._value_type(stmt.value)))
                        defined.add(target.id)
        # __init__ で設定する公開の属性も補完に出す。
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
                for sub in ast.walk(stmt):
                    targets = sub.targets if isinstance(sub, ast.Assign) else (
                        [sub.target] if isinstance(sub, ast.AnnAssign) else [])
                    for target in targets:
                        if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                                and target.value.id == "self" and not target.attr.startswith("_")
                                and target.attr not in defined):
                            self.typing.add("Any")
                            body.append(inner + "%s: Any" % target.attr)
                            defined.add(target.attr)
        for name, text in LENIENT_MEMBERS.get(qualname, {}).items():
            if name not in defined:
                self.typing.update({"Any", "Iterator"})
                body.append(inner + text)
        if not body:
            body = [inner + "..."]
        return lines + body

    @staticmethod
    def _namedtuple_fields(value):
        """``namedtuple("Name", ("a", "b"))`` の形なら、フィールド名を返す。

        Args:
            value (ast.expr): 代入の右辺。

        Returns:
            list[str] | None: フィールド名。namedtuple でなければNone。
        """
        if not (isinstance(value, ast.Call) and ast.unparse(value.func) in ("namedtuple", "collections.namedtuple")
                and len(value.args) == 2):
            return None
        fields = value.args[1]
        if isinstance(fields, ast.Constant) and isinstance(fields.value, str):
            return fields.value.replace(",", " ").split()
        if isinstance(fields, (ast.List, ast.Tuple)) and all(isinstance(e, ast.Constant) for e in fields.elts):
            return [str(e.value) for e in fields.elts if isinstance(e, ast.Constant)]
        return None

    def _all_names(self, value):
        """``__all__`` の右辺から公開名の一覧を求める。

        リテラルのほか、遅延公開の ``sorted(_exports)`` のように辞書リテラルのキーから作る形に対応する。

        Args:
            value (ast.expr): ``__all__`` の右辺。

        Returns:
            list[str] | None: 公開名。求められなければNone。
        """
        if isinstance(value, (ast.List, ast.Tuple)):
            names = [item.value for item in value.elts if isinstance(item, ast.Constant)]
            return names if len(names) == len(value.elts) else None
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("sorted", "list")
                and len(value.args) == 1 and isinstance(value.args[0], ast.Name)):
            for stmt in self._top_level(self.tree.body):
                if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict)
                        and any(isinstance(t, ast.Name) and t.id == value.args[0].id for t in stmt.targets)):
                    return sorted(str(key.value) for key in stmt.value.keys if isinstance(key, ast.Constant))
        return None

    def render(self):
        """スタブ全体の文字列を返す。

        Returns:
            str: ``.pyi`` の内容。
        """
        self._collect_bound()
        body, defined = [], set()
        for stmt in self._top_level(self.tree.body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                continue
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                self.imports.append(ast.unparse(stmt))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name not in defined:
                body += [""] + self._function(stmt, "", stmt.name, False)
                defined.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef) and stmt.name not in defined:
                body += ["", ""] + self._class(stmt, "")
                defined.add(stmt.name)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if stmt.target.id not in defined:
                    body.append("%s: %s" % (stmt.target.id, ast.unparse(stmt.annotation)))
                    defined.add(stmt.target.id)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if not isinstance(target, ast.Name) or target.id in defined:
                        continue
                    defined.add(target.id)
                    names = self._all_names(stmt.value) if target.id == "__all__" else None
                    fields = self._namedtuple_fields(stmt.value)
                    if fields is not None:
                        # namedtuple は型の式に使われるため、変数ではなくクラスとして書き出す。
                        self.typing.update({"NamedTuple", "Any"})
                        body += ["", "class %s(NamedTuple):" % target.id] + [
                            "    %s: Any" % field for field in fields]
                    elif names is not None:
                        # スタブではimportした名前は __all__ に無いと公開扱いにならない。
                        body.append("__all__ = " + repr(names))
                    elif isinstance(stmt.value, ast.Name) and stmt.value.id in defined:
                        # 同じモジュールのクラス・関数の別名(MultDL = MultDoubleLinear 等)は別名のまま書き出す。
                        body.append("%s = %s" % (target.id, stmt.value.id))
                    elif target.id != "__all__":
                        body.append("%s: %s" % (target.id, self._value_type(stmt.value)))
        head = [HEADER.rstrip("\n")] + self._docstring(self.tree, "")
        imports = list(dict.fromkeys(self.imports))
        if self.typing:
            imports.append("from typing import " + ", ".join(sorted(self.typing)))
        imports += sorted(set(self.extra_imports.values()) - set(imports))
        return "\n".join(head + [""] + imports + [""] + body).rstrip() + "\n"


# --- 引数で戻り値が変わるAPIのオーバーロード -------------------------------------


def _wrapper_classes():
    """``nodes/__init__.py`` の ``_WRAPPER_CLASSES`` から、Mayaの型名とクラス名の対応を読む。

    Returns:
        dict[str, str]: Mayaの型名からクラス名への対応。
    """
    tree = ast.parse((SOURCE / "nodes" / "__init__.py").read_text(encoding="utf-8"))
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict)
                and any(isinstance(t, ast.Name) and t.id == "_WRAPPER_CLASSES" for t in stmt.targets)):
            return {str(key.value): value.id for key, value in zip(stmt.value.keys, stmt.value.values)
                    if isinstance(key, ast.Constant) and isinstance(value, ast.Name)}
    raise RuntimeError("_WRAPPER_CLASSES is not found in nodes/__init__.py")


# ls(type=...) の特別な戻り値。joint・skinCluster は専用コレクション、component はその要素群
# (0件はシェイプが決まらないため空の Nodes)。それ以外のノード型は Nodes。
LS_SPECIAL = {"joint": "Joints", "skinCluster": "SkinClusters", "vertex": "Vertices | Nodes", "edge": "Edges | Nodes",
              "face": "Faces | Nodes", "uv": "UVs | Nodes", "controlVertex": "CVs | Nodes"}


def _ls_overloads(stub, node):
    """``ls`` の ``type`` ごとのオーバーロードを返す。

    Args:
        stub (ModuleStub): 出力中のモジュール。
        node (ast.FunctionDef): ``ls`` の定義。

    Returns:
        list[str]: ``def ls(...) -> ...: ...`` の行。
    """
    doc_types = _arg_types(ast.get_docstring(node) or "")
    table = {name: "Nodes" for name in _wrapper_classes()}
    table.update(LS_SPECIAL)
    variants = []
    for maya_type, returns in sorted(table.items()):
        stub.annotation(returns, "ls")
        params = stub._params(node.args, doc_types, "ls", {"type": ('Literal["%s"]' % maya_type, False)})
        variants.append("def ls(%s) -> %s: ..." % (params, returns))
    stub.annotation("Nodes", "ls")
    params = stub._params(node.args, doc_types, "ls", {"type": ("str", False)})
    variants.append("def ls(%s) -> Nodes: ..." % params)
    return variants


def _ls_return(stub, node):
    """``type`` を指定しない ``ls`` の戻り値。

    Args:
        stub (ModuleStub): 出力中のモジュール。
        node (ast.FunctionDef): ``ls`` の定義。

    Returns:
        str: 戻り値の注釈。
    """
    return stub.annotation(
        "Nodes | Plugs | Vertices | Edges | Faces | UVs | CVs | list[Node | Plug | Component]", "ls(return)")


def _connection_variants(stub, node, qualname):
    """``getConnections`` の ``asPair``・``asNode``・``index`` ごとのオーバーロードを返す。

    ``c``・``connections`` によるペア指定は最後の汎用の定義(戻り値は全候補の合併)で受ける。

    Args:
        stub (ModuleStub): 出力中のモジュール。
        node (ast.FunctionDef): ``getConnections`` の定義。
        qualname (str): 報告用の修飾名。

    Returns:
        list[str]: ``def getConnections(...) -> ...: ...`` の行。
    """
    true, false = ("Literal[True]", False), ("Literal[False]", True)
    no_pair = {"c": false, "connections": false, "asPair": false}
    cases = [
        ({"asPair": true, "asNode": true, "index": ("int", False)}, "tuple[Plug, Node] | None"),
        ({"asPair": true, "asNode": true, "index": ("None", True)}, "list[tuple[Plug, Node]]"),
        ({"asPair": true, "asNode": false, "index": ("int", False)}, "tuple[Plug, Plug] | None"),
        ({"asPair": true, "asNode": false, "index": ("None", True)}, "list[tuple[Plug, Plug]]"),
        (dict(no_pair, asNode=true, index=("int", False)), "Node | None"),
        (dict(no_pair, asNode=true, index=("None", True)), "list[Node]"),
        (dict(no_pair, asNode=false, index=("int", False)), "Plug | None"),
        (dict(no_pair, asNode=false, index=("None", True)), "list[Plug]"),
    ]
    doc_types = _arg_types(ast.get_docstring(node) or "")
    variants = []
    for overrides, returns in cases:
        stub.annotation(returns, qualname)
        params = stub._params(node.args, doc_types, qualname, overrides, kwonly_from="asPair")
        variants.append("def getConnections(%s) -> %s: ..." % (params, returns))
    return variants


def _keyword_connection_variants(stub, node, single):
    """``getSource``・``getDestinations`` の、``**kwargs`` で受ける指定ごとのオーバーロードを返す。

    Args:
        stub (ModuleStub): 出力中のモジュール。
        node (ast.FunctionDef): 元の定義。
        single (bool): Trueは常に一件(``getSource``)、Falseは ``index`` の有無で一件か一覧。

    Returns:
        list[str]: オーバーロードの行。
    """
    stub.typing.update({"Any", "Literal"})
    pairs = [("asPair: Literal[True], asNode: Literal[True]", "tuple[Plug, Node]"),
             ("asPair: Literal[True], asNode: Literal[False] = ...", "tuple[Plug, Plug]"),
             ("asPair: Literal[False] = ..., asNode: Literal[True]", "Node"),
             ("asPair: Literal[False] = ..., asNode: Literal[False] = ...", "Plug")]
    head = "self, *, skipConversionNodes: bool = ..., type: str | None = ..., exactType: bool = ..., "
    variants = []
    for flags, item in pairs:
        stub.annotation(item, node.name)
        if single:
            variants.append("def %s(%s%s, **kwargs: Any) -> %s | None: ..." % (node.name, head, flags, item))
        else:
            variants.append("def %s(%s%s, index: int, **kwargs: Any) -> %s | None: ..." % (
                node.name, head, flags, item))
            variants.append("def %s(%s%s, index: None = ..., **kwargs: Any) -> list[%s]: ..." % (
                node.name, head, flags, item))
    return variants


def _get_type_overloads(stub):
    """``Node.getType`` の ``inherited`` ごとのオーバーロードを返す。

    Args:
        stub (ModuleStub): 出力中のモジュール。

    Returns:
        list[str]: オーバーロードの行。
    """
    stub.typing.add("Literal")
    return ["def getType(self, inherited: Literal[True]) -> list[str]: ...",
            "def getType(self, inherited: Literal[False] = ...) -> str: ..."]


def _angle_unit_overloads(stub):
    """既定値があれば None を返さないことを表す ``util._angle_unit`` のオーバーロードを返す。

    Args:
        stub (ModuleStub): 出力中のモジュール。

    Returns:
        list[str]: オーバーロードの行。
    """
    return ["def _angle_unit(unit: str | None, default: str = ...) -> str: ...",
            "def _angle_unit(unit: str | None, default: None) -> str | None: ..."]


def _create_node_overloads(stub, node):
    """``createNode`` の登録済みの型名ごとのオーバーロードを返す。

    作成したノードは指定した型そのものなので、登録表のクラスで返る。

    Args:
        stub (ModuleStub): 出力中のモジュール。
        node (ast.FunctionDef): ``createNode`` の定義。

    Returns:
        list[str]: ``def createNode(...) -> ...: ...`` の行。
    """
    doc_types = _arg_types(ast.get_docstring(node) or "")
    variants = []
    for maya_type, cls in sorted(_wrapper_classes().items()):
        stub.annotation(cls, "createNode")
        params = stub._params(node.args, doc_types, "createNode", {"type": ('Literal["%s"]' % maya_type, False)})
        variants.append("def createNode(%s) -> %s: ..." % (params, cls))
    return variants


OVERLOADS = {
    "mlib.cmds.createNode:createNode": _create_node_overloads,
    "mlib.nodes.node:Node.getType": lambda stub, node: _get_type_overloads(stub),
    "mlib.util:_angle_unit": lambda stub, node: _angle_unit_overloads(stub),
    "mlib.cmds.ls:ls": _ls_overloads,
    "mlib.cmds.ls:ls#return": _ls_return,
    "mlib.nodes.node:Node.getConnections": lambda stub, node: _connection_variants(
        stub, node, "Node.getConnections"),
    "mlib.plugs.plug:Plug.getConnections": lambda stub, node: _connection_variants(
        stub, node, "Plug.getConnections"),
    "mlib.plugs.plug:Plug.getSource": lambda stub, node: _keyword_connection_variants(stub, node, True),
    "mlib.plugs.plug:Plug.getDestinations": lambda stub, node: _keyword_connection_variants(stub, node, False),
}


# --- 全体 -------------------------------------------------------------------------


def _modules(source):
    """スタブを作る ``.py`` と、そのモジュールの完全名を返す。

    Args:
        source (Path): mlib パッケージのフォルダー。

    Returns:
        list[tuple[str, Path]]: (完全名, パス) のリスト。
    """
    result = []
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        if SKIP_DIRS.intersection(relative.parts):
            continue
        parts = [PACKAGE] + list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        result.append((".".join(parts), path))
    return result


def _class_index(modules):
    """クラス名から定義モジュールへの対応を作る。

    同じ名前のクラスが複数ある場合は、パッケージの階層が浅い方(公開の入口に近い方)を使う。

    Args:
        modules (list[tuple[str, Path]]): (完全名, パス) のリスト。

    Returns:
        dict[str, str]: クラス名からモジュールの完全名への対応。
    """
    index = {}
    for name, path in modules:
        for stmt in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(stmt, ast.ClassDef) and not stmt.name.startswith("_"):
                current = index.get(stmt.name)
                if current is None or name.count(".") < current.count("."):
                    index[stmt.name] = name
    return index


COLLECTION_ROOTS = {"Nodes", "Components", "Plugs"}


def _collections(modules):
    """複数形のコレクションクラスと、その要素のクラスの対応をモジュールごとに求める。

    ``Nodes``・``Components``・``Plugs`` の派生を複数形のクラスとし、同じファイルにある単数形のクラス
    (名前の先頭が最も長く一致するもの。例: Joints → Joint、Vertices → Vertex)を要素とする。

    Args:
        modules (list[tuple[str, Path]]): (完全名, パス) のリスト。

    Returns:
        dict[str, dict[str, str]]: モジュールの完全名から{複数形のクラス名: 要素のクラス名}。

    Raises:
        RuntimeError: 要素のクラスが同じファイルに見つからない場合。
    """
    bases, classes = {}, {}
    for name, path in modules:
        for stmt in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(stmt, ast.ClassDef):
                bases[stmt.name] = [b.id for b in stmt.bases if isinstance(b, ast.Name)]
                classes.setdefault(name, []).append(stmt.name)

    def is_collection(cls, seen=()):
        if cls in COLLECTION_ROOTS:
            return True
        return any(base not in seen and is_collection(base, seen + (cls,)) for base in bases.get(cls, ()))

    def common(a, b):
        size = 0
        while size < min(len(a), len(b)) and a[size] == b[size]:
            size += 1
        return size

    result = {}
    for module, names in classes.items():
        for cls in names:
            if not is_collection(cls):
                continue
            singles = [n for n in names if not is_collection(n) and not n.startswith("_")]
            if not singles:
                raise RuntimeError("the element class of %s.%s is not found" % (module, cls))
            result.setdefault(module, {})[cls] = max(singles, key=lambda n: common(n, cls))
    return result


def generate(dest):
    """スタブを ``dest`` の下に書き出す。

    Args:
        dest (Path): 出力先(``mlib`` パッケージに当たるフォルダー)。

    Returns:
        list[tuple[str, str, str, str]]: 省いた注釈の(モジュール, 場所, 型の文字列, 理由)。
    """
    modules = _modules(SOURCE)
    index = _class_index(modules)
    collections = _collections(modules)
    unresolved = []
    for name, path in modules:
        stub = ModuleStub(name, path, index, OVERLOADS, collections.get(name))
        text = stub.render()
        target = dest / path.relative_to(SOURCE).with_suffix(".pyi")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        unresolved += [(name,) + item for item in stub.unresolved]
    (dest / "_stubtypes.pyi").write_text(STUB_TYPES, encoding="utf-8", newline="\n")
    return unresolved


def _stub_files(root):
    """出力先にある ``.pyi`` を、相対パスから改行を揃えた内容への対応で返す。

    mlib の中の ``_docs``(Sphinx の仮想環境)と ``__tests__`` は対象外。Git の改行変換(CRLF)で
    内容が変わって見えないよう、改行は LF に揃えて比べる。

    Args:
        root (Path): 出力先。

    Returns:
        dict[Path, str]: 相対パスから内容への対応。
    """
    if not root.is_dir():
        return {}
    result = {}
    for path in root.rglob("*.pyi"):
        relative = path.relative_to(root)
        if not SKIP_DIRS.intersection(relative.parts):
            result[relative] = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return result


def _sync(work, dest):
    """作り直したスタブを出力先へ反映し、変更・削除したファイル数を返す。

    内容が同じファイルは書き換えない。出力先にだけある ``.pyi`` は、このスクリプトが作ったもの
    (先頭行が生成の印)だけを削除し、手書きのスタブは残す。

    Args:
        work (Path): 作り直したスタブのフォルダー。
        dest (Path): 出力先。

    Returns:
        tuple[int, int]: (書き込んだ数, 削除した数)。
    """
    fresh, current = _stub_files(work), _stub_files(dest)
    written = removed = 0
    for relative, text in fresh.items():
        if current.get(relative) != text:
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            written += 1
    for relative, text in current.items():
        if relative not in fresh and text.startswith(HEADER_MARK):
            (dest / relative).unlink()
            removed += 1
    return written, removed


def main(argv=None):
    """コマンドラインの入口。

    Args:
        argv (list[str] | None): 引数。Noneは ``sys.argv``。

    Returns:
        int: 終了コード。
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dest", type=Path, default=DEST, help="出力先(既定は mlib 本体のフォルダー)")
    parser.add_argument("--check", action="store_true", help="書き出さず、現在のスタブが最新かだけを確かめる")
    parser.add_argument("--report", action="store_true", help="省いた注釈を一覧表示する")
    options = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as work:
        work = Path(work) / PACKAGE
        unresolved = generate(work)
        if options.report:
            for module, where, text, reason in unresolved:
                print("%s: %s: %r (%s)" % (module, where, text, reason))
        if options.check:
            fresh, current = _stub_files(work), _stub_files(options.dest)
            stale = sorted(str(r) for r in set(fresh) | set(current)
                           if fresh.get(r) != current.get(r) and (r in fresh or current[r].startswith(HEADER_MARK)))
            if not stale:
                print("スタブは最新です: %s" % options.dest)
                return 0
            print("スタブが古いか、ありません(%d ファイル): %s" % (len(stale), ", ".join(stale[:5])))
            print("python tools/generate_mlib_stubs.py で作り直してください。")
            return 1
        written, removed = _sync(work, options.dest)
    print("スタブを更新しました: %s (書き込み %d、削除 %d、型を省いた注釈 %d 件)" % (
        options.dest, written, removed, len(unresolved)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
