# hedit ドキュメントのビルド

hedit の利用ガイド・設定項目の説明・開発資料を Sphinx で生成します。
このフォルダーだけで完結します(親リポジトリの hlib ドキュメントには依存しません)。

## 準備

Python 3.11 以上を用意し、この `docs` フォルダーで仮想環境を作ります。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

`.venv/` と `_build/` は Git の対象外です。

## ビルド

```powershell
rebuild.bat
```

警告もエラーとして扱います(`-W`)。成功すると `_build/html/index.html` を開けます。

## 書き方

- 文章は日本語です。設定項目・ショートカットは `preferences.rst`・`shortcuts.rst` に集約しています。
- バージョンは `scripts/hedit/__init__.py` の `__version__` を自動で読みます。
- 機能を追加・変更したときは、該当ページと `changelog.rst` を同時に更新してください。
  設定項目を足す場合は `development.rst` の「設定項目を追加する」の手順に従います。
