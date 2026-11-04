# QPEガイドのビルド

Python 3.11以上を使います。Maya・Qt・親リポジトリの文書は不要です。
QPE直下から次を実行します。

```powershell
python -m venv docs/.venv
docs/.venv/Scripts/python -m pip install -r docs/requirements.txt
docs/.venv/Scripts/python -m sphinx -E -a -b html -W --keep-going docs docs/_build/html
```

`docs/_build/html/index.html`がトップです。`.venv`と`_build`はGit対象外です。
版は`src/product.h`の製品用`QPE_VERSION`を読みます。
本文は日本語、UI表記は実装の日本語メニューを基本とし、MayaのOpen／Import等は併記します。

## 配置と見た目

- `index.rst`から導入、カラム／タブ、ファイル操作、Maya、設定、キー、開発、制限へ移動します。
- `_static/custom.css`は他の内製ガイドと同じ段組みをQPE内へ保持したものです。他ツールを参照せず単独で生成できます。
- `_static/quick-path-explorer.css`でQPEのダーク面と公式アイコンの青緑・淡黄色を指定します。
- `_static/layout.svg`は説明用の模式図です。実画面のスクリーンショットとは区別します。
- `tools/check_docs.py`でリンク・検索・スマートフォン／iPad幅を確認します。ブラウザー検証用依存は`browser-requirements.txt`にあります。

```powershell
docs/.venv/Scripts/python -m pip install -r docs/browser-requirements.txt
docs/.venv/Scripts/python -m playwright install chromium
docs/.venv/Scripts/python docs/tools/check_docs.py --directory docs/_build/html --output .maya-output/docs-check
```

## GitHubでの公開

`.github/workflows/mlib-docs.yml`で既存サイトの`quick-path-explorer/`へ追加します。
他ツールと同じPages成果物を使い、サイト全体を別ワークフローで上書きしません。
Sphinxは警告をエラーにし、公開前後にQPEのページ・検索・ビルドSHAをブラウザー検証します。
将来別リポジトリへ移す場合も、このSphinxプロジェクトをそのままビルドできます。
