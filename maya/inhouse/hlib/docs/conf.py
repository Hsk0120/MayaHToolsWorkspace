"""Build hlib documentation without importing Maya or hlib."""

from pathlib import Path
import logging
import sys

import autoapi
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

# リポジトリルートからのCIビルドでも、docs内の補助モジュールを解決する。
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
copyright = "2026 Hsk0120"
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

exclude_patterns = [
    "_build", "_templates", ".venv", "README.md", "_generated",
    "research", "*_research.rst", "*_survey.rst", "*_inventory.json",
    "concept_classes.rst",
]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
html_static_path = ["_static"]
html_css_files = ["custom.css", "code-dark-plus.css", "mermaid.css"]

# Mermaid はリポジトリに同梱せず、jsDelivr から正確な版を指定して読み込む。
# 版を上げるときは、その版の dist/mermaid.min.js を取得して
# ``sha384`` ダイジェストを base64 化した値で _MERMAID_SRI も必ず更新する。
# (値が一致しないとブラウザが読み込みを拒否し、図が描画されない)
_MERMAID_VERSION = "11.17.2"
_MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{_MERMAID_VERSION}/dist/mermaid.min.js"
_MERMAID_SRI = "sha384-EOXBFmc3gx5mb+vn0vPvvGqACToJD24hhacX5Yx+8NUUQrHIle/Qi5Bg9o3zKwW2"
# 大きなファイルの取得で本文の表示を止めないよう、どちらも defer で実行順だけを保つ。
html_js_files = [
    (_MERMAID_URL, {"integrity": _MERMAID_SRI, "crossorigin": "anonymous", "defer": "defer"}),
    ("mermaid-init.js", {"defer": "defer"}),
]
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


# 独自テンプレートが sphinx-autoapi 同梱のテンプレートを複製せずに参照するための名前空間。
# 例: ``{% include "autoapi-packaged/python/module.rst" %}``
_PACKAGED_TEMPLATE_PREFIX = "autoapi-packaged"
# 独自テンプレートが同梱側から実際に読み込むテンプレート(存在確認に使う)。
_PACKAGED_TEMPLATES_IN_USE = ("python/module.rst",)


def _find_packaged_templates():
    """sphinx-autoapi が配布物に同梱しているテンプレートのフォルダを返す。

    sphinx-autoapi の内部設定値には頼らず、インストールされたパッケージの
    ``templates`` フォルダを直接指す。版の更新で配置が変わっていた場合は、
    ページ生成中の分かりにくい TemplateNotFound ではなく、設定の読み込み時に
    原因と確認先を示して止める。

    Returns:
        Path: 同梱テンプレートのフォルダ。

    Raises:
        RuntimeError: 独自テンプレートが参照する同梱テンプレートが見つからない場合。
    """
    template_dir = Path(autoapi.__file__).resolve().parent / "templates"
    missing = [name for name in _PACKAGED_TEMPLATES_IN_USE if not (template_dir / name).is_file()]
    if missing:
        raise RuntimeError(
            "sphinx-autoapi の同梱テンプレートが見つかりません: "
            f"{', '.join(missing)} (探した場所: {template_dir})。"
            "インストールされている sphinx-autoapi の版と requirements.txt を確認し、"
            "_templates/autoapi/python/module.rst の include 先を合わせてください。"
        )
    return template_dir


_PACKAGED_TEMPLATE_DIR = _find_packaged_templates()


def _prepare_jinja_env(jinja_env):
    """AutoAPI のテンプレート環境へ、hlib 独自テンプレート用の設定を追加する。

    - クラスページのテンプレートから継承図を組み立てる関数を登録する。
    - 同梱テンプレートを ``autoapi-packaged/`` 接頭辞付きでも引けるようにする。
      ``_templates/autoapi`` の同名ファイルが優先されるため、上書きした
      テンプレートから元の既定表示へ処理を委ねるにはこの接頭辞で指定する。
    """
    jinja_env.globals["ancestor_class_diagram"] = (
        lambda class_name: ancestor_class_diagram(class_name, _CLASS_HIERARCHY)
    )
    jinja_env.loader = ChoiceLoader([
        jinja_env.loader,
        PrefixLoader({
            _PACKAGED_TEMPLATE_PREFIX: FileSystemLoader(str(_PACKAGED_TEMPLATE_DIR)),
        }),
    ])


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
