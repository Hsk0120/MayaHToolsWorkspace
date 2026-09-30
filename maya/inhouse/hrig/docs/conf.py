"""Mayaを読み込まずにhrigの利用・検証ドキュメントを生成する。"""
from pathlib import Path

project = "hrig"
copyright = "2026 Hsk0120"
language = "ja"
extensions = []
exclude_patterns = ["_build", "README.md", "requirements.txt"]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
# hlibのCSSを直接共有し、本文・目次の幅、配色・見出し・コード表示を揃える。
html_static_path = [str(Path(__file__).resolve().parents[2] / "hlib/docs/_static")]
html_css_files = ["custom.css", "code-dark-plus.css"]
html_title = "hrig ドキュメント"
