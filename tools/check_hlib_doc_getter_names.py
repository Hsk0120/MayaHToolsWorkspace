"""生成済みSphinxの短名署名・説明・正式名参照をMaya不要で検査する。"""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import pickle
import sys

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "maya/inhouse/hlib"
sys.path.insert(0, str(_PACKAGE_ROOT / "_docs"))

from _getterNames import GetterDocumentation


class _SignatureParser(HTMLParser):
    """指定したHTMLアンカーの関数署名だけを抽出する。"""

    def __init__(self, identifier):
        """署名を探す公開関数名を保持する。

        Args:
            identifier (str): 対象dt要素のHTMLアンカー。
        """
        super().__init__()
        self.identifier = identifier
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        """対象のdt要素で文字列の収集を始める。

        Args:
            tag (str): HTML要素名。
            attrs (list[tuple]): 要素のアトリビュート名と値。
        """
        if tag == "dt" and dict(attrs).get("id") == self.identifier:
            self.active = True

    def handle_endtag(self, tag):
        """署名のdt要素が終わったら収集を終える。

        Args:
            tag (str): 終了するHTML要素名。
        """
        if tag == "dt":
            self.active = False

    def handle_data(self, data):
        """署名の引数・区切り・既定値を表示順で集める。

        Args:
            data (str): HTML要素内のテキスト。
        """
        if self.active:
            self.parts.append(data)


def _signature_parameters(html, identifier):
    """関数名を除く署名を返し、未掲載のアンカーはNoneで示す。

    Args:
        html (str): 生成されたHTML。
        identifier (str): 対象の公開関数名。

    Returns:
        str | None: 引数表示の文字列。署名がない場合はNone。
    """
    parser = _SignatureParser(identifier)
    parser.feed(html)
    signature = "".join(parser.parts)
    _, opening, parameters = signature.partition("(")
    return " ".join(parameters.split()) if opening else None


def check(build_dir):
    """Sphinx環境とHTMLの両方で取得・判定APIの表示を照合する。

    Args:
        build_dir (Path): HTMLビルドの出力先。

    Returns:
        list[str]: 不一致の説明。空なら全て一致。
    """
    build_dir = Path(build_dir)
    with (build_dir / ".doctrees/environment.pickle").open("rb") as stream:
        environment = pickle.load(stream)
    docs = GetterDocumentation(_PACKAGE_ROOT)
    objects = environment.autoapi_all_objects
    # BuildEnvironmentのpickleではdomainインスタンスは除かれるが、登録データは残る。
    references = environment.domaindata["py"]["objects"]
    errors = []
    html_cache = {}
    for pair in docs.aliases.values():
        alias, getter = objects.get(pair.alias), objects.get(pair.getter)
        if alias is None or getter is None:
            errors.append("AutoAPIの対応が見つかりません: " + pair.alias)
            continue
        if alias.args != getter.args:
            errors.append("短名の署名が正式メソッドと異なります: " + pair.alias)
        expected = docs.rewrite_docstring(getter.docstring, pair.parameters, owner=pair.getter)
        if alias.docstring != expected:
            errors.append("短名の説明が正式メソッドと異なります: " + pair.alias)
        if alias.return_annotation != getter.return_annotation:
            errors.append("短名の戻り型が正式メソッドと異なります: " + pair.alias)
        if alias.overloads != getter.overloads or alias.type_params != getter.type_params:
            errors.append("短名のオーバーロードまたは型引数が正式メソッドと異なります: " + pair.alias)
        if getter.display:
            errors.append("正式取得・判定名がAPI一覧の表示対象です: " + pair.getter)
        is_command = pair.alias.startswith("hlib.cmds.")
        public_alias = "hlib." + pair.alias.rsplit(".", 1)[-1] if is_command else pair.alias
        public_getter = "hlib." + pair.getter.rsplit(".", 1)[-1] if is_command else pair.getter
        entry = references.get(public_alias)
        original_entry = references.get(public_getter)
        if entry is None:
            errors.append("短名の参照が未登録です: " + public_alias)
            continue
        if original_entry is None or original_entry.node_id != entry.node_id:
            errors.append("正式名の参照が短名へ解決しません: " + public_getter)
        path = build_dir / (entry.docname + ".html")
        if path not in html_cache:
            html_cache[path] = path.read_text(encoding="utf-8")
        html = html_cache[path]
        if f'id="{entry.node_id}"' not in html:
            errors.append("短名のHTMLアンカーがありません: " + public_alias)
        if is_command:
            short_name = pair.alias.rsplit(".", 1)[-1]
            getter_name = pair.getter.rsplit(".", 1)[-1]
            public_cmds_alias = "hlib.cmds." + short_name
            public_cmds_getter = "hlib.cmds." + getter_name
            cmds_entry = references.get(public_cmds_alias)
            cmds_getter_entry = references.get(public_cmds_getter)
            if cmds_entry is None:
                errors.append("cmdsの短名参照が未登録です: " + public_cmds_alias)
            elif cmds_entry.docname != entry.docname:
                errors.append("cmdsとルートの説明ページが異なります: " + public_cmds_alias)
            if (cmds_entry is None or cmds_getter_entry is None
                    or cmds_entry.node_id != cmds_getter_entry.node_id):
                errors.append("cmdsの正式名が短名へ解決しません: " + public_cmds_getter)
            root_signature = _signature_parameters(html, public_alias)
            cmds_signature = _signature_parameters(html, public_cmds_alias)
            if root_signature is None or cmds_signature is None or root_signature != cmds_signature:
                errors.append("cmdsとルートの構文・引数表示が異なります: " + public_cmds_alias)
            if f'id="{public_cmds_getter}"' not in html:
                errors.append("cmdsの既存get名のHTMLアンカーがありません: " + public_cmds_getter)
        if not is_command and f'id="{pair.getter}"' not in html:
            errors.append("既存取得・判定名のHTMLアンカーがありません: " + pair.getter)
    commands = build_dir / "autoapi/hlib/cmds/index.html"
    command_html = commands.read_text(encoding="utf-8")
    for old_module, short_module in docs.command_modules.items():
        old_name, short_name = old_module.rsplit(".", 1)[-1], short_module.rsplit(".", 1)[-1]
        modules = environment.autoapi_objects
        expected_synopsis = docs.rewrite_docstring(modules[old_module].docstring, owner=short_module)
        if modules[short_module].docstring != expected_synopsis:
            errors.append("コマンド概要が正式モジュールと異なります: " + short_module)
        if f'href="{old_name}/index.html"' in command_html:
            errors.append("コマンド一覧にget入口が重複しています: " + old_name)
        if f'href="{short_name}/index.html"' not in command_html:
            errors.append("コマンド一覧に短名がありません: " + short_name)
        legacy = build_dir / f"autoapi/hlib/cmds/{old_name}/index.html"
        if not legacy.is_file() or f'id="hlib.{old_name}"' not in legacy.read_text(encoding="utf-8"):
            errors.append("既存getコマンドページのアンカーがありません: " + old_name)
        short_html = (build_dir / f"autoapi/hlib/cmds/{short_name}/index.html").read_text(encoding="utf-8")
        if '<dt class="field-odd">param ' in short_html or '<dt class="field-even">param ' in short_html:
            errors.append("コマンドに未整形の引数フィールドがあります: " + short_name)
    if "hlib" in sys.modules or "maya" in sys.modules:
        errors.append("検査中にhlibまたはMayaがimportされました。")
    return errors


def main():
    """指定されたビルド成果物を検査し、終了コードで結果を伝える。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    arguments = parser.parse_args()
    errors = check(arguments.build_dir)
    for error in errors:
        print(error)
    print(f"取得・判定APIの文書検査: {len(errors)} 件の不一致")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
