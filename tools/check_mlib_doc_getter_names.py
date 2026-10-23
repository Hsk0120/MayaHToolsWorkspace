"""Sphinxの正式get/is定義と基礎7コマンドの掲載をMaya不要で検査する。"""

import argparse
import ast
from html.parser import HTMLParser
from pathlib import Path
import pickle
import re
import sys

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "maya/inhouse/mlib"
_COMMAND_NAMES = {"getNode", "getPlug", "createNode", "ls", "delete", "duplicate", "select"}


class _SignatureParser(HTMLParser):
    """指定したHTMLアンカーの関数署名だけを抽出する。"""

    def __init__(self, identifier):
        """署名を探す公開関数名を保持する。

        Args:
            identifier (str): 対象dt要素のHTMLアンカー。
        """
        super().__init__()
        self.identifier = identifier
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        """対象のdt要素で文字列の収集を始める。

        Args:
            tag (str): HTML要素名。
            attrs (list[tuple]): 要素のアトリビュート名と値。
        """
        if tag == "dt" and dict(attrs).get("id") == self.identifier:
            self.active = True

    def handle_endtag(self, tag):
        """署名のdt要素が終わったら収集を終える。

        Args:
            tag (str): 終了するHTML要素名。
        """
        if tag == "dt":
            self.active = False

    def handle_data(self, data):
        """署名の引数・区切り・既定値を表示順で集める。

        Args:
            data (str): HTML要素内のテキスト。
        """
        if self.active:
            self.parts.append(data)

def _signature_parameters(html, identifier):
    """関数名を除く署名を返し、未掲載のアンカーはNoneで示す。

    Args:
        html (str): 生成されたHTML。
        identifier (str): 対象の公開関数名。

    Returns:
        str | None: 引数表示の文字列。署名がない場合はNone。
    """
    parser = _SignatureParser(identifier)
    parser.feed(html)
    signature = "".join(parser.parts)
    _, opening, parameters = signature.partition("(")
    return " ".join(parameters.split()) if opening else None


def _canonical_definitions(package_root):
    """実装の公開get/is定義と、正式判定に重複する省略名を列挙する。"""
    package_root = Path(package_root)
    definitions, forbidden = set(), set()
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root)
        if any(part in {"__tests__", "_docs", "cmds"} for part in relative.parts):
            continue
        if path.stem.startswith("_"):
            continue
        module = ".".join(("mlib", *relative.with_suffix("").parts))
        for statement in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if isinstance(statement, ast.ClassDef):
                if statement.name.startswith("_"):
                    continue
                owner, members = module + "." + statement.name, statement.body
            else:
                owner, members = module, [statement]
            methods = {member.name: member for member in members
                       if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for name in methods:
                if not re.fullmatch(r"(?:get|is)[A-Z]\w*", name):
                    continue
                definitions.add(owner + "." + name)
                if not name.startswith("is"):
                    continue
                short = name[2].lower() + name[3:]
                other = methods.get(short)
                # Plugin.loaded等、同名の独立APIは終了した判定別名と区別する。
                if other is not None:
                    body = other.body[1:] if ast.get_docstring(other) else other.body
                    if not (len(body) == 1 and isinstance(body[0], ast.Return)
                            and isinstance(body[0].value, ast.Call)
                            and ((isinstance(body[0].value.func, ast.Attribute)
                                  and body[0].value.func.attr == name)
                                 or (isinstance(body[0].value.func, ast.Name)
                                     and body[0].value.func.id == name))):
                        continue
                forbidden.add(owner + "." + short)
    return definitions, forbidden


def check(build_dir, package_root=_PACKAGE_ROOT):
    """実ASTの正式名をAutoAPI・参照登録・HTMLと照合する。"""
    build_dir = Path(build_dir)
    with (build_dir / ".doctrees/environment.pickle").open("rb") as stream:
        environment = pickle.load(stream)
    objects = environment.autoapi_all_objects
    references = environment.domaindata["py"]["objects"]
    definitions, forbidden = _canonical_definitions(package_root)
    errors, html_cache = [], {}

    def html_for(entry):
        """同じ生成ページは一度だけ読み込む。"""
        path = build_dir / (entry.docname + ".html")
        if path not in html_cache:
            html_cache[path] = path.read_text(encoding="utf-8")
        return html_cache[path]

    for identifier in sorted(definitions):
        obj, entry = objects.get(identifier), references.get(identifier)
        if obj is None or not obj.display:
            errors.append("正式get/is定義がAutoAPIへ掲載されていません: " + identifier)
        if entry is None:
            errors.append("正式get/is名の公開参照がありません: " + identifier)
        elif f'id="{entry.node_id}"' not in html_for(entry):
            errors.append("正式get/is名のHTMLアンカーがありません: " + identifier)
    for identifier in sorted(forbidden):
        if identifier in objects or identifier in references:
            errors.append("終了した判定省略入口が掲載されています: " + identifier)
    for name in sorted(_COMMAND_NAMES):
        root_id, cmds_id = "mlib." + name, "mlib.cmds." + name
        root_entry, cmds_entry = references.get(root_id), references.get(cmds_id)
        if root_entry is None or cmds_entry is None:
            errors.append("基礎コマンドの公開参照がありません: " + name)
            continue
        if root_entry.docname != cmds_entry.docname:
            errors.append("cmdsとルートの説明ページが分かれています: " + name)
        root_signature = _signature_parameters(html_for(root_entry), root_id)
        cmds_signature = _signature_parameters(html_for(cmds_entry), cmds_id)
        if root_signature is None or cmds_signature is None or root_signature != cmds_signature:
            errors.append("cmdsとルートの構文・引数表示が異なります: " + name)
    if "mlib" in sys.modules or "maya" in sys.modules:
        errors.append("検査中にmlibまたはMayaがimportされました。")
    return errors


def main():
    """指定されたHTMLを検査し、不一致を終了コードへ反映する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    arguments = parser.parse_args()
    errors = check(arguments.build_dir)
    for error in errors:
        print(error)
    print(f"正式get/is APIの文書検査: {len(errors)} 件の不一致")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
