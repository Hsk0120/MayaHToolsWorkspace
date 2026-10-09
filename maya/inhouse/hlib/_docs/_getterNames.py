"""Mayaをimportせず、明示されたget/is省略入口を文書の主表記へ合わせる。"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

_COMPONENT_SHORT_NAMES = {"getUV": "uv", "getUVs": "uvs", "getCV": "cv", "getCVs": "cvs"}


@dataclass(frozen=True)
class GetterAlias:
    """製品ソースで確認した取得・判定メソッドと省略入口の対応を保持する。"""

    alias: str
    getter: str
    parameters: frozenset[str]


def collect_getter_aliases(package_root):
    """実際の_getter_alias/_is_alias宣言だけから省略入口の対応を集める。

    Args:
        package_root (Path): hlibパッケージの配置。

    Returns:
        dict[str, GetterAlias]: 省略入口の完全名をキーにした対応表。
    """
    package_root = Path(package_root)
    functions = {}
    pending = []
    for path in sorted(package_root.rglob("*.py")):
        if any(part in {"_docs", "__tests__"} for part in path.relative_to(package_root).parts):
            continue
        parts = path.relative_to(package_root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = ".".join((package_root.name, *parts))
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        imports = {}
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom):
                prefix = module.split(".")
                if path.name != "__init__.py":
                    prefix.pop()
                if statement.level:
                    prefix = prefix[:len(prefix) - statement.level + 1]
                    imported_module = ".".join((*prefix, statement.module or ""))
                else:
                    imported_module = statement.module or ""
                for name in statement.names:
                    imports[name.asname or name.name] = imported_module + "." + name.name
        for statement in tree.body:
            scope = module + "." + statement.name if isinstance(statement, ast.ClassDef) else module
            members = statement.body if isinstance(statement, ast.ClassDef) else [statement]
            for member in members:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                identifier = scope + "." + member.name
                functions[identifier] = member
                for decorator in member.decorator_list:
                    if not (isinstance(decorator, ast.Call)
                            and isinstance(decorator.func, ast.Name)
                            and decorator.func.id in {"_getter_alias", "_is_alias"}
                            and decorator.args
                            and isinstance(decorator.args[0], ast.Name)):
                        continue
                    getter_name = decorator.args[0].id
                    getter = imports.get(getter_name, scope + "." + getter_name)
                    prefix = "is" if decorator.func.id == "_is_alias" else "get"
                    pending.append((identifier, getter, prefix))
    aliases = {}
    for alias, getter, prefix in pending:
        name = getter.rsplit(".", 1)[-1]
        offset = len(prefix)
        short = (_COMPONENT_SHORT_NAMES.get(name) if prefix == "get" else None)
        short = short or name[offset:offset + 1].lower() + name[offset + 1:]
        if not re.fullmatch(prefix + r"[A-Z]\w*", name) or alias.rsplit(".", 1)[-1] != short:
            raise ValueError(f"{prefix}省略入口の対応が不正です: {alias} -> {getter}")
        if getter not in functions:
            raise ValueError(f"{prefix}省略入口の正式メソッドが見つかりません: {getter}")
        args = functions[getter].args
        parameters = frozenset(arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs))
        aliases[alias] = GetterAlias(alias, getter, parameters)
    return aliases


class GetterDocumentation:
    """AutoAPIの表示情報だけを整え、製品の定義・公開名は変更しない。"""

    def __init__(self, package_root):
        """製品ソースから実在する省略入口を確認する。

        Args:
            package_root (Path): hlibパッケージの配置。
        """
        self.package_name = Path(package_root).name
        self.aliases = collect_getter_aliases(package_root)
        self.pairs_by_getter = {entry.getter: entry for entry in self.aliases.values()}
        self.getters = {entry.getter: entry.alias for entry in self.aliases.values()}
        names = "|".join(re.escape(name) for name in sorted(self.getters, key=len, reverse=True))
        self.qualified_pattern = re.compile(r"(?<![A-Za-z0-9_.])(?:" + names + r")(?![A-Za-z0-9_])")
        self.short_names = {
            entry.getter.rsplit(".", 1)[-1]: entry.alias.rsplit(".", 1)[-1]
            for entry in self.aliases.values()
        }
        predicate_definitions = _predicate_definitions(package_root)
        self.ambiguous_predicate_owners = {
            name: owners for name, owners in predicate_definitions.items()
            if name in self.short_names
            and any(owner + "." + name not in self.getters for owner in owners)
        }
        self.short_receivers = set(self.short_names.values()) | {
            entry.alias.rsplit(".", 2)[-2] for entry in self.aliases.values()
            if entry.alias.rsplit(".", 2)[-2][:1].isupper()
        }
        self.math_equivalent_owners = {
            entry.getter.rsplit(".", 1)[0] for entry in self.aliases.values()
            if entry.getter.startswith(self.package_name + ".maths.")
            and entry.getter.endswith(".isEquivalent")
        }
        self.math_equivalent_classes = {
            identifier.rsplit(".", 1)[-1] for identifier in self.math_equivalent_owners
        }
        self.command_modules = {
            entry.getter.rsplit(".", 1)[0]: entry.alias.rsplit(".", 1)[0]
            for entry in self.aliases.values()
            if entry.alias.startswith(self.package_name + ".cmds.")
        }

    def skip_member(self, app, what, name, obj, skip, options):
        """正式取得・判定メソッドの重複掲載を省き、省略名へ本文を集約する。

        Args:
            app: Sphinxアプリケーション。
            what (str): AutoAPIの種類。
            name (str): 完全名。
            obj: AutoAPIオブジェクト。
            skip (bool): AutoAPIの既定除外判断。
            options: AutoAPIオプション。

        Returns:
            bool | None: 省略入口を持つ正式名ならTrue、それ以外は既定の判断を維持する。
        """
        if what in {"class", "exception", "module", "package"}:
            self._bind_parent(obj)
        if what in {"function", "method"}:
            if getattr(obj, "hlib_short_id", None) or self._source_id(obj) in self.getters:
                return True
        return None

    def rewrite_docstring(self, text, parameters=(), *, owner=""):
        """実在する取得・判定メソッドの参照を短名へ揃え、標準名を保つ。

        Args:
            text (str): AutoAPIが解析した説明文。
            parameters (Iterable[str]): 改名してはならない引数名。
            owner (str): 説明の定義元。Plug内のbare/self参照の判別に使う。

        Returns:
            str: 省略名を用いる説明文。
        """
        # Python名の境界はASCIIで判定し、「getPlugへ」「isValidなら」も扱う。
        # 定義元の完全名では、getコマンドのモジュール名も同時に省略する。
        def replace_qualified(match):
            if (match.start() and text[match.start() - 1] in "\"'"
                    and match.end() < len(text) and text[match.end()] in "\"'"):
                return match.group(0)
            return self.getters[match.group(0)]

        text = self.qualified_pattern.sub(replace_qualified, text)
        pattern = r"(?<![A-Za-z0-9_.])(?P<prefix>(?:[A-Za-z_][A-Za-z0-9_]*\.)*|\.)(?P<name>(?:get|is)[A-Z][A-Za-z0-9_]*)(?![A-Za-z0-9_])"

        def replace(match):
            prefix, name = match.group("prefix", "name")
            if name not in self.short_names:
                return match.group(0)
            if prefix == ".":
                # foo.getNode().getName()の後半は、直前のhlib取得/型生成から判別する。
                # OpenMayaの生成式().getWeights()等を同名hlibメソッドと混同しない。
                before = text[:match.start()].rstrip()
                if not before.endswith(")"):
                    return match.group(0)
                depth = 0
                opening = None
                for index in range(len(before) - 1, -1, -1):
                    if before[index] == ")":
                        depth += 1
                    elif before[index] == "(":
                        depth -= 1
                        if depth == 0:
                            opening = index
                            break
                callee = re.search(r"([A-Za-z_][A-Za-z0-9_.]*)\s*$", before[:opening]) if opening is not None else None
                if not (callee and callee[1].rsplit(".", 1)[-1] in self.short_receivers):
                    return match.group(0)
            parts = prefix.rstrip(".").split(".") if prefix else []
            is_hlib = bool(parts and parts[0] in {self.package_name, "hlib"})
            # getElementはPlugにも存在するが、数学値の同名APIはOpenMaya標準名。
            # レシーバーが明確にPlugを表す参照だけを省略名へ変換する。
            if name == "getElement":
                receiver = parts[-1] if parts else ""
                plug_reference = (
                    receiver in {"Plug", "ArrayPlug", "CompoundPlug", "plug", "array"}
                    or receiver.endswith("_plug")
                    or (owner.startswith(self.package_name + ".plugs.")
                        and receiver in {"", "self", "cls"})
                )
                if not plug_reference:
                    return match.group(0)
            if not is_hlib and any(
                part in {"cmds", "maya", "om", "om2", "OpenMaya", "OpenMayaAnim", "pm", "pymel", "cymel"}
                or re.match(r"M[A-Z]", part) for part in parts
            ):
                return match.group(0)
            if name in self.ambiguous_predicate_owners:
                # 同名判定の省略入口が別クラスにあっても、衝突して元名を残すクラスへ
                # 適用しない。曖昧な変数名や文脈のないbare参照は元の判定名を維持する。
                receiver = parts[-1] if parts else ""
                owners = self.ambiguous_predicate_owners[name]
                if receiver in {"", "self", "cls"}:
                    candidates = {
                        identifier for identifier in owners
                        if owner == identifier or owner.startswith(identifier + ".")
                    }
                else:
                    receiver_class = {
                        "plugin": "Plugin", "reference": "Reference", "scene": "Scene",
                        "layout": "WorkspaceLayout", "workspace_layout": "WorkspaceLayout",
                        "workspaceLayout": "WorkspaceLayout",
                    }.get(receiver, receiver)
                    candidates = {
                        identifier for identifier in owners
                        if identifier.rsplit(".", 1)[-1] == receiver_class
                    }
                if not candidates or any(identifier + "." + name not in self.getters
                                         for identifier in candidates):
                    return match.group(0)
            if name == "isEquivalent":
                # hlib自身のdefに対応する参照だけを変える。native変数の同名呼出しや
                # hlibで再定義していないQuaternionの標準APIには手を加えない。
                receiver = parts[-1] if parts else ""
                qualified_owner = prefix.rstrip(".")
                owner_matches = any(
                    owner == identifier or owner.startswith(identifier + ".")
                    for identifier in self.math_equivalent_owners
                )
                hlib_reference = (
                    qualified_owner in self.math_equivalent_owners
                    or (is_hlib and receiver in self.math_equivalent_classes)
                    or (len(parts) == 1 and receiver in self.math_equivalent_classes)
                    or (receiver in {"", "self", "cls"} and owner_matches)
                )
                if not hlib_reference:
                    return match.group(0)
            if not prefix and (name in parameters or re.match(r"\s*=", text[match.end():])):
                return match.group(0)
            if (match.start() and text[match.start() - 1] in "\"'"
                    and match.end() < len(text) and text[match.end()] in "\"'"):
                return match.group(0)
            return prefix + self.short_names[name]

        # 先頭のget取得を変えた後、その戻り値に続く取得・判定名も判別できる。
        while True:
            updated = re.sub(pattern, replace, text)
            if updated == text:
                break
            text = updated
        return text

    def prepare_object(self, obj):
        """テンプレート描画前に短名へ署名・戻り型・説明を移す。

        Args:
            obj: 描画するAutoAPIオブジェクト。

        Returns:
            str: Jinjaの呼出し箇所へ出力を加えない空文字列。
        """
        self._bind_parent(obj)
        all_objects = obj.app.env.autoapi_all_objects
        for child in obj.children:
            getter_id = getattr(child, "hlib_getter_source", None)
            if getter_id:
                original = all_objects.get(getter_id)
                if original is None:
                    raise RuntimeError(f"AutoAPIの正式メソッドが見つかりません: {getter_id}")
                child.args = original.args
                child.overloads = list(original.overloads)
                child.return_annotation = original.return_annotation
                child.type_params = original.type_params
                pair = self.pairs_by_getter[getter_id]
                child.docstring = self.rewrite_docstring(original.docstring, pair.parameters, owner=getter_id)
            else:
                parameters = {arg[1] for arg in child.obj.get("args", ()) if arg[1]}
                child.docstring = self.rewrite_docstring(child.docstring, parameters, owner=self._source_id(child))
        obj.docstring = self.rewrite_docstring(obj.docstring, owner=self._source_id(obj))
        module_alias = self._source_id(obj) + "." + obj.short_name
        pair = self.aliases.get(module_alias)
        if pair and pair.getter.startswith(self.package_name + ".cmds."):
            # cmdsの再公開関数は元モジュールと同じ完全名を持つため、
            # all_objectsでは関数が優先される。Synopsisはモジュール表から取得する。
            original_module = obj.app.env.autoapi_objects[pair.getter.rsplit(".", 1)[0]]
            obj.docstring = self.rewrite_docstring(original_module.docstring, owner=original_module.id)
        return ""

    def preferred_command(self, obj):
        """コマンド一覧から、本文を省略入口へ移したgetモジュールを除く。"""
        return obj.id not in self.command_modules

    def short_command(self, obj):
        """正式getコマンドの主説明がある省略入口を返す。"""
        module = self.command_modules.get(obj.id)
        return module.rsplit(".", 1)[-1] if module else None

    def register_reference_aliases(self, app, env):
        """既存の正式get/is名の参照を、短名の説明へ引き続き解決する。

        Args:
            app: Sphinxアプリケーション。
            env: 読み込みを終えたSphinx環境。
        """
        domain = env.get_domain("py")
        for obj in env.autoapi_all_objects.values():
            getter = getattr(obj, "hlib_getter_id", None)
            if getter and obj.id in domain.objects:
                domain.objects[getter] = domain.objects[obj.id]._replace(aliased=True)
        for getter_module, alias_module in self.command_modules.items():
            short = alias_module.rsplit(".", 1)[-1]
            getter = getter_module.rsplit(".", 1)[-1]
            public_short = self.package_name + "." + short
            if public_short in domain.objects:
                entry = domain.objects[public_short]._replace(aliased=True)
                domain.objects[self.package_name + "." + getter] = entry
                domain.objects[getter_module + "." + getter] = entry
                domain.objects[alias_module + "." + short] = entry
            public_cmds_short = self.package_name + ".cmds." + short
            if public_cmds_short in domain.objects:
                # cmdsとルートは同じ関数だが、構文には双方の公開名を記載する。
                # cmds.getXの旧参照はcmds.xの説明へ解決する。
                entry = domain.objects[public_cmds_short]._replace(aliased=True)
                domain.objects[self.package_name + ".cmds." + getter] = entry

    def _source_id(self, obj):
        """再公開されたオブジェクトは定義元の名前で照合する。"""
        return obj.obj.get("original_path", obj.id)

    def _bind_parent(self, parent):
        """同じクラス/モジュール内の正式名と省略名を表示用に関連付ける。"""
        children = {child.short_name: child for child in parent.children}
        source = self._source_id(parent)
        for child in parent.children:
            identifier = child.obj.get("original_path", source + "." + child.short_name)
            pair = self.aliases.get(identifier)
            if pair is None:
                continue
            getter_name = pair.getter.rsplit(".", 1)[-1]
            child.hlib_getter_source = pair.getter
            child.hlib_getter_id = parent.id + "." + getter_name
            if getter_name in children:
                children[getter_name].hlib_short_id = child.id


def _predicate_definitions(package_root):
    """省略入口を持たない同名判定も、定義クラス・モジュールごとに列挙する。

    Args:
        package_root (Path): hlibパッケージの配置。

    Returns:
        dict[str, set[str]]: 判定名をキー、定義元の完全名を値にした対応。
    """
    package_root = Path(package_root)
    definitions = {}
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root)
        if any(part in {"_docs", "__tests__"} for part in relative.parts):
            continue
        parts = relative.with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = ".".join((package_root.name, *parts))
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for statement in tree.body:
            owner = module + "." + statement.name if isinstance(statement, ast.ClassDef) else module
            members = statement.body if isinstance(statement, ast.ClassDef) else [statement]
            for member in members:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.fullmatch(r"is[A-Z]\w*", member.name):
                    definitions.setdefault(member.name, set()).add(owner)
    return definitions
