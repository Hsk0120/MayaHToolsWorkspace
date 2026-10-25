# mlib ドキュメントのビルド

公開する本文は `index.rst`・`whymlib.rst`・`getting_started.rst`・`modules.rst` です。
APIページはdocstringから生成します。`autoapi/` を直接編集せず、元のPythonファイルを直してください。
Mayaやmlibをimportせずにビルドできます。

## ローカル確認

リポジトリルートのPowerShellで、既存の文書用venvを使います。

```powershell
& ./maya/inhouse/mlib/_docs/.venv/Scripts/python.exe tools/check_mlib_exports.py
& ./maya/inhouse/mlib/_docs/rebuild.bat --no-pause
& ./maya/inhouse/mlib/_docs/.venv/Scripts/python.exe tools/check_mlib_docs.py --check-directory maya/inhouse/mlib/_docs/_build/html
& ./maya/inhouse/mlib/_docs/.venv/Scripts/python.exe tools/check_mlib_doc_getter_names.py maya/inhouse/mlib/_docs/_build/html
```

`rebuild.bat` は古い出力を削除し、警告も失敗として扱います。結果は `_build/html/index.html` です。
Sphinxを直接実行する場合も新しい出力先を使ってください。削除済みページは自動では消えません。
ビルド成功はMaya内での動作確認を意味しません。

## 英語版

日本語を原文とし、`locale/en/LC_MESSAGES/docs.po` に英訳を保持します。
本文やdocstringの変更後はgettextを抽出し、変更した文だけを翻訳します。
日英のビルドは順に実行してください。

```powershell
& ./maya/inhouse/mlib/_docs/.venv/Scripts/python.exe -m sphinx -E -a -b gettext -W --keep-going maya/inhouse/mlib/_docs .maya-output/mlib-docs/gettext
& ./maya/inhouse/mlib/_docs/.venv/Scripts/python.exe -m sphinx -E -a -b html -W --keep-going -D language=en maya/inhouse/mlib/_docs .maya-output/mlib-docs/en
```

## 設定と公開

- `conf.py`: Sphinx・AutoAPI・翻訳の設定。
- `_templates/autoapi/python/`: コマンド・クラスの表示。
- `_static/`: 配色と継承図の描画。Mermaidは `conf.py` の固定版とSRIで読み込みます。
- `requirements.txt`: 文書用の依存パッケージ。

`.github/workflows/mlib-docs.yml` が対象変更のmainへのpush時にビルドし、GitHub Pagesへ公開します。
ローカルのビルドだけでは公開版は変わりません。生成HTMLはGitへ登録しません。
