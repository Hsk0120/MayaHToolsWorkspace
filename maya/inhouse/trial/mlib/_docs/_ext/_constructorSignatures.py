"""Mayaをimportせず、単数Nodeの継承したconstructor署名を表示する。"""

import ast
from pathlib import Path


def _conditional_bases(package_name, package_root):
    """条件式を評価せず、条件付き基底の両枝をimport完全名へ解決する。"""
    result = {}
    if package_root is None:
        return result
    root = Path(package_root)
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in {"_docs", "__tests__"} for part in relative.parts):
            continue
        parts = relative.with_suffix("").parts
        is_package = parts[-1] == "__init__"
        if is_package:
            parts = parts[:-1]
        module_parts = (package_name, *parts)
        module = ".".join(module_parts)
        import_scope = module_parts if is_package else module_parts[:-1]
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        imports = {}
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom):
                if statement.level:
                    prefix = import_scope[:len(import_scope) - statement.level + 1]
                    imported_module = ".".join((*prefix, statement.module or ""))
                else:
                    imported_module = statement.module or ""
                imported_module = imported_module.rstrip(".")
                for entry in statement.names:
                    if entry.name != "*":
                        imports[entry.asname or entry.name] = imported_module + "." + entry.name
            elif isinstance(statement, ast.Import):
                for entry in statement.names:
                    local = entry.asname or entry.name.split(".")[0]
                    imports[local] = entry.name if entry.asname else local

        def resolve(expression):
            """名前・名前に続く属性だけを解決し、呼出し等を基底と推測しない。"""
            if isinstance(expression, ast.Name):
                return imports.get(expression.id, module + "." + expression.id)
            if isinstance(expression, ast.Attribute):
                owner = resolve(expression.value)
                return owner + "." + expression.attr if owner else None
            return None

        for statement in tree.body:
            if not (isinstance(statement, ast.Assign)
                    and isinstance(statement.value, ast.IfExp)):
                continue
            candidates = (resolve(statement.value.body), resolve(statement.value.orelse))
            if not all(candidates):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    result[module + "." + target.id] = candidates
    return result


class ConstructorDocumentation:
    """AutoAPIの表示時だけ基底署名を参照し、解析オブジェクトは変更しない。"""

    def __init__(self, package_name, package_root=None):
        """対象パッケージの単数Node基底を指定する。

        Args:
            package_name (str): 文書化するパッケージ名。
            package_root (Path | None): 条件付き基底を静的に調べる製品ソース。
        """
        self.node_id = package_name + ".nodes.node.Node"
        self.conditional_bases = _conditional_bases(package_name, package_root)

    def signature(self, obj) -> str:
        """自身の署名か、単一継承でNodeへ到達する最近接基底の署名を返す。

        Args:
            obj: ビルド中のAutoAPIクラスオブジェクト。

        Returns:
            str: 表示する引数。別系統・未知・循環・多重継承では空文字列。
                自身に署名がある場合は、系統によらず元の表示を維持する。
        """
        own_args = getattr(obj, "args", None) or ""
        constructor = getattr(obj, "constructor", None)
        if own_args or (constructor is not None
                        and not getattr(constructor, "inherited", False)):
            return own_args

        app = getattr(obj, "app", None)
        environment = getattr(app, "env", None)
        objects = getattr(environment, "autoapi_all_objects", None)
        if objects is None:
            return ""

        return self._node_signature(obj, objects, frozenset(), None) or ""

    def _node_signature(self, obj, objects, visited, nearest_args):
        """クラスの単一継承を追い、Node未到達の場合はNoneを返す。"""
        identifier = getattr(obj, "id", None)
        if not identifier or identifier in visited:
            return None
        visited = visited | {identifier}
        if nearest_args is None:
            args = getattr(obj, "args", None) or ""
            constructor = getattr(obj, "constructor", None)
            # 引数なしの独自constructorも、さらに上の署名で置き換えない。
            if args or (constructor is not None
                        and not getattr(constructor, "inherited", False)):
                nearest_args = args
        if identifier == self.node_id:
            return nearest_args or ""
        bases = getattr(obj, "bases", ()) or ()
        if len(bases) != 1 or not isinstance(bases[0], str):
            return None
        base = bases[0]
        if "." not in base:
            base = identifier.rsplit(".", 1)[0] + "." + base
        return self._base_signature(base, objects, visited, nearest_args)

    def _base_signature(self, identifier, objects, visited, nearest_args):
        """条件付き基底は両枝のNode系統と表示署名の一致を必要とする。"""
        candidates = self.conditional_bases.get(identifier)
        if candidates:
            if identifier in visited:
                return None
            visited = visited | {identifier}
            signatures = [self._base_signature(candidate, objects, visited, nearest_args)
                          for candidate in candidates]
            if signatures[0] is not None and signatures[0] == signatures[1]:
                return signatures[0]
            return None
        obj = objects.get(identifier)
        if obj is None:
            return None
        return self._node_signature(obj, objects, visited, nearest_args)
