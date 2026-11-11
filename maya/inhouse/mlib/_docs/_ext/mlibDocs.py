"""mlib文書に固有の表示を、SphinxとAutoAPIへ登録する。

本文やビルド設定はsource/conf.py、ページの配置はsource/_templatesが担当する。
この拡張は継承図・生成時の引数表示・パッケージ名の補正・短い参照の解決をつなぐ。
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


def _include_private_base_members(app, what, name, obj, skip, options):
    """掲載する member を AutoAPI の既定から調整する。

    - 非公開の基底クラス(先頭 ``_``、例 ``_ContainerMixin``)から受け継いだ公開 member は、
      基底のページを載せないため、受け継いだ公開クラスのページに掲載する。
      公開の基底から受け継いだ member は従来どおり基底のページだけに載せる。

    Returns:
        bool | None: False は掲載、None は AutoAPI の判定に任せる。
    """
    if getattr(obj, "inherited", False) and not obj.short_name.startswith("_"):
        base = obj.obj.get("inherited_from") or {}
        base_name = base.get("full_name", "").rpartition(".")[2]
        if base_name.startswith("_"):
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


def _display_bases(bases):
    """クラスページの「ベースクラス」に載せる基底の名前を返す。

    - ``A if TYPE_CHECKING else B`` の形の基底(Lambert 等)は、式ではなく型検査用の A を載せる。
      実行時の継承は変えず、表示だけを整える。
    - 非公開の基底(先頭 ``_``、例 ``_ContainerMixin``)はページが無いため載せない。
      受け継いだ member は :func:`_include_private_base_members` で派生クラスのページに載る。

    Args:
        bases (list[str]): AutoAPI が解析した基底の名前。

    Returns:
        list[str]: 表示する基底の名前。
    """
    result = []
    for base in bases or ():
        match = re.fullmatch(r"\s*(.+?)\s+if\s+.+\s+else\s+.+", base)
        if match:
            base = match.group(1)
        if base.rpartition(".")[2].startswith("_"):
            continue
        result.append(base)
    return result


def _ancestor_names(class_name):
    """短いクラス名から、自身と祖先の短い名前を近い順に返す(静的解析した継承情報による)。"""
    order, queue = [], [class_name]
    while queue:
        name = queue.pop(0)
        if name in order:
            continue
        order.append(name)
        info = _CLASS_HIERARCHY.get(name)
        if info:
            queue.extend(base.rpartition(".")[2] for base in info["bases"])
    return order


class _ShortReferenceResolver:
    """クラスのページをまたぐ短い参照や、パッケージ経由の名前を、登録済みの完全名へ解決する。

    ``autoapi_own_page_level = "class"`` ではクラスのページに現在のモジュールの文脈が無いため、
    ``:meth:`Joint.orient``` や ``:class:`NodeRef``` のような短い参照が解決しない。
    また AutoAPI は定義モジュールの名前(``mlib.nodes.transform.Transform``)で登録するため、
    ``mlib.nodes.Transform`` のようなパッケージ経由の名前も解決しない。
    Sphinx の ``missing-reference`` で、次の順に完全名を探して解決する。

    1. ``mlib.cmds.createNode.createNode`` のようにモジュールと関数が同名の重複を除いた名前。
    2. ``Class.member`` の Class と、その祖先クラスの member(継承したメソッド)。
    3. 名前の後ろが一致する登録名。前に付いたパッケージ(``mlib.nodes`` 等)は、
       登録名の先頭と一致することを求める。候補が複数なら、参照元のページのクラスとその祖先、
       参照元のモジュールの順に絞り、1つに決まらなければ解決しない(誤ったリンクを作らない)。
    """

    def __init__(self):
        self._env_id = None
        self._objects = {}
        self._by_suffix = {}

    def _index(self, env):
        """Python ドメインの登録名を、後ろの部分の名前から引ける表にする(ビルドごとに作り直す)。"""
        objects = env.get_domain("py").objects
        if self._env_id == id(env) and len(objects) == len(self._objects):
            return
        self._env_id = id(env)
        self._objects = dict(objects)
        self._by_suffix = {}
        for full_name in self._objects:
            parts = full_name.split(".")
            for start in range(1, len(parts)):
                self._by_suffix.setdefault(".".join(parts[start:]), []).append(full_name)

    @staticmethod
    def _context(refdoc):
        """参照元のページから、(クラスの短い名前 | None, モジュールの完全名 | None)を返す。"""
        parts = refdoc.replace("\\", "/").split("/")
        if len(parts) < 3 or parts[0] != "autoapi":
            return None, None
        parts = parts[1:]
        if parts[-1] == "index":
            return None, ".".join(parts[:-1])
        return parts[-1], ".".join(parts[:-1])

    def _accepts(self, full_name, objtypes):
        """登録名の種類が、参照の役割(meth・class 等)に合うか判定する。"""
        return objtypes is None or self._objects[full_name].objtype in objtypes

    def _find(self, target, objtypes, refdoc):
        """target に対応する登録名を1つ返す。決まらなければ None。"""
        if target in self._objects:
            return target if self._accepts(target, objtypes) else None
        parts = target.split(".")
        # 1. モジュールと関数が同名(mlib.cmds.createNode.createNode)。
        if len(parts) >= 2 and parts[-1] == parts[-2]:
            shorter = ".".join(parts[:-1])
            if shorter in self._objects and self._accepts(shorter, objtypes):
                return shorter
        context_class, context_module = self._context(refdoc)
        # 2. Class.member の祖先クラスを辿る。
        if len(parts) >= 2 and parts[-2] in _CLASS_HIERARCHY:
            for name in _ancestor_names(parts[-2]):
                info = _CLASS_HIERARCHY.get(name)
                full_name = f"{info['qualname']}.{parts[-1]}" if info else None
                if full_name in self._objects and self._accepts(full_name, objtypes):
                    return full_name
        # 3. 後ろが一致する登録名。
        for start in range(len(parts)):
            prefix = ".".join(parts[:start])
            candidates = [
                name for name in self._by_suffix.get(".".join(parts[start:]), ())
                if (not prefix or name.startswith(prefix + ".")) and self._accepts(name, objtypes)
            ]
            if not candidates:
                continue
            if len(candidates) == 1:
                return candidates[0]
            return self._narrow(candidates, context_class, context_module)
        return None

    @staticmethod
    def _narrow(candidates, context_class, context_module):
        """複数の候補を、参照元のクラスの祖先・参照元のモジュールの順に絞る。"""
        if context_class:
            for name in _ancestor_names(context_class):
                info = _CLASS_HIERARCHY.get(name)
                if not info:
                    continue
                owned = [c for c in candidates if c.rpartition(".")[0] == info["qualname"]]
                if len(owned) == 1:
                    return owned[0]
        if context_module:
            local = [c for c in candidates if c.rpartition(".")[0] == context_module]
            if len(local) == 1:
                return local[0]
        return None

    def __call__(self, app, env, node, contnode):
        """Sphinx の ``missing-reference`` から呼ばれ、解決できた参照のノードを返す。"""
        if node.get("refdomain") != "py":
            return None
        target = node.get("reftarget", "")
        # 非公開の名前(先頭 ``_``)はページが無いため探さない。
        if not target[:1].isalpha():
            return None
        self._index(env)
        domain = env.get_domain("py")
        objtypes = domain.objtypes_for_role(node.get("reftype"))
        full_name = self._find(target, objtypes, node.get("refdoc", ""))
        if full_name is None:
            return None
        return domain.resolve_xref(env, node["refdoc"], app.builder, node["reftype"], full_name, node, contnode)


_resolve_short_reference = _ShortReferenceResolver()


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
    jinja_env.globals["display_bases"] = _display_bases
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
    app.connect("autoapi-skip-member", _include_private_base_members)
    app.connect("missing-reference", _resolve_short_reference)
