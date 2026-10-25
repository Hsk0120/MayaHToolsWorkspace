"""mlibのSphinx設定。本文の編集方法とビルド手順は../README.mdを参照。"""

from pathlib import Path
import sys

# 1. 文書の場所と基本情報
# __file__を基準にするため、どのフォルダからビルドしても同じ設定になる。
_SOURCE_DIR = Path(__file__).resolve().parent
_DOCS_DIR = _SOURCE_DIR.parent
_MLIB_ROOT = _DOCS_DIR.parent
_PACKAGE_NAME = _MLIB_ROOT.name

# 継承図などの独自処理は_extにまとめ、通常の設定と分けている。
sys.path.insert(0, str(_DOCS_DIR / "_ext"))
from mlibDocs import prepare_autoapi

project = _PACKAGE_NAME
copyright = "2026 Hsk0120"
language = "ja"

# 2. APIページの自動生成
# AutoAPIはPythonソースを静的解析する。Mayaもmlibもimportしない。
extensions = ["autoapi.extension", "sphinx.ext.napoleon", "mlibDocs"]
autoapi_dirs = [str(_MLIB_ROOT)]
autoapi_ignore = ["*/__tests__/*", "*/_docs/*"]
autoapi_options = [
    "members", "undoc-members", "private-members", "special-members",
    "show-inheritance", "show-module-summary",
]
autoapi_python_class_content = "class"
autoapi_member_order = "alphabetical"
autoapi_own_page_level = "class"  # メソッドは所属クラスのページ内へ掲載する。
autoapi_template_dir = "_templates/autoapi"
autoapi_prepare_jinja_env = prepare_autoapi
autoapi_add_toctree_entry = False  # API目次の入口はmodules.rstで指定する。
autoapi_keep_files = False  # 生成したRSTは編集せず、元のdocstringを直す。

# 3. HTMLの見た目
html_theme = "sphinxdoc"
html_title = f"{_PACKAGE_NAME} ドキュメント"
pygments_style = "one-dark"
templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["css/theme.css", "css/layout.css", "css/code-dark-plus.css", "css/mermaid.css"]

# 4. 継承図の描画
# Mermaid本体はCDNから読み込む。版を変えるときはSRIも更新する。
# URLとSRIはmaya/inhouse/mlib/__tests__/checks/check_mlib_docs.pyもここから読み、生成HTMLと照合する。
_MERMAID_VERSION = "11.17.2"
_MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{_MERMAID_VERSION}/dist/mermaid.min.js"
_MERMAID_SRI = "sha384-EOXBFmc3gx5mb+vn0vPvvGqACToJD24hhacX5Yx+8NUUQrHIle/Qi5Bg9o3zKwW2"
html_js_files = [
    (_MERMAID_URL, {"integrity": _MERMAID_SRI, "crossorigin": "anonymous", "defer": "defer"}),
    ("js/mermaid-init.js", {"defer": "defer"}),
]

# 5. ページとして読み込まないフォルダ・ファイル
exclude_patterns = [
    "_templates", "_includes",
]
