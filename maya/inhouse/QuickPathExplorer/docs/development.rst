開発と配布
==========

構成
----

製品のUI・ファイル操作・設定・Maya連携はC++／Qtです。
Windows版は静的Qtをリンクした単一exe、Maya版はホストのQtへリンクした年別mllです。
製品の横にPython／PySide／``_internal`` を置く必要はありません。
開発用スクリプトとMayaの最小起動用 ``userSetup.py`` ではPythonを使用します。

再ビルド
--------

QPE直下で実行します。Visual Studio、Windows SDK、CMake／Ninja、Python 3.12、Gitが必要です。
同梱の ``.vsconfig`` から必要なC++ツールセットを準備します。
Maya版には対象年のSDK・Qtヘッダーも必要です。

.. code-block:: powershell

   .\check_environment.cmd
   py -3.12 tools/build_static_qt.py --source-archives third_party/sources --jobs 4
   py -3.12 tools/build_native_media.py --source-archives third_party/sources --jobs 4
   .\build_windows.cmd
   .\build_maya.cmd --versions 2022 2027

Windowsのビルドは回帰テスト後に直下exeを更新します。使用中のexeは先に終了してください。
Visual Studioプロジェクトは ``generate_projects.cmd`` で生成できます。
親ワークスペースやmlibへ依存しないビルド入口です。

詳細なツールセット表、短いビルド先の指定、改変Qtへの再リンクは
`BUILDING.md <https://github.com/Hsk0120/MayaHToolsWorkspace/blob/main/maya/inhouse/QuickPathExplorer/BUILDING.md>`_ を参照してください。

ライセンスと配布物
------------------

QPE独自コードは同梱のMITライセンス、Qt・FFmpeg等は各依存物のライセンスが適用されます。
依存物の条件、対応ソース、構成記録は ``third_party`` にあります。
exeだけでなく、対応ソース・ライセンス・再リンク手順も同じ配布先から利用できるようにしてください。
詳細は同梱の ``LICENSE``、``third_party/NOTICES.txt`` とBUILDING.mdを確認してください。

.. code-block:: powershell

   py -3.12 tools/prepare_cpp_relink.py --name product-source

このコマンドはソース付きフォルダーを作ります。ZIPは作りません。
Windows用の静的QtをMayaへ持ち込まず、Maya版を別に構築します。

検証
----

静的QtのC++回帰は、専用一時データを使います。

.. code-block:: powershell

   py -3.12 tools/build_cpp_windows.py --product --test

Maya GUIテストは専用prefs・専用シーンで実行します。
通常作業中のMayaへテストを送信しないでください。
Qtプログラム操作、OS実入力、実プロセス再起動は別の検証です。
`VERIFICATION.md <https://github.com/Hsk0120/MayaHToolsWorkspace/blob/main/maya/inhouse/QuickPathExplorer/VERIFICATION.md>`_ に再実行手順と実機確認項目があります。

このガイドをビルドする
----------------------

この ``docs`` はMaya不要の独立したSphinxプロジェクトです。
Python 3.11以上で依存を導入し、警告をエラーとしてビルドします。

.. code-block:: powershell

   python -m pip install -r docs/requirements.txt
   python -m sphinx -E -a -b html -W --keep-going docs docs/_build/html

GitHub Actionsは同じ設定で生成し、既存GitHub Pagesの ``quick-path-explorer/`` へ公開します。
