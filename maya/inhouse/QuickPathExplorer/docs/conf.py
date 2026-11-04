"""QPE単独でビルドできる利用ガイドのSphinx設定。MayaやQtは読み込まない。"""

import os
from pathlib import Path
import re


QPE_ROOT = Path(__file__).resolve().parent.parent
match = re.search(r'#define\s+QPE_VERSION\s+"([^"]+)"',
                  (QPE_ROOT / "src/product.h").read_text(encoding="utf-8"))
if match is None:
    raise ValueError("src/product.hにQPE_VERSIONがありません。")

project = "QuickPathExplorer"
author = "Hsk0120"
copyright = "2026 Hsk0120"
version = release = match.group(1)
language = "ja"
extensions = []
exclude_patterns = ["_build", ".venv", "README.md", "tools"]
html_theme = "sphinxdoc"
html_title = f"QuickPathExplorer {release} ドキュメント"
html_logo = "../icons/quickPathExplorer.svg"
html_favicon = html_logo
html_static_path = ["_static"]
html_css_files = ["custom.css", "quick-path-explorer.css"]
templates_path = ["_templates"]
html_show_sourcelink = False
html_sidebars = {"**": ["globaltoc.html", "searchbox.html"]}
html_context = {"build_revision": os.environ.get("GITHUB_SHA", "local")}
pygments_style = "one-dark"
nitpicky = True
