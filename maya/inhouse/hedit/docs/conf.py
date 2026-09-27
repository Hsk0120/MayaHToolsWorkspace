"""hedit ドキュメントの Sphinx 設定。

hedit は将来、別リポジトリへ切り出す想定のため、この docs フォルダーだけで完結する
(親リポジトリの hlib ドキュメントや共有設定に依存しない)。
"""
import re
from pathlib import Path

HEDIT_ROOT = Path(__file__).resolve().parent.parent

# バージョンは埋め込みPython(src/embedded_python.h内のkInitSource)の定義を正本とする。
_match = re.search(r"__version__\s*=\s*'([^']+)'", (HEDIT_ROOT / "src" / "embedded_python.h").read_text(encoding="utf-8"))
release = _match.group(1) if _match else "unknown"
version = release

project = "hedit"
copyright = "2026 Hsk0120"
author = "Hsk0120"
language = "ja"

extensions = []
exclude_patterns = ["_build", ".venv", "README.md"]
templates_path = []

html_theme = "sphinxdoc"
html_title = "hedit {} ドキュメント".format(release)
html_static_path = ["_static"]
html_css_files = ["custom.css", "code-dark-plus.css", "hedit.css"]
html_show_sourcelink = False
pygments_style = "one-dark"

# 表の見出し・脚注などの警告をエラーとして扱う(rebuild.bat は -W を付けて実行する)。
nitpicky = False
