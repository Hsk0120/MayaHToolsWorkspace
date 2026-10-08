"""Mayaを起動せず、hlibの明示的な公開入口と追加漏れを検査する。

各パッケージの通常importと__all__を公開仕様として読む。commonだけは
遅延import用の_exportsとTYPE_CHECKING宣言を照合する。実行時の公開処理や
公開対象の別マニフェストを生成・更新するツールではない。
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys

CLASS_PACKAGES = ("nodes", "plugs", "components", "maths", "common", "json")
# 削除済みPlugへのアクセスを示す内部例外。既存の公開APIへ追加しない。
PRIVATE_CLASSES = {("plugs.plug", "DeletedAttributeError")}


@dataclass(frozen=True)
class ExportIssue:
    """公開入口の不一致箇所と修正に必要な説明を保持する。"""

    path: Path
    line: int
    code: str
    message: str

    def __str__(self):
        """CLIで表示するファイル・行番号付きの診断を返す。"""
        return "{}:{}: {} {}".format(self.path, self.line, self.code, self.message)


@dataclass(frozen=True)
class Target:
    """importが参照するモジュールと、その中の名前を保持する。"""

    module: str
    name: str | None


class Source:
    """一つのPythonファイルのトップレベル定義とimportを読む。"""

    def __init__(self, path, module, is_package):
        self.path = path
        self.module = module
        self.tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        self.context = module if is_package else module.rpartition(".")[0]
        self.definitions = {}
        self.classes = {}
        for node in self.tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.definitions[node.name] = node
                if isinstance(node, ast.ClassDef):
                    self.classes[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        self.definitions[target.id] = node

    def imports(self, statements=None):
        """トップレベルimportの公開名・参照先・行番号を列挙する。"""
        for node in self.tree.body if statements is None else statements:
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = self.context.split(".")
                    base = ".".join(parts[:len(parts) - node.level + 1])
                    module = ".".join(part for part in (base, node.module) if part)
                else:
                    module = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        yield "*", Target(module, "*"), node.lineno
                    elif node.module is None:
                        yield alias.asname or alias.name, Target(module + "." + alias.name, None), node.lineno
                    else:
                        yield alias.asname or alias.name, Target(module, alias.name), node.lineno
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name if alias.asname else alias.name.split(".")[0]
                    yield alias.asname or alias.name.split(".")[0], Target(module, None), node.lineno

    def typing_imports(self):
        """TYPE_CHECKINGブロックで宣言した参照先を列挙する。"""
        for node in self.tree.body:
            if isinstance(node, ast.If) and (
                    isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING" or
                    isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING"):
                yield from self.imports(node.body)


class ExportChecker:
    """ソースだけを参照して公開宣言と実装を照合する。"""

    def __init__(self, package_root):
        self.root = Path(package_root).resolve()
        self.package = self.root.name
        self.sources = {}
        self.entries = {}
        self.issues = []

    def issue(self, source, line, code, message):
        """診断を記録する。"""
        self.issues.append(ExportIssue(source.path, line, code, message))

    def load(self, module):
        """ローカルモジュールをASTとして読み、外部モジュールはNoneを返す。"""
        if module != self.package and not module.startswith(self.package + "."):
            return None
        if module in self.sources:
            return self.sources[module]
        relative = module[len(self.package):].lstrip(".")
        location = self.root.joinpath(*relative.split(".")) if relative else self.root
        path = location / "__init__.py" if location.is_dir() else location.with_suffix(".py")
        if not path.is_file():
            return None
        try:
            source = Source(path, module, path.name == "__init__.py")
        except (OSError, SyntaxError) as error:
            self.issues.append(ExportIssue(path, getattr(error, "lineno", 1) or 1, "E001", str(error)))
            return None
        self.sources[module] = source
        return source

    def import_map(self, source, imports):
        """重複束縛とstar importを検出して参照先の表を返す。"""
        result = {}
        for name, target, line in imports:
            if name == "*":
                self.issue(source, line, "E002", "公開入口ではstar importを使わず公開名を明示する")
            elif name in result and not name.startswith("_"):
                self.issue(source, line, "E003", "公開名 {} のimportが重複している".format(name))
            result[name] = (target, line)
        return result

    def all_names(self, source, lazy):
        """明示__all__またはcommonの_exportsから公開名を取得する。"""
        node = source.definitions.get("__all__")
        if node is None:
            self.issue(source, 1, "E004", "公開入口に__all__がない")
            return []
        if "_exports" in source.definitions and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "sorted" and len(node.value.args) == 1 and isinstance(node.value.args[0], ast.Name) and node.value.args[0].id == "_exports":
            return list(lazy)
        try:
            names = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            self.issue(source, node.lineno, "E004", "__all__は公開名のリストまたはタプルで明示する")
            return []
        if not isinstance(names, (list, tuple)) or any(not isinstance(name, str) for name in names):
            self.issue(source, node.lineno, "E004", "__all__は文字列のリストまたはタプルにする")
            return []
        if len(names) != len(set(names)):
            self.issue(source, node.lineno, "E005", "__all__の公開名が重複している")
        return names

    def check_all_mutations(self, source):
        """実行時のリスト追記で、明示した公開一覧を変更していないか確認する。"""
        for node in ast.walk(source.tree):
            changes = isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "__all__":
                changes = node.func.attr in {"append", "extend", "insert", "remove", "pop", "clear"}
            if changes:
                self.issue(source, node.lineno, "E019", "__all__への実行時の追記・削除をやめ、公開名をリストへ明示する")

    def lazy_map(self, source):
        """commonの明示的な遅延公開表を通常importと同じ形式にする。"""
        node = source.definitions.get("_exports")
        if node is None:
            return {}
        result = {}
        if not isinstance(node.value, ast.Dict):
            self.issue(source, node.lineno, "E006", "_exportsは参照先を明示した辞書にする")
            return result
        for key, value in zip(node.value.keys, node.value.values):
            try:
                name = ast.literal_eval(key)
                module, attribute = ast.literal_eval(value)
                if not isinstance(name, str) or not isinstance(module, str) or attribute is not None and not isinstance(attribute, str):
                    raise ValueError("invalid export")
            except (ValueError, TypeError):
                self.issue(source, node.lineno, "E006", "_exportsのキーと参照先を文字列で明示する")
                continue
            if name in result:
                self.issue(source, key.lineno, "E003", "遅延公開名 {} が重複している".format(name))
            result[name] = (Target(source.module + "." + module, attribute), key.lineno)
        return result

    def resolve(self, target, visited=None):
        """パッケージを経由する再公開を辿り、定義元を返す。"""
        visited = set() if visited is None else visited
        if target in visited:
            return None
        visited.add(target)
        source = self.load(target.module)
        if source is None:
            return target if not target.module.startswith(self.package + ".") else None
        if target.name is None or target.name in source.definitions:
            return target
        entry = self.entries.get(target.module)
        bindings = entry[1] if entry else {name: (ref, line) for name, ref, line in source.imports()}
        if target.name in bindings:
            return self.resolve(bindings[target.name][0], visited)
        return None

    def inspect_entry(self, module):
        """一つの公開入口の名前と参照先を照合する。"""
        source = self.load(module)
        if source is None:
            self.issues.append(ExportIssue(self.root, 1, "E001", "公開入口 {} を読み込めない".format(module)))
            return
        self.check_all_mutations(source)
        lazy = self.lazy_map(source) if module == self.package + ".common" else {}
        bindings = lazy or self.import_map(source, source.imports())
        names = self.all_names(source, lazy)
        self.entries[module] = (names, bindings)
        typing = self.import_map(source, source.typing_imports())
        if lazy:
            for name in sorted(set(names) | set(typing)):
                if name not in typing or name not in bindings or typing[name][0] != bindings[name][0]:
                    self.issue(source, typing.get(name, (None, 1))[1], "E007", "{} の遅延公開とTYPE_CHECKINGの参照先が一致しない".format(name))
            if set(names) != set(lazy):
                self.issue(source, 1, "E007", "__all__と_exportsの公開名が一致しない")
        elif typing:
            self.issue(source, 1, "E007", "通常importで公開する入口に補完用の重複宣言を残さない")
        for name in names:
            if name.startswith("_"):
                self.issue(source, 1, "E008", "非公開名 {} を__all__へ追加しない".format(name))
            if name in bindings:
                target, line = bindings[name]
                if self.resolve(target) is None:
                    self.issue(source, line, "E009", "{} の公開先 {} に対象がない".format(name, target))
            elif name not in source.definitions:
                self.issue(source, 1, "E009", "{} が__all__にあるがimportまたは定義されていない".format(name))
        for name, (target, line) in bindings.items():
            if name not in names and not name.startswith("_") and target.module.startswith(self.package + "."):
                self.issue(source, line, "E010", "importした {} が__all__から漏れている（内部用途は_別名にする）".format(name))

    def check_classes(self, folder):
        """追加クラスの公開漏れ・同名衝突・定義元の不一致を確認する。"""
        module = self.package + "." + folder
        names, bindings = self.entries.get(module, ([], {}))
        found = {}
        for path in sorted((self.root / folder).glob("*.py")):
            if path.name.startswith("_"):
                continue
            source = self.load(module + "." + path.stem)
            if source is None:
                continue
            for name, node in source.classes.items():
                if name.startswith("_") or (folder + "." + path.stem, name) in PRIVATE_CLASSES:
                    continue
                if name in found:
                    self.issue(source, node.lineno, "E011", "{} が {} と同名のクラスを定義している".format(name, found[name].module))
                expected = Target(source.module, name)
                found[name] = expected
                if name not in names:
                    self.issue(source, node.lineno, "E012", "{} を {}/__init__.pyでimportし__all__へ追加する".format(name, folder))
                elif name not in bindings or self.resolve(bindings[name][0]) != expected:
                    self.issue(source, node.lineno, "E013", "{} の公開先が定義元 {} と一致しない".format(name, source.module))

    def check_commands(self):
        """コマンドの追加漏れとrootへの再公開漏れを確認する。"""
        module = self.package + ".cmds"
        names, bindings = self.entries.get(module, ([], {}))
        root_names, root_bindings = self.entries.get(self.package, ([], {}))
        root_source = self.load(self.package)
        # root自身の関数・公開モジュールはコマンドの再公開で上書きしない。
        # 予約名もrootの明示的な公開入口から求め、別の管理一覧は持たない。
        reserved = {
            name for name in root_names
            if (root_source is not None and isinstance(root_source.definitions.get(name),
                                                       (ast.FunctionDef, ast.AsyncFunctionDef)))
            or (name in root_bindings and root_bindings[name][0].name is None)
        }
        for path in sorted((self.root / "cmds").glob("*.py")):
            if path.name.startswith("_"):
                continue
            source = self.load(module + "." + path.stem)
            if source is None:
                continue
            node = source.definitions.get(path.stem)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.issue(source, 1, "E014", "公開コマンドはファイル名と同名の関数を定義する")
                continue
            expected = Target(source.module, path.stem)
            if path.stem not in names:
                self.issue(source, node.lineno, "E015", "{} を cmds/__init__.pyでimportし__all__へ追加する".format(path.stem))
            elif path.stem not in bindings or self.resolve(bindings[path.stem][0]) != expected:
                self.issue(source, node.lineno, "E013", "{} のコマンド公開先が定義元と一致しない".format(path.stem))
            if path.stem in reserved:
                continue
            if path.stem not in root_names:
                self.issue(source, node.lineno, "E016", "{} を hlib/__init__.pyでも公開する".format(path.stem))
            elif path.stem not in root_bindings or self.resolve(root_bindings[path.stem][0]) != expected:
                self.issue(source, node.lineno, "E013", "{} のroot公開先がコマンド定義元と一致しない".format(path.stem))

    def check_wrapper_map(self, folder):
        """明示した型対応表が、実在する公開クラスを参照しているか確認する。"""
        module = self.package + "." + folder
        source = self.load(module)
        if source is None:
            return
        node = source.definitions.get("_WRAPPER_CLASSES")
        if node is None:
            return
        names, bindings = self.entries.get(module, ([], {}))
        if not isinstance(node.value, ast.Dict):
            self.issue(source, node.lineno, "E017", "_WRAPPER_CLASSESは型名とクラス名を明示した辞書にする")
            return
        seen = set()
        for key, value in zip(node.value.keys, node.value.values):
            try:
                type_name = ast.literal_eval(key)
                if not isinstance(type_name, str) or not type_name:
                    raise ValueError("invalid type")
            except (ValueError, TypeError):
                self.issue(source, node.lineno, "E017", "型対応表のキーは空でない文字列にする")
                continue
            if type_name in seen:
                self.issue(source, key.lineno, "E017", "型対応表の {} が重複している".format(type_name))
            seen.add(type_name)
            name = value.id if isinstance(value, ast.Name) else None
            target = self.resolve(bindings[name][0]) if name in bindings else Target(module, name)
            definition = self.load(target.module) if target is not None else None
            if name not in names or target is None or definition is None or not isinstance(definition.classes.get(target.name), ast.ClassDef):
                self.issue(source, value.lineno, "E018", "型 {} の対応先はimport済みの公開クラス名で指定する".format(type_name))

    def run(self):
        """全公開パッケージを読み、安定した順番の診断一覧を返す。"""
        for folder in CLASS_PACKAGES + ("cmds",):
            self.inspect_entry(self.package + "." + folder)
        self.inspect_entry(self.package)
        for folder in CLASS_PACKAGES:
            self.check_classes(folder)
        self.check_commands()
        for folder in ("nodes", "plugs"):
            self.check_wrapper_map(folder)
        return sorted(self.issues, key=lambda issue: (str(issue.path), issue.line, issue.code))


def check(package_root):
    """指定したhlibパッケージの公開仕様を検査し診断一覧を返す。"""
    return ExportChecker(package_root).run()


def main(argv=None):
    """CLI引数を読み、検査結果に応じた終了コードを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "maya" / "inhouse" / "hlib",
                        help="hlibパッケージディレクトリ（既定: ワークスペース内hlib）")
    args = parser.parse_args(argv)
    issues = check(args.package_root)
    for issue in issues:
        print(issue)
    print("hlib公開入口: {}件の不一致".format(len(issues)))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
