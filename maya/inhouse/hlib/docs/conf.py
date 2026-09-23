"""Build hlib documentation without importing Maya or hlib."""

from pathlib import Path
import logging


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

exclude_patterns = ["_build", "_templates", ".venv", "README.md"]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = "hlib ドキュメント"


def _include_constructors(app, what, name, obj, skip, options):
    """AutoAPI が既定で隠す初期化・割り当てメソッドも掲載する。"""
    if what == "method" and obj.short_name in {"__init__", "__new__"}:
        if not obj.inherited and not obj.imported:
            return False
    return None


def setup(app):
    app.connect("autoapi-skip-member", _include_constructors)
