"""FramePlayer ドキュメントの Sphinx 設定。

FramePlayer は将来、別リポジトリへ切り出す想定のため、この docs フォルダーだけで完結する
(親リポジトリの hlib・hedit ドキュメントや共有設定に依存しない)。見た目は hedit と同じ作りで、色だけを
FramePlayer の画面に合わせる(``_static/frameplayer.css``)。
"""
import re
from pathlib import Path

FRAMEPLAYER_ROOT = Path(__file__).resolve().parent.parent

# バージョンは src/app/FramePlayer.rc の FP_VERSION_TEXT を正本とする(exe とインストーラーも同じ値を使う)。
_match = re.search(r'#define\s+FP_VERSION_TEXT\s+"([^"]+)"',
                   (FRAMEPLAYER_ROOT / "src" / "app" / "FramePlayer.rc").read_text(encoding="utf-8"))
release = _match.group(1) if _match else "unknown"
version = release

project = "FramePlayer"
copyright = "2026 Hsk0120"
author = "Hsk0120"
language = "ja"

extensions = []
exclude_patterns = ["_build", ".venv", "README.md", "locale", "tools"]

html_theme = "sphinxdoc"
html_title = "FramePlayer {} ドキュメント".format(release)
html_static_path = ["_static"]
html_css_files = ["custom.css", "code-dark-plus.css", "frameplayer.css"]
html_show_sourcelink = False
pygments_style = "one-dark"

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
            config.html_title = "FramePlayer {} documentation".format(release)
    app.connect("config-inited", english_title)
