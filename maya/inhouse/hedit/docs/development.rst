開発ガイド
==========

構成
----

.. code-block:: text

   hedit/
   ├ CMakeLists.txt        C++ プラグインのビルド定義(Maya devkit の pluginEntry.cmake を利用)
   ├ generate_vs.bat       Visual Studio のプロジェクトだけを生成する
   ├ src/                  C++ / Qt のエディター本体
   │  ├ plugin.cpp         プラグインの登録(コマンド hedit)と、Maya 側の処理をエディターへ渡す接続
   │  ├ editor.h/.cpp      画面全体(Window)、コード欄(Code)、出力欄(Output)、行番号(NumberedText)
   │  ├ explorer.h/.cpp    Explorer(フォルダーツリー)
   │  └ spelling.h/.cpp    Windows の辞書を使った英語スペルチェック
   ├ scripts/hedit/        Maya 側の Python
   │  ├ __init__.py        show() / restore() と版(__version__)
   │  ├ docking.py         MayaQWidgetDockableMixin のドックと workspaceControl
   │  ├ bridge.py          コード実行・出力の購読・補完/静的解析の呼び出し・保存先
   │  ├ completion.py      ast による補完の索引(Index)
   │  ├ analysis.py        構文の静的解析
   │  └ startup.py         起動時の自動ロード・Window メニュー・画面の復元
   ├ scripts/userSetup.py  .mod から起動時に startup.initialize() を遅延実行
   ├ release/plug-ins/     ビルド済みの hedit.mll(windows/<Mayaの年>/<版>/)
   ├ tests/                補完・standalone・GUI・復元の自動テスト
   ├ icons/                アイコン
   └ docs/                 このドキュメント

エディターの役割分担
~~~~~~~~~~~~~~~~~~~~

C++ は「画面と入力」を担当し、Maya に触れる処理(コード実行・補完・静的解析・出力の取得・保存先の決定)は、
プラグインが Python 側の関数を **コールバックとして渡します**\ 。エディターは Maya の API を直接呼びません。
そのため、画面の部分を Maya なしで(offscreen で)テストできます。

設定項目を追加する
------------------

Preferences のチェック項目は、\ ``src/editor.cpp`` の Window のコンストラクターで、
``toggle(キー, メニュー表示名, 初期値)`` を 1 行足すと追加できます。

#. ``toggle("myOption", "My option", false);`` を、メニューに並べたい位置(既存の ``toggle`` の並び)へ追加する。
   ``toggle`` が、メニュー項目・保存(``preferences.ini``)・変更時の全タブへの反映(``applyOptions``)を担当します。
#. 動作を実装する場所で ``option("myOption")`` を読む。
#. 即座に反映すべき処理があれば、\ ``toggle`` の切り替え通知の中(キーごとの ``if (key=="...")`` の並び)に足す。
#. 1 タブごとに反映するものは、\ ``applyOptions(Code*)`` に足す。
#. ``docs/preferences.rst`` の一覧表と、項目ごとの節(初期値・何をするか・詳しい動き・オフのとき・注意)を追加する。
#. ``tests/options_smoke.py`` に、切り替えの検証を追加する。

.. note::

   キーは ``preferences.ini`` の保存名になります。一度公開したキーの名前は変えないでください
   (変えると、利用者の保存済みの設定が読み込まれなくなります)。

ビルド
------

Windows で、Visual Studio と Maya の devkit が必要です。親リポジトリ(MayaHToolsWorkspace)では、
``tools/build_maya_plugin.py`` が Visual Studio・CMake・ツールセットを自動検出し、必要な devkit を
インストール済みの Maya から生成します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hedit --versions 2022 2024 2025 2026 2027

* ビルドフォルダーは ``.maya-output/plugin-build/`` の下(Git の対象外)です。
* 出力は ``release/plug-ins/windows/<Mayaの年>/<hedit の版>/hedit.mll`` です。バージョンを上げるときは
  ``scripts/hedit/__init__.py`` の ``__version__`` と、\ ``hedit.mod`` の版・パスを合わせて更新します。
* ロード済みの ``.mll`` は上書きできません。ビルドの前に、該当する Maya を終了してください。

Visual Studio のプロジェクトだけを作る
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hedit --versions 2027 --generate-only

``.maya-output/plugin-build/hedit/<年>/hedit.sln`` を Visual Studio で開き、Release / x64 でビルドします。
または ``generate_vs.bat 2027`` を使います(年を省略すると 2027)。構成の変更は、生成されたプロジェクトではなく
``CMakeLists.txt`` に反映してください。

テスト
------

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_tests.py 2022 2024 2025 2026 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_gui.py 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_session.py 2024 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_startup.py 2024 2027

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - スクリプト
     - 内容
   * - ``run_tests.py``
     - 補完の単体テスト、Maya standalone での ``.mod`` / プラグイン / 補完候補、同じ C++ ウィジェットの offscreen 描画
   * - ``run_gui.py``
     - 専用の空シーン・専用設定の Maya GUI で、表示・ドッキング・実行・出力・補完・検索・ショートカットなどを確認
   * - ``run_session.py``
     - タブと Explorer の復元
   * - ``run_startup.py``
     - 同じ専用設定で 3 回起動し、ドック・Python / MEL 本文の復元と、閉じた場合の非表示を確認

* GUI テストのモジュールディレクトリには hedit の ``.mod`` だけを用意します(ワークスペース全体の外部モジュールは読み込みません)。
  普段の起動バッチ・ユーザー設定・信頼設定は変更しません。
* ログ・画像は ``.maya-output/`` の下に保存します。
* 起動・テストの期限は各 120 秒、終了待ちは 30 秒です。\ ``--timeout`` / ``--shutdown-timeout`` で変更できます。

別リポジトリへ切り出すときに必要なこと
--------------------------------------

hedit は hlib とは独立していますが、現在は親リポジトリ(MayaHToolsWorkspace)の次の資産を利用しています。

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - 依存しているもの
     - 切り出し時の対応
   * - ``tools/build_maya_plugin.py``\ ・\ ``tools/maya_devkit.py``
     - Visual Studio / CMake / devkit の自動検出とローカル devkit の生成。リポジトリへコピーするか、共通のビルド用リポジトリとして分ける
   * - ``tools/run_hlib_gui_versions.py``\ (GUI テストの起動・監視)
     - ``tests/run_gui.py`` などが利用している。専用設定・タイムアウト監視・終了処理ごとコピーが必要
   * - ``maya/modules/hedit.mod``
     - ``../inhouse/hedit`` という相対パスを、リポジトリ構成に合わせて書き換える
   * - ``docs/cpp-documentation.md``\ (C++ コメント規約)
     - 規約のファイルを一緒に移す
   * - 配色の元(hlib の ``code-dark-plus.css``)
     - 色の値は ``editor.cpp`` に直接書かれているため、移動は不要
   * - ``WORK_LOG.md`` などの運用ファイル
     - 移さない(親リポジトリ側の運用)

切り出したあとは、\ ``docs/`` を単独でビルドできます(``docs/README.md``)。
