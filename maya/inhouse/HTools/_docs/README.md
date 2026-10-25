# HTools の説明ページ(Sphinx)

HToolsメニューの各ツールの使い方・画面の説明。GitHub Pages の `htools/` に公開する。

- 1ツール1ページ: `<カテゴリ>/<ツールのファイル名>.rst`(メニューのフォルダー・ファイル名と同じ)。
  `HTools.toolHelp.openHelp(カテゴリ, ツール)` とHToolsメニューの Help がこの名前でページを開く。
- 画面のスクリーンショットは `_static/images/<カテゴリ>/<ツール>*.png`。
- ツールを足したら、ページを足してカテゴリの `index.rst` の目次へ並べる。

手元でのビルド:

```bat
python -m sphinx -W --keep-going -b html maya/inhouse/HTools/_docs maya/inhouse/HTools/_docs/_build/html
```
