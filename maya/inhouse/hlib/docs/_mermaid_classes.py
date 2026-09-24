"""hlibのクラス継承関係をast静的解析だけで集計し、Mermaid classDiagramを組み立てる。

development.rst の「ビルド時に hlib・Maya を import せず」方針に従い、
``ast`` モジュールでのソース解析のみを行い、対象モジュールを一切importしない。
"""

import ast
from pathlib import Path

_IGNORE_DIR_NAMES = {"__tests__", "docs", "__pycache__", ".venv"}


def _module_qualname(path, hlib_root):
    """hlib配下の .py ファイルパスから ``hlib.x.y`` 形式の完全修飾モジュール名を作る。

    Args:
        path (Path): 対象ファイルの絶対パス。
        hlib_root (Path): ``hlib`` パッケージディレクトリの絶対パス。

    Returns:
        str: ドット区切りのモジュール完全修飾名。``__init__.py`` はパッケージ名に畳む。
    """
    relative = path.relative_to(hlib_root.parent)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_class_hierarchy(hlib_root):
    """hlib配下の全クラス定義を静的解析し、短いクラス名をキーにした継承情報を返す。

    Args:
        hlib_root (Path): ``hlib`` パッケージディレクトリの絶対パス。

    Returns:
        dict[str, dict]: ``{短いクラス名: {"bases": [基底クラス名...], "qualname": 完全修飾名}}``。
            同名クラスが複数モジュールにある場合は後勝ちで上書きする。
    """
    classes = {}
    for path in sorted(hlib_root.rglob("*.py")):
        relative_parts = set(path.relative_to(hlib_root).parts)
        if relative_parts & _IGNORE_DIR_NAMES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        module_qualname = _module_qualname(path, hlib_root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    continue
            classes[node.name] = {
                "bases": bases,
                "qualname": f"{module_qualname}.{node.name}",
            }
    return classes


def ancestor_class_diagram(class_name, hierarchy, indent=6):
    """祖先チェーンと直接の派生クラスを含むMermaid図を返す。

    hierarchy に無い基底クラス(組み込み型・外部クラス)は終端ノードとして扱う
    (それ以上は展開しない)。

    Args:
        class_name (str): 起点となる短いクラス名。
        hierarchy (dict): collect_class_hierarchy() が返す辞書。
        indent (int): 各行に付与する半角スペース数。

    Returns:
        str | None: Mermaid classDiagramのソース(字下げ済み)。
            class_name が hierarchy に無ければ None。
    """
    if class_name not in hierarchy:
        return None

    body = ["classDiagram"]
    visited_nodes = set()
    visited_edges = set()

    def walk(name):
        if name in visited_nodes:
            return
        visited_nodes.add(name)
        info = hierarchy.get(name)
        if info is None:
            return
        for base in info["bases"]:
            base_short = base.rsplit(".", 1)[-1]
            edge = (base_short, name)
            if edge not in visited_edges:
                visited_edges.add(edge)
                body.append(f"    {base_short} <|-- {name}")
            walk(base_short)

    walk(class_name)
    # 基底クラスのページでも、次に参照する具象クラスを把握できるようにする。
    # 孫以降は各派生クラスのページで表示し、全体図の巨大化を避ける。
    for name, info in sorted(hierarchy.items()):
        if any(base.rsplit(".", 1)[-1] == class_name for base in info["bases"]):
            edge = (class_name, name)
            if edge not in visited_edges:
                visited_edges.add(edge)
                body.append(f"    {class_name} <|-- {name}")
    if len(body) == 1:
        body.append(f"    class {class_name}")

    prefix = " " * indent
    return "\n".join(prefix + line for line in body)


def overall_class_diagram(hierarchy, indent=6):
    """hlib全クラスの継承関係を、サブパッケージ単位のnamespaceでまとめたMermaid図を返す。

    Args:
        hierarchy (dict): collect_class_hierarchy() が返す辞書。
        indent (int): 各行に付与する半角スペース数。

    Returns:
        str: Mermaid classDiagramのソース(字下げ済み)。
    """
    groups = {}
    for name, info in hierarchy.items():
        parts = info["qualname"].split(".")
        group = parts[1] if len(parts) > 2 else "(root)"
        groups.setdefault(group, []).append(name)

    body = ["classDiagram"]
    for group in sorted(groups):
        body.append(f"    namespace {group} {{")
        for name in sorted(groups[group]):
            body.append(f"        class {name}")
        body.append("    }")

    edges = set()
    for name, info in hierarchy.items():
        for base in info["bases"]:
            base_short = base.rsplit(".", 1)[-1]
            edges.add((base_short, name))
    for base_short, name in sorted(edges):
        body.append(f"    {base_short} <|-- {name}")

    prefix = " " * indent
    return "\n".join(prefix + line for line in body)
