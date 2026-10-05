# FramePlayer ドキュメントのビルド

FramePlayer の利用ガイドを Sphinx で生成します。このフォルダーだけで完結します(親リポジトリの hlib・hedit のドキュメントには
依存しません)。見た目は hedit と同じ作りで、色だけを FramePlayer に合わせています(`_static/frameplayer.css`)。

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

## 画面の画像

`_static/images` の画像は `tools/capture_docs.py` で撮ります。FramePlayer とセットアップを起動し、その窓だけを `PrintWindow` で
撮ります(画面全体は撮りません)。撮影の間は FramePlayer の設定を撮影用の値にし、終わったら元に戻します。

```powershell
cd ..
cmake --build build --config Release
python docs\tools\capture_docs.py --ffmpeg C:\path\to\ffmpeg.exe
python docs\tools\capture_docs.py --ffmpeg C:\path\to\ffmpeg.exe --only main,compare
```

見本の動画と連番は ffmpeg で `tools/_media` に作ります(Git の対象外。一度作れば使い回します)。

## 英語版

日本語が元です。英語版は `locale/en/LC_MESSAGES/docs.po` の英訳から作ります。英訳はリポジトリ直下で次を実行します
(ローカルの LLM(Ollama)で、訳の無い文だけを英訳します。GPU のメモリを約 18GB 使うので、Maya を使っていないときに実行します)。

```powershell
python tools/translate_docs.py FramePlayer
```

英語版を手元で作るときは `-D language=en` を付けます。

```powershell
.venv\Scripts\python -m sphinx -E -a -b html -W -D language=en . _build\html\en
```

## 書き方

- 文章は日本語です。画面の文字(ボタン・メニュー)は英語なので、そのままの綴りで書きます。
- バージョンは `src/app/FramePlayer.rc` の `FP_VERSION_TEXT` を自動で読みます。
- 機能を追加・変更したときは、該当ページと `changelog.rst` を同時に更新してください。画面が変わったら画像も撮り直します。
