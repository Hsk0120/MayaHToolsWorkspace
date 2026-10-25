"""mlib文書に固有の表示を、SphinxとAutoAPIへ登録する。

本文やビルド設定はsource/conf.py、ページの配置はsource/_templatesが担当する。
この拡張は継承図・生成時の引数表示・パッケージ名の補正をつなぐ。
Mayaやmlibはimportせず、Pythonソースだけを調べる。
"""

import logging
from pathlib import Path
import re

import autoapi
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

from _constructorSignatures import ConstructorDocumentation
from _mermaidClasses import ancestor_class_diagram, collect_class_hierarchy

_MLIB_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_NAME = _MLIB_ROOT.name
_CLASS_HIERARCHY = collect_class_hierarchy(_MLIB_ROOT)
_CONSTRUCTOR_DOCS = ConstructorDocumentation(_PACKAGE_NAME, _MLIB_ROOT)

# 独自module.rstからAutoAPI標準のmodule.rstを参照するための別名。
# 同じ名前で読み込むと、独自テンプレート自身を再び読み込んでしまう。
_PACKAGED_TEMPLATE_PREFIX = "autoapi-packaged"
_PACKAGED_TEMPLATES_IN_USE = ("python/module.rst",)


class _ReexportedSubpackageFilter(logging.Filter):
    """mlib/__init__.py がサブパッケージを公開するimport（例: ``from . import cmds``）で、
    AutoAPI が同じオブジェクトを
    親ページとサブパッケージページの両方に載せてしまう重複警告だけを無視する。"""

    _IGNORED_MESSAGE_PREFIXES = (
        f"duplicate object description of {_PACKAGE_NAME}.cmds,",
    )

    def filter(self, record):
        """再公開されたcmdsの既知の重複だけを除く。"""
        message = record.getMessage()
        return not message.startswith(self._IGNORED_MESSAGE_PREFIXES)


def _include_constructors(app, what, name, obj, skip, options):
    """AutoAPI が既定で隠す初期化・割り当てメソッドも掲載する。"""
    if what == "method" and obj.short_name in {"__init__", "__new__"}:
        if not obj.inherited and not obj.imported:
            return False
    return None


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


def _ancestor_diagram(class_name):
    """テンプレートが指定したクラスの継承図を返す。"""
    return ancestor_class_diagram(class_name, _CLASS_HIERARCHY)


def prepare_autoapi(jinja_env):
    """AutoAPI のテンプレート環境へ、mlib 独自テンプレート用の設定を追加する。

    - クラスページのテンプレートから継承図を組み立てる関数を登録する。
    - 同梱テンプレートを ``autoapi-packaged/`` 接頭辞付きでも引けるようにする。
      ``_templates/autoapi`` の同名ファイルが優先されるため、上書きした
      テンプレートから元の既定表示へ処理を委ねるにはこの接頭辞で指定する。
    """
    jinja_env.globals["package_name"] = _PACKAGE_NAME
    jinja_env.globals["node_constructor_args"] = _CONSTRUCTOR_DOCS.signature
    jinja_env.globals["ancestor_class_diagram"] = _ancestor_diagram
    jinja_env.loader = ChoiceLoader([
        jinja_env.loader,
        PrefixLoader({
            _PACKAGED_TEMPLATE_PREFIX: FileSystemLoader(str(_PACKAGED_TEMPLATE_DIR)),
        }),
    ])


def _adapt_package_name_in_source(source):
    """本文・使用例・AutoAPI参照を、配置されたパッケージ名へ合わせる。

    JSON形式識別子、宣言定数、ページのファイル名は変更しない。
    元の rst/Python ファイルは書き換えず、ビルド入力だけを変換する。

    Args:
        source (list[str]): 変換対象のソース。先頭要素だけを更新する。
    """
    if _PACKAGE_NAME == "mlib":
        return
    # AutoAPIが既に配置名で作った完全名は、同じ接頭辞で再置換しない。
    already_named = re.escape(_PACKAGE_NAME) + r'(?=$|[._/]|[^A-Za-z0-9_-])'
    pattern = (r'(https?://[^\s<>`]+|[\"\x27]mlib\.blendShape[\"\x27]|'
               + already_named + r')|(?<![A-Za-z0-9_])mlib(?=$|[._/]|[^A-Za-z0-9_-])')
    before = source[0].splitlines()
    after = [re.sub(pattern, lambda match: match[1] or _PACKAGE_NAME, line)
             for line in before]
    # 長いパッケージ名でもreSTの見出し線が短くならないようにする。
    for index in range(1, len(after)):
        line = after[index].strip()
        if line and len(set(line)) == 1 and line[0] in "=-~^\"" and before[index - 1] != after[index - 1]:
            after[index] = line[0] * max(len(line), len(after[index - 1]) * 2)
    source[0] = "\n".join(after) + "\n"


def _adapt_package_name(app, docname, source):
    """通常のページ本文を、配置されたパッケージ名へ合わせる。"""
    _adapt_package_name_in_source(source)


def _adapt_included_package_name(app, relative_path, parent_docname, source):
    """includeされた図にも、通常のページと同じ配置名を反映する。"""
    _adapt_package_name_in_source(source)


def setup(app):
    """Sphinxのビルド時に必要な表示補正だけを登録する。"""
    logging.getLogger("sphinx").addFilter(_ReexportedSubpackageFilter())
    app.connect("source-read", _adapt_package_name)
    app.connect("include-read", _adapt_included_package_name)
    app.connect("autoapi-skip-member", _include_constructors)
