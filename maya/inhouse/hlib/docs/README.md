# hlib ドキュメントのビルド

デザインには Sphinxdoc テーマと `_static/custom.css` を使用しています。
コードブロックは `_static/code-dark-plus.css` でVS Code Dark+に近い配色にしています。
Pygmentsによる静的な分類のため、VS Codeのセマンティックハイライトとは一部異なります。

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

PowerShell やタスクから一時停止なしで実行する場合:

```powershell
& ./maya/inhouse/hlib/docs/rebuild.bat --no-pause
```

成功時の終了コードは `0`、失敗時は非 `0` です。警告も失敗として扱います。
出力先は `maya/inhouse/hlib/docs/_build/html/index.html` です。
依存パッケージを変更した場合は、先に上記の `pip install` を再実行してください。

- `conf.py`: Sphinx と静的 API 解析の設定
- `_templates/autoapi/python/class.rst`: cymel に合わせたクラス一覧・詳細の表記
- `index.rst`: ドキュメントの入口
- `getting_started.rst`: Maya 内での使用例
- `development.rst`: パッケージ構成と更新方針
- `requirements.txt`: ドキュメント専用の依存パッケージ

API ページはビルドごとに hlib のソースから生成します。
`autoapi/` は一時生成物です。直接編集せず、元の docstring を更新してください。
ビルド成功は Maya 内での API 動作確認を意味しません。
