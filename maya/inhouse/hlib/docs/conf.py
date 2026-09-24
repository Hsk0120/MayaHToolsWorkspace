"""Build hlib documentation without importing Maya or hlib."""

from pathlib import Path
import logging

from _mermaid_classes import ancestor_class_diagram, collect_class_hierarchy, overall_class_diagram


class _DynamicExportFilter(logging.Filter):
    """Ignore only aliases populated by hlib's runtime discovery."""

    def filter(self, record):
        return record.getMessage() not in {
            "Cannot resolve import of hlib.nodes.Joints in hlib",
            "Cannot resolve import of hlib.nodes.SkinClusters in hlib",
        }


class _ReexportedSubpackageFilter(logging.Filter):
    """hlib/__init__.py がサブパッケージをトップレベル属性として再代入する箇所
    （例: ``cmds = importlib.import_module(...)``）で、AutoAPI が同じオブジェクトを
    親ページとサブパッケージページの両方に載せてしまう重複警告だけを無視する。"""

    _IGNORED_MESSAGE_PREFIXES = (
        "duplicate object description of hlib.cmds,",
    )

    def filter(self, record):
        message = record.getMessage()
        return not message.startswith(self._IGNORED_MESSAGE_PREFIXES)


logging.getLogger("sphinx.autoapi._mapper").addFilter(_DynamicExportFilter())
logging.getLogger("sphinx").addFilter(_ReexportedSubpackageFilter())

project = "hlib"
language = "ja"
extensions = ["autoapi.extension", "sphinx.ext.napoleon"]

autoapi_dirs = [str(Path(__file__).resolve().parent.parent)]
autoapi_ignore = ["*/__tests__/*", "*/docs/*"]
autoapi_options = [
    "members", "undoc-members", "private-members", "special-members",
    "show-inheritance", "show-module-summary",
]
autoapi_python_class_content = "class"
autoapi_member_order = "alphabetical"
autoapi_own_page_level = "class"
autoapi_template_dir = "_templates/autoapi"
autoapi_add_toctree_entry = False
autoapi_keep_files = False

exclude_patterns = ["_build", "_templates", ".venv", "README.md", "_generated"]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
html_static_path = ["_static"]
html_css_files = ["custom.css", "code-dark-plus.css", "mermaid.css"]
html_js_files = ["mermaid.min.js", "mermaid-init.js"]
html_title = "hlib ドキュメント"

# hlib配下のクラス継承関係をast静的解析のみで集計する(hlib・Mayaをimportしない)。
# 各クラスページの継承図(_templates/autoapi/python/class.rst)と、
# 全体クラス図(development.rst に .. include:: される _generated/full_class_diagram.rst)
# の両方がこの辞書を参照する。
_HLIB_ROOT = Path(__file__).resolve().parent.parent
_CLASS_HIERARCHY = collect_class_hierarchy(_HLIB_ROOT)


def _include_constructors(app, what, name, obj, skip, options):
    """AutoAPI が既定で隠す初期化・割り当てメソッドも掲載する。"""
    if what == "method" and obj.short_name in {"__init__", "__new__"}:
        if not obj.inherited and not obj.imported:
            return False
    return None


def _prepare_jinja_env(jinja_env):
    """クラスページのテンプレートから継承図を組み立てられるようにする。"""
    jinja_env.globals["ancestor_class_diagram"] = (
        lambda class_name: ancestor_class_diagram(class_name, _CLASS_HIERARCHY)
    )


autoapi_prepare_jinja_env = _prepare_jinja_env


def _write_generated_docs(app):
    """development.rst が .. include:: する全体クラス図の.rstフラグメントを書き出す。"""
    generated_dir = Path(__file__).resolve().parent / "_generated"
    generated_dir.mkdir(exist_ok=True)
    diagram = overall_class_diagram(_CLASS_HIERARCHY)
    content = (
        "hlib 全体クラス図\n"
        "------------------\n"
        "\n"
        f"hlib全 {len(_CLASS_HIERARCHY)} クラスの継承関係です"
        "(サブパッケージ単位でグループ化しています)。\n"
        "\n"
        ".. raw:: html\n"
        "\n"
        "   <pre class=\"mermaid\">\n"
        f"{diagram}\n"
        "   </pre>\n"
    )
    (generated_dir / "full_class_diagram.rst").write_text(content, encoding="utf-8")


def setup(app):
    app.connect("autoapi-skip-member", _include_constructors)
    app.connect("builder-inited", _write_generated_docs)
