開発
====

ソースは ``maya/inhouse/FramePlayer`` にあります。このフォルダーだけで完結し、MayaHTools の共通ライブラリ(hlib など)には依存しません。

ビルド
------

Visual Studio 2022(C++ によるデスクトップ開発)と、それに付属する CMake を使います。

.. code-block:: bat

   cd maya\inhouse\FramePlayer
   cmake -S . -B build -G "Visual Studio 17 2022" -A x64
   cmake --build build --config Release
   rem 配布用の FramePlayer.exe(パッケージの直下)を更新する
   cmake --install build --config Release

* 映像のシェーダー(HLSL)は、Windows SDK の ``fxc.exe`` でビルドのときにバイトコードにして埋め込みます。
* ランタイムを静的にリンクしているので、exe 1つで動きます。

セットアップ
------------

``tools/WinAppKit`` の汎用のインストーラー(WinAppSetup)で作ります。設定は ``installer/FramePlayer.wak.ini`` です。
版は ``src/app/FramePlayer.rc`` の ``FP_VERSION_*`` から読みます。

.. code-block:: bat

   ..\..\..\tools\WinAppKit\build\Release\WinAppSetup.exe --build installer\FramePlayer.wak.ini --out FramePlayerSetup.exe

フォルダーの構成
----------------

.. code-block:: text

   FramePlayer/
   ├ FramePlayer.exe        プレイヤーの本体(配布用)
   ├ FramePlayerSetup.exe   セットアップ(配布用。中に FramePlayer.exe を含む)
   ├ FramePlayer.mod        このフォルダーを Maya のモジュールとして読み込むときの定義
   ├ maya/                  Maya へドラッグ&ドロップする連携のスクリプト
   ├ python/frameplayer/    Maya 側の連携パネルの本体
   ├ docs/                  このドキュメント
   ├ installer/             セットアップの設定
   ├ resources/icon/        アイコン
   ├ src/                   C++ のソース
   └ tests/                 確認用のツール

確認用のツール
--------------

``tests`` のツールで、プレイヤーと同じ読み込みの処理を使って正確さを確かめます(詳しくは FramePlayer の ``README.md``)。

* ``FramePlayerVerify.exe``: 各コマに描いたコマ番号を読み、順・逆・飛び飛びに取り出したコマがずれていないかを確かめます。
* ``FramePlayerColorCheck.exe``: 色のパッチの値を、規格から計算した期待値と比べます(SDR と HDR の画面)。
* ``run_codec_check.py``: Windows のすべてのデコーダー・入れ物の組み合わせをまとめて確かめます。
* ``run_sequence_check.py``・``run_exr_check.py``: 連番画像と OpenEXR の読み込みを確かめます。

ドキュメント
------------

このドキュメントは ``docs`` フォルダーの Sphinx で作ります。日本語が元で、英語版は ``locale/en`` の翻訳から作ります。

.. code-block:: powershell

   cd maya\inhouse\FramePlayer\docs
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   .\rebuild.bat

* 画面の画像は ``docs/tools/capture_docs.py`` で撮り直せます。FramePlayer とセットアップを起動して、その窓だけを撮ります。
* 英訳は、リポジトリの直下で ``python tools/translate_docs.py FramePlayer`` を実行します(ローカルの LLM で、訳の無い文だけを英訳します)。
* GitHub Pages には、main へプッシュすると日本語版と英語版が載ります。
