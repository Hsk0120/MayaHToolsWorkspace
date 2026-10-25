"""Mayaを読み込まずにmlrigの利用・検証ドキュメントを生成する。"""

project = "mlrig"
copyright = "2026 Hsk0120"
language = "ja"
extensions = []
exclude_patterns = ["_build", "README.md", "requirements.txt", "locale"]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
# CSSはこのdocs内で管理する。他パッケージの文書やビルド処理には依存しない。
html_static_path = ["_static"]
html_css_files = ["css/theme.css", "css/layout.css", "css/code-dark-plus.css"]
html_title = "mlrig ドキュメント"

# ---- 英語版(gettext) ----
# 本文の文を locale/en/LC_MESSAGES/docs.po に取り出し、英訳して保存する(英訳は tools/translate_docs.py)。
# 英語版は ``-D language=en`` でビルドする。訳の無い文は日本語のまま出る。
locale_dirs = ["locale/"]
gettext_compact = "docs"  # 全ページの文を1つの docs.po にまとめる。
gettext_location = False  # 行番号を書かない(本文の行がずれても .po が変わらないように)。
gettext_uuid = False
templates_path = ["_templates"]  # 言語の切り替え(_templates/layout.html)。


def setup(app):
    """英語版のときだけ、ページの題名を英語にする(conf.py の値は .po の翻訳の対象外のため)。"""
    def english_title(app, config):
        if config.language == "en":
            config.html_title = "mlrig documentation"
    app.connect("config-inited", english_title)
