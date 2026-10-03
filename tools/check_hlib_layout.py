"""hlib・hlib_* のレイアウト規則(import順・定数位置・空行・クラス内メンバー順)を検査・整形する。

規則の本文は docs/hlib-api-design.md「ファイル・クラスのレイアウト規則」。ast と tokenize だけを
使うため通常の Python で実行でき、hlib や Maya を import しない。

--check     規則違反を一覧表示する(違反があれば終了コード1)。
--fix       import群の並び替え・クラス内メンバーの並び替え・空行の正規化を書き込む。
--snapshot  各ファイルの関数本文・import束縛・モジュール文・コメントを JSON に保存する。
--compare   保存した JSON と現在のソースを比較し、差分があれば一覧表示して終了コード1。
--outline   クラスのメンバー構成(分類・行範囲)を表示する。
"""
import argparse
import ast
import collections
import copy
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("maya/inhouse/hlib", "maya/inhouse/hlib_bifrost", "maya/inhouse/hlib_posedriverconnect")
EXCLUDED_DIRS = {"__tests__", "tests", "docs", "__pycache__", ".logs"}
MAYA_PACKAGES = {"maya", "maya.api"}
MAYA_SUBMODULES = {"cmds", "mel", "utils", "standalone", "OpenMaya", "OpenMayaAnim", "OpenMayaUI", "OpenMayaRender"}
CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
STDLIB_NAMES = frozenset(getattr(sys, "stdlib_module_names", ()) or (
    "abc", "argparse", "ast", "base64", "builtins", "collections", "contextlib", "copy", "copyreg",
    "dataclasses", "datetime", "enum", "functools", "hashlib", "html", "importlib", "inspect", "io",
    "itertools", "json", "logging", "math", "numbers", "operator", "os", "pathlib", "pickle", "pkgutil",
    "re", "shutil", "string", "struct", "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
    "tokenize", "traceback", "types", "typing", "unittest", "uuid", "warnings", "weakref"))

ATTRIBUTE, INIT, SPECIAL, CLASS_PUBLIC, PROPERTY, PUBLIC, PRIVATE = range(7)
CATEGORY_LABELS = ("attribute", "init", "special", "classmethod", "property", "public", "private")
INIT_ORDER = {"__new__": 0, "__init__": 1, "__post_init__": 2}
OPERATORS = {"add", "sub", "mul", "matmul", "truediv", "floordiv", "mod", "divmod", "pow",
             "lshift", "rshift", "and", "xor", "or"}
DUNDER_FOLLOWERS = {
    "__ne__": (("__eq__",), 1), "__hash__": (("__eq__",), 2),
    "__str__": (("__repr__",), 1),
    "__setitem__": (("__getitem__",), 1), "__delitem__": (("__getitem__",), 2),
    "__deepcopy__": (("__copy__",), 1), "__exit__": (("__enter__",), 1),
    "__reduce_ex__": (("__reduce__",), 1),
}
PREFIX_PAIRS = (("disconnect", "connect"), ("unlock", "lock"), ("hide", "show"), ("remove", "add"))
INFORMATIONAL = {"L000", "L023"}
DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
IMPORTS = (ast.Import, ast.ImportFrom)
FSTRING_START = getattr(tokenize, "FSTRING_START", -1)
FSTRING_END = getattr(tokenize, "FSTRING_END", -2)


class Unsupported(Exception):
    """自動整形の対象外にするクラス構成。"""


class Violation:
    """検出した規則違反(またはスキップの通知)。"""

    def __init__(self, path, line, code, message):
        self.path = path
        self.line = line
        self.code = code
        self.message = message

    def __str__(self):
        return "{}:{}: {} {}".format(relative(self.path), self.line, self.code, self.message)


class Source:
    """1ファイル分のテキスト・AST・トークン情報。"""

    def __init__(self, path, text):
        self.path = path
        self.lines = text.split("\n")
        if self.lines and self.lines[-1] == "":
            self.lines.pop()
        self.tree = ast.parse(text, filename=str(path))
        self.string_lines = set()
        self.comment_lines = {}
        self.tokens = []
        fstring_starts = []
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            self.tokens.append(tok)
            if tok.type == tokenize.STRING:
                self.string_lines.update(range(tok.start[0] + 1, tok.end[0] + 1))
            elif tok.type == FSTRING_START:
                fstring_starts.append(tok.start[0])
            elif tok.type == FSTRING_END and fstring_starts:
                self.string_lines.update(range(fstring_starts.pop() + 1, tok.end[0] + 1))
            elif tok.type == tokenize.COMMENT and tok.line[:tok.start[1]].strip() == "":
                self.comment_lines[tok.start[0]] = tok.start[1]

    def is_blank(self, lineno):
        return lineno not in self.string_lines and self.lines[lineno - 1].strip() == ""

    def is_comment(self, lineno):
        return lineno in self.comment_lines

    def blank_count(self, line_numbers):
        return sum(1 for n in line_numbers if self.is_blank(n))

    def leading_comment_top(self, start, indent):
        """start 行の直上に空行を挟まず続く、indent 以下の字下げのコメント行の先頭行番号。"""
        line = start
        while line > 1 and self.is_comment(line - 1) and self.comment_lines[line - 1] <= indent:
            line -= 1
        return line

    def header_end(self, node):
        """def/class ヘッダーを閉じるコロンがある行番号を返す。"""
        depth = 0
        for tok in self.tokens:
            if tok.start[0] < node.lineno or (tok.start[0] == node.lineno and tok.start[1] < node.col_offset):
                continue
            if tok.type != tokenize.OP:
                continue
            if tok.string in "([{":
                depth += 1
            elif tok.string in ")]}":
                depth -= 1
            elif tok.string == ":" and depth == 0:
                return tok.start[0]
        return node.lineno


def relative(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def iter_files(targets):
    for target in targets:
        path = Path(target)
        if path.is_file():
            yield path
            continue
        for file in sorted(path.rglob("*.py")):
            if EXCLUDED_DIRS.isdisjoint(file.relative_to(path).parts[:-1]):
                yield file


def read_source(path):
    """テキストと、書き戻し用の改行コード・BOM の有無を返す。"""
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data[3:].decode("utf-8") if bom else data.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), eol, bom


def write_source(path, text, eol, bom):
    data = text.replace("\n", eol).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def load(path):
    text, eol, bom = read_source(path)
    return Source(path, text), eol, bom


def node_start(node):
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decorators])


def is_docstring(node):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def is_type_checking(node):
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
            or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"))


def is_import_like(node):
    return isinstance(node, IMPORTS) or is_type_checking(node)


def decorator_name(node):
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def clamp(value, low, high):
    return max(low, min(value, high))


# ---------------------------------------------------------------- import


def import_module_name(stmt):
    if isinstance(stmt, ast.Import):
        return stmt.names[0].name
    return "." * stmt.level + (stmt.module or "")


def import_sort_key(module, is_from):
    """(グループ, import/from, 大小無視のモジュール名, モジュール名)。isort の既定順に合わせる。"""
    if module == "__future__":
        group = -1
    elif module.startswith("."):
        group = 2
    else:
        group = 0 if module.split(".")[0] in STDLIB_NAMES else 1
    match = re.match(r"^(\.+)(.*)$", module)
    key = match.group(1) + "_" + match.group(2) if match else module
    return (group, 1 if is_from else 0, key.lower(), key)


def statement_key(stmt):
    return import_sort_key(import_module_name(stmt), isinstance(stmt, ast.ImportFrom))


def maya_import_conversion(stmt):
    """``from maya import cmds`` 形式を ``import maya.cmds as cmds`` へ変換する対応を返す。"""
    if not isinstance(stmt, ast.ImportFrom) or stmt.level or stmt.module not in MAYA_PACKAGES:
        return None
    if not all(alias.name in MAYA_SUBMODULES for alias in stmt.names):
        return None
    return [(stmt.module + "." + alias.name, alias.asname or alias.name) for alias in stmt.names]


def import_region(tree):
    """連続した import 群の (開始index, 終了index) を返す。整形できない構成なら理由を返す。"""
    body = tree.body
    first = next((i for i, stmt in enumerate(body) if isinstance(stmt, IMPORTS)), None)
    if first is None:
        return None, None
    if not all(is_docstring(stmt) for stmt in body[:first]):
        return None, "import群の前に文がある"
    last = first
    for index in range(first, len(body)):
        if is_import_like(body[index]):
            last = index
        else:
            break
    if any(isinstance(stmt, IMPORTS) for stmt in body[last + 1:]):
        return None, "import群の後に import がある"
    return (first, last), None


def import_entries(src, first, last):
    """import 群を (sort_key, 行テキスト, 文) の列と TYPE_CHECKING ブロックの列に分ける。"""
    body = src.tree.body
    entries = []
    type_checking = []
    region_start = src.leading_comment_top(node_start(body[first]), 0)
    prev_end = region_start - 1
    for stmt in body[first:last + 1]:
        top = src.leading_comment_top(node_start(stmt), 0)
        floating = [src.lines[n - 1] for n in range(prev_end + 1, top)]
        while floating and floating[0].strip() == "":
            floating.pop(0)
        while floating and floating[-1].strip() == "":
            floating.pop()
        leading = floating + [src.lines[n - 1] for n in range(top, node_start(stmt))]
        stmt_lines = [src.lines[n - 1] for n in range(stmt.lineno, stmt.end_lineno + 1)]
        prev_end = stmt.end_lineno
        if is_type_checking(stmt):
            type_checking.append(leading + stmt_lines)
            continue
        conversion = maya_import_conversion(stmt)
        if conversion and len(stmt_lines) == 1 and "#" not in stmt_lines[0]:
            for index, (module, binding) in enumerate(conversion):
                line = "import {} as {}".format(module, binding)
                entries.append((import_sort_key(module, False), (leading if index == 0 else []) + [line], stmt))
        else:
            entries.append((statement_key(stmt), leading + stmt_lines, stmt))
    return region_start, prev_end, entries, type_checking


def entry_label(entry):
    return next((line.strip() for line in entry[1] if not line.lstrip().startswith("#")), "")


def rewrite_imports(src):
    """import 群を規則どおりに並べ替えた置換 (start, end_exclusive, lines) を返す。"""
    region, _ = import_region(src.tree)
    if region is None:
        return None
    region_start, region_end, entries, type_checking = import_entries(src, *region)
    out = []
    group = None
    for key, lines, _ in sorted(entries, key=lambda entry: entry[0]):
        if group is not None and key[0] != group:
            out.append("")
        out.extend(lines)
        group = key[0]
    for block in type_checking:
        out.append("")
        out.extend(block)
    return (region_start, region_end + 1, out)


# ---------------------------------------------------------------- class members


class Member:
    """クラス本体の1文と、その分類・行範囲。"""

    def __init__(self, node):
        self.node = node
        self.indent = node.col_offset
        self.start = node_start(node)
        self.end = node.end_lineno
        self.name = getattr(node, "name", None)
        self.category = ATTRIBUTE
        self.subkey = 0
        self.attach_to = None  # 付随先の定義名(property setter・別名代入)または Member(属性 docstring)
        self.decorators = [decorator_name(d) for d in getattr(node, "decorator_list", [])]


def classify_members(cls):
    """クラス本体を Member の列に分類する。整形できない構成は Unsupported を送出する。"""
    body = list(cls.body)
    if body and is_docstring(body[0]):
        body = body[1:]
    def_names = {stmt.name for stmt in body if isinstance(stmt, FUNCTIONS)}
    members = []
    seen = set()
    for stmt in body:
        member = Member(stmt)
        if isinstance(stmt, FUNCTIONS):
            name = stmt.name
            decos = member.decorators
            accessor = any(d.endswith((".setter", ".deleter", ".getter")) for d in decos)
            property_like = accessor or any(d in ("property", "cached_property") or d.endswith(".cached_property")
                                            for d in decos)
            if accessor:
                if name not in seen:
                    raise Unsupported("property {} の getter が先に定義されていない".format(name))
                member.category = PROPERTY
                member.attach_to = name
            else:
                if name in seen:
                    raise Unsupported("同名メンバー {} が複数ある".format(name))
                if property_like:
                    member.category = PROPERTY
                elif name in INIT_ORDER:
                    member.category, member.subkey = INIT, INIT_ORDER[name]
                elif name.startswith("__") and name.endswith("__"):
                    member.category = SPECIAL
                elif name.startswith("_"):
                    member.category = PRIVATE
                elif "staticmethod" in decos or "classmethod" in decos:
                    member.category = CLASS_PUBLIC
                else:
                    member.category = PUBLIC
                referenced = set()
                for deco in stmt.decorator_list:
                    referenced |= names_in(deco)
                for default in stmt.args.defaults + [d for d in stmt.args.kw_defaults if d is not None]:
                    referenced |= names_in(default)
                if (referenced - {name}) & def_names:
                    raise Unsupported("{} のデコレータ・既定値がクラス内の定義を参照する".format(name))
            seen.add(name)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            value = stmt.value
            if (isinstance(value, ast.Name) and value.id in def_names and len(targets) == 1
                    and isinstance(targets[0], ast.Name)):
                member.attach_to = value.id
                member.name = targets[0].id
            elif value is not None and names_in(value) & def_names:
                raise Unsupported("クラス属性がメソッドを参照する")
            elif len(targets) == 1 and isinstance(targets[0], ast.Name):
                member.name = targets[0].id
        elif is_docstring(stmt) and members and isinstance(members[-1].node, (ast.Assign, ast.AnnAssign)):
            member.attach_to = members[-1]
        elif isinstance(stmt, ast.Pass) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
            pass
        else:
            raise Unsupported("クラス直下に {} がある".format(type(stmt).__name__))
        members.append(member)
    return members


def follower_anchors(name):
    """対になる先行メンバーの候補名と、先行メンバーの直後での順位を返す。対にならなければ None。"""
    if name in DUNDER_FOLLOWERS:
        return DUNDER_FOLLOWERS[name]
    match = re.match(r"^__([ri])(\w+)__$", name)
    if match and match.group(2) in OPERATORS:
        return (("__{}__".format(match.group(2)),), 1 if match.group(1) == "r" else 2)
    match = re.match(r"^set([A-Z].*)?$", name)
    if match:
        rest = match.group(1) or ""
        candidates = ["get" + rest, "is" + rest, "has" + rest]
        if rest:
            candidates.append(rest[0].lower() + rest[1:])
        return (tuple(candidates), 1)
    for prefix, anchor in PREFIX_PAIRS:
        match = re.match(r"^{}([A-Z].*)?$".format(prefix), name)
        if not match:
            continue
        rest = match.group(1) or ""
        candidates = [anchor + rest]
        if prefix == "disconnect" and rest:
            candidates.append(anchor)
        return (tuple(candidates), 1)
    return None


def primary_indices(members):
    return [i for i, m in enumerate(members) if m.attach_to is None]


def resolve_pairs(members):
    """直後に続けるべき先行メンバーを持つメンバーを {index: (anchor_index, rank)} で返す。"""
    index_of = {}
    for index in primary_indices(members):
        if members[index].name is not None:
            index_of.setdefault(members[index].name, index)
    pairs = {}
    for index in primary_indices(members):
        member = members[index]
        if member.name is None or member.category == ATTRIBUTE:
            continue
        found = follower_anchors(member.name)
        if found is None:
            continue
        candidates, rank = found
        for candidate in candidates:
            anchor = index_of.get(candidate)
            if anchor is not None and anchor != index and members[anchor].category == member.category:
                pairs[index] = (anchor, rank)
                break
    return pairs


def ordered_indices(members):
    """規則に沿ったメンバー順(付随メンバーを除く index の列)を返す。"""
    primary = sorted(primary_indices(members), key=lambda i: (members[i].category, members[i].subkey, i))
    pairs = resolve_pairs(members)
    followers = collections.defaultdict(list)
    for index, (anchor, rank) in pairs.items():
        followers[anchor].append((rank, index))
    emitted = set()
    result = []

    def emit(index):
        if index in emitted:
            return
        emitted.add(index)
        result.append(index)
        for _, follower in sorted(followers.get(index, ())):
            emit(follower)

    for index in primary:
        if index not in pairs:
            emit(index)
    for index in primary:
        emit(index)
    return result


def attached_indices(members):
    """付随メンバーを、付随先 index ごとにまとめる。"""
    attached = collections.defaultdict(list)
    by_name = {}
    for index in primary_indices(members):
        if members[index].name is not None:
            by_name.setdefault(members[index].name, index)
    for index, member in enumerate(members):
        if member.attach_to is None:
            continue
        target = members.index(member.attach_to) if isinstance(member.attach_to, Member) else by_name[member.attach_to]
        attached[target].append(index)
    return attached


def member_blocks(src, cls, members):
    """各メンバーの行テキスト(付随コメント込み)を返す。"""
    docstring = cls.body[0] if cls.body and is_docstring(cls.body[0]) else None
    prev_end = docstring.end_lineno if docstring is not None else src.header_end(cls)
    blocks = []
    for member in members:
        top = src.leading_comment_top(member.start, member.indent)
        trailing = []
        floating = []
        for n in range(prev_end + 1, top):
            if src.is_blank(n):
                floating.append("")
            elif src.comment_lines.get(n, 0) > member.indent and blocks:
                trailing.append(src.lines[n - 1])
            else:
                floating.append(src.lines[n - 1])
        if blocks:
            blocks[-1].extend(trailing)
        while floating and floating[0] == "":
            floating.pop(0)
        while floating and floating[-1] == "":
            floating.pop()
        blocks.append(floating + [src.lines[n - 1] for n in range(top, member.end + 1)])
        prev_end = member.end
    return blocks


def reorder_class(src, cls):
    """クラス本体を規則順に並べ替えた置換 (start, end_exclusive, lines) を返す。"""
    members = classify_members(cls)
    if not members:
        return None
    blocks = member_blocks(src, cls, members)
    attached = attached_indices(members)
    docstring = cls.body[0] if cls.body and is_docstring(cls.body[0]) else None
    start = node_start(cls)
    header_end = docstring.end_lineno if docstring is not None else src.header_end(cls)
    out = [src.lines[n - 1] for n in range(start, header_end + 1)]
    if docstring is not None:
        out.append("")
    previous = None
    for position, index in enumerate(ordered_indices(members)):
        member = members[index]
        if position:
            if previous.category == ATTRIBUTE and member.category == ATTRIBUTE:
                # 連続する属性(dataclass のフィールドなど)は元の空行数を保ち、離れていた属性は詰める。
                adjacent = members.index(previous) + 1 == index or (
                    members.index(previous) + 2 == index and members[index - 1].attach_to is previous)
                gap = range(members[index - 1].end + 1, src.leading_comment_top(member.start, member.indent))
                out.extend([""] * (src.blank_count(gap) if adjacent else 0))
            else:
                out.append("")
        out.extend(blocks[index])
        for extra in attached[index]:
            if not is_docstring(members[extra].node):
                out.append("")
            out.extend(blocks[extra])
        previous = member
    return (start, cls.end_lineno + 1, out)


# ---------------------------------------------------------------- blank lines


def adjust_blanks(src, gap, target):
    """gap(行番号の列)の空行数を target に揃えた行テキストを返す。コメント行は保持する。"""
    entries = [(src.is_blank(n), "" if src.is_blank(n) else src.lines[n - 1]) for n in gap]
    blanks = sum(1 for is_blank, _ in entries if is_blank)
    if blanks > target:
        remove = blanks - target
        kept = []
        for is_blank, text in entries:
            if is_blank and remove:
                remove -= 1
                continue
            kept.append((is_blank, text))
        entries = kept
    elif blanks < target:
        entries = [(True, "")] * (target - blanks) + entries
    return [text for _, text in entries]


def statement_lists(node):
    """compound statement の持つ文の列(body・orelse・finalbody・handlers・cases)を列挙する。"""
    for field in ("body", "orelse", "finalbody"):
        value = getattr(node, field, None)
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            yield value
    for handler in getattr(node, "handlers", None) or []:
        yield handler.body
    for case in getattr(node, "cases", None) or []:
        yield case.body


def blank_replacements(src):
    """空行規則に合わせる置換 (start, end_exclusive, lines) の一覧を返す。"""
    reps = []
    body = src.tree.body

    def gap_before(node, indent):
        return src.leading_comment_top(node_start(node), indent)

    def add(start, end, gap, target):
        if src.blank_count(gap) != target:
            reps.append((start, end, adjust_blanks(src, gap, target)))

    if body:
        top = gap_before(body[0], 0)
        add(1, top, list(range(1, top)), 0)
    for index in range(1, len(body)):
        prev, cur = body[index - 1], body[index]
        top = gap_before(cur, 0)
        gap = list(range(prev.end_lineno + 1, top))
        blanks = src.blank_count(gap)
        if index == 1 and is_docstring(prev):
            target = 2 if isinstance(cur, DEFINITIONS) else 1
        elif isinstance(prev, DEFINITIONS) or isinstance(cur, DEFINITIONS):
            target = 2
        elif is_import_like(prev) and not is_import_like(cur):
            target = clamp(blanks, 1, 2)
        else:
            target = clamp(blanks, 0, 2)
        add(prev.end_lineno + 1, top, gap, target)
    for node in ast.walk(src.tree):
        if not isinstance(node, ast.stmt):
            continue
        if isinstance(node, DEFINITIONS) and node.decorator_list:
            last = max(d.end_lineno for d in node.decorator_list)
            add(last + 1, node.lineno, list(range(last + 1, node.lineno)), 0)
        if isinstance(node, ast.ClassDef):
            members = node.body
            for index in range(1, len(members)):
                prev, cur = members[index - 1], members[index]
                top = gap_before(cur, cur.col_offset)
                gap = list(range(prev.end_lineno + 1, top))
                if (index == 1 and is_docstring(prev)) or isinstance(prev, DEFINITIONS) or isinstance(cur, DEFINITIONS):
                    target = 1
                else:
                    target = clamp(src.blank_count(gap), 0, 1)
                add(prev.end_lineno + 1, top, gap, target)
        else:
            for statements in statement_lists(node):
                for index in range(1, len(statements)):
                    prev, cur = statements[index - 1], statements[index]
                    top = gap_before(cur, cur.col_offset)
                    gap = list(range(prev.end_lineno + 1, top))
                    add(prev.end_lineno + 1, top, gap, clamp(src.blank_count(gap), 0, 1))
        nested = getattr(node, "body", None)
        if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
            top = gap_before(nested[0], nested[0].col_offset)
            line = top - 1
            while line >= 1 and src.is_blank(line):
                line -= 1
            add(line + 1, top, list(range(line + 1, top)), 0)
    return reps


def apply_replacements(lines, reps):
    """(start, end_exclusive, new_lines) を 1-based 行番号で後ろから適用する。"""
    reps = sorted(reps, key=lambda rep: (rep[0], rep[1]), reverse=True)
    last_start = None
    for start, end, new_lines in reps:
        if last_start is not None and end > last_start:
            raise RuntimeError("置換範囲が重なっている: {}-{} と {}".format(start, end, last_start))
        last_start = start
        lines[start - 1:end - 1] = list(new_lines)
    return lines


def rebuild(path, lines):
    while lines and lines[-1].strip() == "":
        lines.pop()
    return Source(path, "\n".join(lines) + "\n")


def classes_by_depth(tree):
    """ClassDef を、外側を囲む ClassDef の数(深さ)ごとにまとめた dict を返す。

    同じ深さのクラスは互いを含まないため、1回の置換でまとめて並べ替えられる。
    check_classes と同じく、関数内に定義したクラスも対象にする。
    """
    depths = collections.defaultdict(list)

    def visit(node, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                depths[depth].append(child)
                visit(child, depth + 1)
            else:
                visit(child, depth)

    visit(tree, 0)
    return depths


def fix_text(path, text):
    """整形後のテキストを返す。"""
    src = Source(path, text)
    depth = 0
    while True:
        # 外側のクラスから順に並べ替える。並べ替えで行番号が変わるため、深さごとに解析し直す。
        classes = classes_by_depth(src.tree).get(depth)
        if not classes:
            break
        reps = []
        for node in classes:
            try:
                rep = reorder_class(src, node)
            except Unsupported:
                rep = None
            if rep is not None:
                reps.append(rep)
        if reps:
            src = rebuild(path, apply_replacements(src.lines, reps))
        depth += 1
    rep = rewrite_imports(src)
    if rep is not None:
        src = rebuild(path, apply_replacements(src.lines, [rep]))
    src = rebuild(path, apply_replacements(src.lines, blank_replacements(src)))
    return "\n".join(src.lines) + "\n"


# ---------------------------------------------------------------- check


def check_imports(src, violations):
    body = src.tree.body
    region, reason = import_region(src.tree)
    if region is None:
        if reason is not None:
            first_import = next(stmt for stmt in body if isinstance(stmt, IMPORTS))
            if src.path.name == "__init__.py":
                violations.append(Violation(src.path, first_import.lineno, "L000",
                                            "import群の検査をスキップ({})".format(reason)))
            else:
                violations.append(Violation(src.path, first_import.lineno, "L001",
                                            "import群が連続していない({})".format(reason)))
        return
    first, last = region
    _, _, entries, _ = import_entries(src, first, last)
    keys = [entry[0] for entry in entries]
    for actual, wanted, entry in zip(keys, sorted(keys), entries):
        if actual != wanted:
            expected = entries[keys.index(wanted)]
            violations.append(Violation(src.path, entry[2].lineno, "L002", "import順: 「{}」を「{}」より前に置く".format(
                entry_label(expected), entry_label(entry))))
            break
    saw_type_checking = False
    prev = None
    for stmt in body[first:last + 1]:
        if is_type_checking(stmt):
            saw_type_checking = True
            continue
        if saw_type_checking:
            violations.append(Violation(src.path, stmt.lineno, "L006", "if TYPE_CHECKING: ブロックを import群の後に置く"))
            saw_type_checking = False
        if maya_import_conversion(stmt):
            violations.append(Violation(src.path, stmt.lineno, "L003", "import 形式: import maya.X as X を使う"))
        if prev is not None:
            blanks = src.blank_count(range(prev.end_lineno + 1, src.leading_comment_top(node_start(stmt), 0)))
            wanted = 0 if statement_key(prev)[0] == statement_key(stmt)[0] else 1
            if blanks != wanted:
                violations.append(Violation(src.path, stmt.lineno, "L002",
                                            "import群の空行: {}行(期待 {}行)".format(blanks, wanted)))
        prev = stmt


def check_module(src, violations):
    body = src.tree.body
    skip_all = import_region(src.tree)[0] is None and src.path.name == "__init__.py"
    first_def = next((i for i, stmt in enumerate(body) if isinstance(stmt, DEFINITIONS)), None)
    if first_def is None:
        return
    defined = set()
    index = first_def
    while index < len(body):
        stmt = body[index]
        if isinstance(stmt, DEFINITIONS):
            defined.add(stmt.name)
            index += 1
            continue
        # 連続した代入をひとまとまりとして扱い、先行定義に依存する値を含む並びは後置を許す。
        block = []
        while index < len(body) and isinstance(body[index], (ast.Assign, ast.AnnAssign)):
            block.append(body[index])
            index += 1
        if not block:
            index += 1
            continue
        if any(item.value is not None and names_in(item.value) & defined for item in block):
            continue
        for item in block:
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if any(CONSTANT_NAME.match(name) for name in names):
                violations.append(Violation(src.path, item.lineno, "L004",
                                            "定数 {} を関数・クラス定義の前に置く".format(", ".join(names))))
            elif "__all__" in names and not skip_all:
                violations.append(Violation(src.path, item.lineno, "L005", "__all__ を関数・クラス定義の前に置く"))


def check_blank_lines(src, violations):
    for start, end, new_lines in blank_replacements(src):
        blanks = src.blank_count(range(start, end))
        wanted = sum(1 for line in new_lines if line.strip() == "")
        violations.append(Violation(src.path, end, "L010", "空行 {}行(期待 {}行)".format(blanks, wanted)))
    if src.lines and src.lines[-1].strip() == "":
        violations.append(Violation(src.path, len(src.lines), "L011", "ファイル末尾の余分な空行"))


def check_classes(src, violations):
    for cls in ast.walk(src.tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        try:
            members = classify_members(cls)
        except Unsupported as error:
            violations.append(Violation(src.path, cls.lineno, "L023",
                                        "クラス {} の並び検査をスキップ({})".format(cls.name, error)))
            continue
        primary = primary_indices(members)
        highest = (-1, 0)
        highest_name = None
        out_of_order = []
        for index in primary:
            member = members[index]
            rank = (member.category, member.subkey)
            if rank < highest:
                out_of_order.append("{} ({}) を {} ({}) より前に置く".format(
                    member.name, CATEGORY_LABELS[member.category], highest_name, CATEGORY_LABELS[highest[0]]))
            elif rank > highest:
                highest, highest_name = rank, member.name
        if out_of_order:
            violations.append(Violation(src.path, cls.lineno, "L020", "クラス {}: メンバー順の違反 {}件(例: {})".format(
                cls.name, len(out_of_order), out_of_order[0])))
        groups = collections.defaultdict(list)
        for index, (anchor, _) in resolve_pairs(members).items():
            groups[anchor].append(index)
        for anchor, followers in sorted(groups.items()):
            positions = sorted(primary.index(i) for i in [anchor] + followers)
            if positions[0] != primary.index(anchor) or positions != list(range(positions[0], positions[0] + len(positions))):
                violations.append(Violation(src.path, members[anchor].start, "L021", "クラス {}: {} を {} の直後に置く".format(
                    cls.name, ", ".join(members[i].name for i in followers), members[anchor].name)))
        for index, member in enumerate(members):
            if not isinstance(member.attach_to, str):
                continue
            anchor = next(i for i in primary if members[i].name == member.attach_to)
            if any(m.attach_to != member.attach_to for m in members[anchor + 1:index]):
                violations.append(Violation(src.path, member.start, "L022", "クラス {}: {} を {} の直後に置く".format(
                    cls.name, member.name, member.attach_to)))


def check_source(src):
    violations = []
    check_imports(src, violations)
    check_module(src, violations)
    check_blank_lines(src, violations)
    check_classes(src, violations)
    violations.sort(key=lambda v: v.line)
    return violations


# ---------------------------------------------------------------- snapshot / compare


def digest(node):
    return hashlib.sha1(ast.dump(node).encode("utf-8")).hexdigest()[:16]


def import_bindings(stmt):
    """import が束縛する名前と参照先を、import 形式の違いを吸収した文字列で返す。"""
    bindings = []
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            if alias.asname:
                bindings.append("{}<-{}".format(alias.asname, alias.name))
            else:
                bindings.append("{}<-import {}".format(alias.name.split(".")[0], alias.name))
        return bindings
    module = "." * stmt.level + (stmt.module or "")
    for alias in stmt.names:
        if not stmt.level and stmt.module in MAYA_PACKAGES and alias.name in MAYA_SUBMODULES:
            bindings.append("{}<-{}.{}".format(alias.asname or alias.name, stmt.module, alias.name))
        else:
            bindings.append("{}<-{}:{}".format(alias.asname or alias.name, module, alias.name))
    return bindings


def snapshot_source(src):
    functions = collections.defaultdict(list)
    classes = {}
    imports = []
    statements = []

    def visit_class(cls, prefix):
        header = copy.copy(cls)
        header.body = [ast.Pass()]
        qualname = prefix + cls.name
        classes[qualname] = {"header": digest(header), "members": sorted(digest(stmt) for stmt in cls.body)}
        for stmt in cls.body:
            if isinstance(stmt, FUNCTIONS):
                functions[qualname + "." + stmt.name].append(digest(stmt))
            elif isinstance(stmt, ast.ClassDef):
                visit_class(stmt, qualname + ".")

    for stmt in src.tree.body:
        if isinstance(stmt, IMPORTS):
            imports.extend(import_bindings(stmt))
        elif isinstance(stmt, FUNCTIONS):
            functions[stmt.name].append(digest(stmt))
        elif isinstance(stmt, ast.ClassDef):
            visit_class(stmt, "")
        else:
            statements.append(ast.dump(stmt))
    return {
        "functions": {name: sorted(values) for name, values in functions.items()},
        "classes": classes,
        "imports": sorted(imports),
        "statements": sorted(statements),
        "comments": sorted(tok.string for tok in src.tokens if tok.type == tokenize.COMMENT),
    }


def compare_snapshots(before, after):
    """差分の説明文の一覧を返す。"""
    messages = []
    for name in sorted(set(before["functions"]) | set(after["functions"])):
        old = before["functions"].get(name)
        new = after["functions"].get(name)
        if old is None:
            messages.append("関数が追加: {}".format(name))
        elif new is None:
            messages.append("関数が削除: {}".format(name))
        elif old != new:
            messages.append("関数の内容が変化: {}".format(name))
    for name in sorted(set(before["classes"]) | set(after["classes"])):
        old = before["classes"].get(name)
        new = after["classes"].get(name)
        if old is None or new is None:
            messages.append("クラスの{}: {}".format("追加" if old is None else "削除", name))
            continue
        if old["header"] != new["header"]:
            messages.append("クラス宣言が変化: {}".format(name))
        if old["members"] != new["members"]:
            messages.append("クラス直下の文が変化: {} ({} -> {} 件)".format(name, len(old["members"]), len(new["members"])))
    for label, key in (("import束縛", "imports"), ("モジュール文", "statements"), ("コメント", "comments")):
        old = collections.Counter(before[key])
        new = collections.Counter(after[key])
        for item in sorted((old - new).elements()):
            messages.append("{}が削除: {}".format(label, item[:160]))
        for item in sorted((new - old).elements()):
            messages.append("{}が追加: {}".format(label, item[:160]))
    return messages


# ---------------------------------------------------------------- outline / main


def outline(src):
    lines = []
    for cls in ast.walk(src.tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        lines.append("class {} (L{}-{})".format(cls.name, cls.lineno, cls.end_lineno))
        try:
            members = classify_members(cls)
        except Unsupported as error:
            lines.append("  (skip: {})".format(error))
            continue
        for member in members:
            label = CATEGORY_LABELS[member.category] if member.attach_to is None else "attached"
            decos = " ".join("@" + d for d in member.decorators)
            lines.append("  L{:>5}-{:<5} {:<10} {} {}".format(
                member.start, member.end, label, member.name or type(member.node).__name__, decos).rstrip())
    return lines


def package_of(path):
    parts = relative(path).split("/")
    if parts[:2] == ["maya", "inhouse"]:
        return "/".join(parts[2:4]) if len(parts) > 4 else parts[2]
    return parts[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*",
                        help="対象のファイル・ディレクトリ(既定: hlib・hlib_bifrost・hlib_posedriverconnect)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="規則違反を一覧表示する")
    mode.add_argument("--fix", action="store_true", help="並び替えと空行の正規化を書き込む")
    mode.add_argument("--snapshot", metavar="JSON", help="構造の要約を保存する")
    mode.add_argument("--compare", metavar="JSON", help="保存した要約と比較する")
    mode.add_argument("--outline", action="store_true", help="クラスのメンバー構成を表示する")
    args = parser.parse_args(argv)
    targets = [Path(p) if Path(p).is_absolute() else ROOT / p for p in (args.paths or DEFAULT_TARGETS)]
    files = list(iter_files(targets))
    if args.check:
        violations = []
        for path in files:
            violations.extend(check_source(load(path)[0]))
        for violation in violations:
            print(violation)
        counted = [v for v in violations if v.code not in INFORMATIONAL]
        per_code = collections.Counter(v.code for v in violations)
        per_package = collections.Counter(package_of(v.path) for v in counted)
        print("files: {}  violations: {}  informational: {}".format(len(files), len(counted), len(violations) - len(counted)))
        print("by code: " + ", ".join("{}={}".format(code, count) for code, count in sorted(per_code.items())))
        print("by package: " + ", ".join("{}={}".format(name, count) for name, count in sorted(per_package.items())))
        return 1 if counted else 0
    if args.fix:
        changed = []
        for path in files:
            text, eol, bom = read_source(path)
            fixed = fix_text(path, text)
            if fixed != text:
                ast.parse(fixed, filename=str(path))
                write_source(path, fixed, eol, bom)
                changed.append(path)
        for path in changed:
            print("fixed: {}".format(relative(path)))
        print("changed {} / {} files".format(len(changed), len(files)))
        return 0
    if args.snapshot:
        data = {"files": {relative(path): snapshot_source(load(path)[0]) for path in files}}
        output = Path(args.snapshot)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print("snapshot: {} files -> {}".format(len(files), output))
        return 0
    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))["files"]
        after = {relative(path): snapshot_source(load(path)[0]) for path in files}
        prefixes = tuple(relative(t) + "/" for t in targets if t.is_dir())
        differences = 0
        for name in sorted(set(before) | set(after)):
            if name not in after:
                if name.startswith(prefixes):
                    print("{}: ファイルが無い".format(name))
                    differences += 1
                continue
            if name not in before:
                print("{}: 要約に無いファイル".format(name))
                differences += 1
                continue
            messages = compare_snapshots(before[name], after[name])
            for message in messages:
                print("{}: {}".format(name, message))
            differences += len(messages)
        print("compared {} files, {} differences".format(len(after), differences))
        return 1 if differences else 0
    for path in files:
        print("== {}".format(relative(path)))
        for line in outline(load(path)[0]):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
