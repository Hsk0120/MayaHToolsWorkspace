"""Build Hlib documentation without importing Maya or Hlib."""

from pathlib import Path
import logging


class _DynamicExportFilter(logging.Filter):
    """Ignore only aliases populated by Hlib's runtime discovery."""

    def filter(self, record):
        return record.getMessage() not in {
            "Cannot resolve import of Hlib.nodes.Joints in Hlib",
            "Cannot resolve import of Hlib.nodes.SkinClusters in Hlib",
        }


logging.getLogger("sphinx.autoapi._mapper").addFilter(_DynamicExportFilter())

project = "Hlib"
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
html_theme = "pydata_sphinx_theme"
html_title = "Hlib ドキュメント"


def _include_constructors(app, what, name, obj, skip, options):
    """AutoAPI が既定で隠す初期化・割り当てメソッドも掲載する。"""
    if what == "method" and obj.short_name in {"__init__", "__new__"}:
        if not obj.inherited and not obj.imported:
            return False
    return None


def setup(app):
    app.connect("autoapi-skip-member", _include_constructors)
