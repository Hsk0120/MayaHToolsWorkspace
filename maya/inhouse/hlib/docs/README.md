# hlib ドキュメントのビルド

デザインには Sphinxdoc テーマと `_static/custom.css` を使用しています。
コードブロックは `_static/code-dark-plus.css` でVS Code Dark+に近い配色にしています。
Pygmentsによる静的な分類のため、VS Codeのセマンティックハイライトとは一部異なります。

クラス継承図の描画に使う Mermaid はリポジトリに同梱していません。
`conf.py` で jsDelivr の版を固定した URL と SRI ハッシュ(`integrity`)を指定して読み込むため、
図の表示にはネットワーク接続が必要です(オフラインでは図の元テキストがそのまま表示されます)。
版を上げるときは `_MERMAID_VERSION` と、その版の `dist/mermaid.min.js` から計算した
`_MERMAID_SRI` を必ず同時に更新してください。ハッシュは次のように計算できます。
取得したファイルはリポジトリの外(一時フォルダー)に保存し、計算後に削除します。
`_static` などへ置くと、同梱をやめた Mermaid 本体をビルド出力やコミットに
再び含めてしまうためです。

```powershell
$js = Join-Path $env:TEMP "mermaid-sri-check.min.js"
curl.exe -sSfL -o $js https://cdn.jsdelivr.net/npm/mermaid@<版>/dist/mermaid.min.js
python -c "import base64,hashlib,sys;print('sha384-'+base64.b64encode(hashlib.sha384(open(sys.argv[1],'rb').read()).digest()).decode())" $js
Remove-Item $js
```

ビルドした HTML が `conf.py` の版・ハッシュどおりに Mermaid を読み込み、
Mermaid 本体を出力に含んでいないことは、ブラウザなしで次のように確認できます
(GitHub Actions でもビルド直後に同じ確認を行います)。

```powershell
& ./maya/inhouse/hlib/docs/.venv/Scripts/python.exe tools/check_hlib_docs.py --check-directory maya/inhouse/hlib/docs/_build/html
```

## 公開版と自動更新

公開URL: [hlib ドキュメント](https://hsk0120.github.io/MayaHToolsWorkspace/)

`.github/workflows/hlib-docs.yml` が、`main` へのpush時にSphinxをビルドし、
GitHub Pagesへ公開します。対象は `maya/inhouse/hlib/**` またはワークフロー自体の変更です。
Mayaや外部submoduleは不要で、Python 3.11と本フォルダーの `requirements.txt` を使用します。
生成HTMLのコミットは不要です。ローカルの再ビルドだけでは公開版は更新されません。

[Actionsの実行履歴](https://github.com/Hsk0120/MayaHToolsWorkspace/actions/workflows/hlib-docs.yml)
で `build`・`deploy` の成功を確認できます。手動実行は `Run workflow` → `main` です。
詳しい仕組みとトラブル時の確認方法は `installation.rst` に記載しています。

## ローカルビルド

Python 3.11 以上を使用します。Maya や mayapy は不要です。
リポジトリルートから PowerShell で実行してください。
`py` がない場合は、インストール済み Python の実行ファイルを指定します。

```powershell
py -3.11 -m venv maya/inhouse/hlib/docs/.venv
& ./maya/inhouse/hlib/docs/.venv/Scripts/python.exe -m pip install -r maya/inhouse/hlib/docs/requirements.txt
& ./maya/inhouse/hlib/docs/.venv/Scripts/python.exe -m sphinx -b html -W --keep-going maya/inhouse/hlib/docs maya/inhouse/hlib/docs/_build/html
Start-Process maya/inhouse/hlib/docs/_build/html/index.html
```

`-W` により警告もビルド失敗として扱います。全ページを再生成する場合は
Sphinx の引数に `-E -a` を追加してください。

## 再ビルド

初回セットアップ後は `maya/inhouse/hlib/docs/rebuild.bat` をダブルクリックすると、
全ページを再生成します。終了時に結果を確認できるよう一時停止します。
実行時のカレントディレクトリには依存しません。
Sphinx は出力先にある古いファイルを削除しないため、`rebuild.bat` は毎回
`_build/html` を空にしてから生成します(ソースから消したファイルが出力に残らないようにするため)。
以前の出力が残っている状態で上記の `sphinx` コマンドを直接使う場合は、先に `_build/html` を削除してください。

PowerShell やタスクから一時停止なしで実行する場合:

```powershell
& ./maya/inhouse/hlib/docs/rebuild.bat --no-pause
```

成功時の終了コードは `0`、失敗時は非 `0` です。警告も失敗として扱います。
出力先は `maya/inhouse/hlib/docs/_build/html/index.html` です。
依存パッケージを変更した場合は、先に上記の `pip install` を再実行してください。

- `conf.py`: Sphinx と静的 API 解析の設定
- `_templates/autoapi/python/class.rst`: クラスページの構成(継承図と、メンバーを
  「メソッド」「プロパティ・属性」に分けた早見表・説明)
- `_templates/autoapi/python/module.rst`: `hlib.cmds` のコマンドページだけを独自書式にし、
  それ以外は sphinx-autoapi 同梱の既定テンプレートへ委ねる(同梱テンプレートは複製しない)
- `index.rst`: ドキュメントの入口
- `getting_started.rst`: Maya 内での使用例
- `development.rst`: パッケージ構成と更新方針
- `requirements.txt`: ドキュメント専用の依存パッケージ

API ページはビルドごとに hlib のソースから生成します。
`autoapi/` は一時生成物です。直接編集せず、元の docstring を更新してください。
ビルド成功は Maya 内での API 動作確認を意味しません。
