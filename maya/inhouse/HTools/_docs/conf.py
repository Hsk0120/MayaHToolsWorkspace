"""Mayaを読み込まずにHToolsの各ツールの説明ページを生成する。"""
project = "HTools"
copyright = "2026 Hsk0120"
language = "ja"
extensions = []
exclude_patterns = ["_build", "README.md", "requirements.txt"]
html_theme = "sphinxdoc"
pygments_style = "one-dark"
# mlibの見た目(本文・目次の幅、配色・見出し・コード表示)に揃えたCSSの写しを _static に置く
# (FramePlayer の説明ページと同じ形。mlib側の文書の配置が変わっても影響を受けない)。
html_static_path = ["_static"]
html_css_files = ["custom.css", "code-dark-plus.css"]
html_title = "HTools ドキュメント"
