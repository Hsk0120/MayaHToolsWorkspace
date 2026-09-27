開発ガイド
==========

構成
----

.. code-block:: text

   hedit/
   ├ CMakeLists.txt          C++ プラグインのビルド定義(Maya devkit の pluginEntry.cmake を利用)
   ├ generate_vs.bat         Visual Studio のプロジェクトだけを生成する
   ├ src/                    C++ / Qt のエディター本体
   │  ├ plugin.cpp           プラグインの登録(コマンド hedit)、埋め込みPythonの展開、Maya 側処理の接続
   │  ├ embedded_python.h    旧 scripts/hedit/*.py 相当をC++文字列として同梱するブートストラップ
   │  ├ editor.h/.cpp        画面全体(Window)、コード欄(Code)、出力欄(Output)、行番号(NumberedText)
   │  ├ explorer.h/.cpp      Explorer(フォルダーツリー)
   │  └ spelling.h/.cpp      Windows の辞書を使った英語スペルチェック
   ├ scripts/userSetup.py    起動時に cmds.loadPlugin('hedit') を1回呼ぶだけの最小ブートストラップ
   ├ release/plug-ins/       ビルド済みの hedit.mll(windows/<Mayaの年>/<版>/)
   ├ tests/                  補完・standalone・GUI・復元の自動テスト
   ├ icons/                  アイコンの元データ(実行時は plugin.cpp に同梱した SVG を使う)
   └ docs/                   このドキュメント

hedit 本体の Python は hedit.mll に同梱する
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

旧版にあった ``scripts/hedit/__init__.py`` / ``docking.py`` / ``bridge.py`` / ``completion.py`` /
``analysis.py`` / ``startup.py`` は、内容をそのまま ``src/embedded_python.h`` の生文字列リテラルへ移しました。
``initializePlugin``\ (``plugin.cpp``)が ``hedit::embedded::installModules()`` で ``sys.meta_path`` の
先頭へ import フックを登録し、``import hedit`` や ``from . import docking`` は通常の ``.py`` と同じく
import した時点で同梱ソースから読み込まれます(バッチ/mayapy でも登録するため、補完などの
Python API は standalone でも使えます)。ディスク上にこれらの ``.py`` ファイルは存在しません。
**Plug-in Manager での明示ロードだけでも、復元・Window メニュー登録まで含めて完結します。**

* フックを ``sys.meta_path`` の先頭に置くのは、``PYTHONPATH`` 上に同名のフォルダー(旧版の ``__pycache__``
  だけが残った ``scripts/hedit`` など)があっても、空の名前空間パッケージとして先に解決させないためです。
  そうした同梱以外で読まれた ``hedit`` 系のモジュールは、ロード時に取り除きます。
* プラグインをアンロードしてロードし直しても、同梱から読み込み済みのモジュールは残します
  (旧版の ``.py`` と同じく、ドックのホストやタイマーなどの状態を失わないため)。
  新しいソースを反映するには Maya を再起動してください。

ロード時の処理の分担は次のとおりです。

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 処理
     - 実装
   * - Window メニューの項目追加・削除
     - ``plugin.cpp`` の ``installMenu`` / ``uninstallMenu``。Python を介さず ``MGlobal::executeCommand`` で MEL を実行する。
       メインメニューがあれば同期的に登録し、起動初期でまだ無い場合だけ ``evalDeferred -lowestPriority`` に回す。
   * - メニューの緑の H アイコン
     - ``plugin.cpp`` の ``kMenuIconSvg`` に SVG を同梱。``menuItem -image`` はファイルパスしか受け付けないため、
       ロード時に ``<userPrefDir>/hedit/hedit.svg`` へ書き出して使う(内容が同じなら書き直さない)。
   * - 前回画面の復元
     - ``hedit.startup.plugin_loaded()``\ (PySide の ``MayaQWidgetDockableMixin`` が必要なため Python)。
       保存済みの空の workspaceControl が残っている場合は、表示するだけにして Maya 自身の ``uiScript``
       (``hedit.restore()``)に中身を作らせる。
   * - Maya 終了時の出力転送の停止
     - ``plugin.cpp`` の ``onMayaExiting``\ (``kMayaExiting``)。終了処理中の reporter 追記を hedit 画面へ描画しない。

.. note::

   MSVC の制約で、生文字列リテラルの区切り子は16文字以内、1つのリテラルは約16KB以内に保ってください。

``scripts/userSetup.py`` だけは残しています。Maya 起動時に(ユーザーが毎回 Plug-in Manager を
開かなくても)自動で ``hedit`` がロードされるようにするための入口で、行うのは
``cmds.loadPlugin('hedit')`` の呼び出しだけです。復元・メニュー登録などの実処理は一切含みません。
``.mod`` は ``MAYA_PLUG_IN_PATH`` に加え、この ``userSetup.py`` を見つけるための
``PYTHONPATH +:= scripts`` を設定します。

Python 自体を廃止したわけではありません。補完(``ast``)や構文チェック(``compile()``)は
Python 言語の解析そのものが必要なため、Maya に同梱された CPython を
``MGlobal::executePythonCommand`` 経由で呼び出す構成を維持しています。変更したのは
「hedit 本体のロジックが ``.py`` ファイルに依存しない」点であり、実行時に Python を
使わなくしたわけではありません。

``embedded_python.h`` 内のソースを編集した場合、対応する ``.py`` は存在しないため
``hlib`` のような ``reload()`` は使えません。編集後は Maya を再起動してビルド済み
``.mll`` を読み込み直してください。

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
* 出力は ``release/plug-ins/windows/<Mayaの年>/<hedit の版>/hedit.mll`` です。
* ロード済みの ``.mll`` は上書きできません。ビルドの前に、該当する Maya を終了してください。
* ``src/embedded_python.h`` の Python ソースも ``.mll`` に含まれるため、Python 部分だけを直した場合も再ビルドが必要です。

版を上げるときは、次の箇所をそろえて更新します(このドキュメントの版は 1 の値を自動で読みます)。

#. ``src/embedded_python.h`` の ``kInitSource`` 内の ``__version__``\ (ドックのタイトルにも表示)
#. ``src/plugin.cpp`` の ``MFnPlugin plugin(object, "hedit", "<版>", "Any")``
#. ``CMakeLists.txt`` の出力先 ``release/plug-ins/windows/${MAYA_VERSION}/<版>`` と PDB の出力先
#. 親リポジトリの ``maya/modules/hedit.mod`` の各バージョンの版と ``MAYA_PLUG_IN_PATH``
#. ``docs/changelog.rst``

Visual Studio のプロジェクトだけを作る
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hedit --versions 2027 --generate-only

``.maya-output/plugin-build/hedit/<年>/hedit.sln`` を Visual Studio で開き、Release / x64 でビルドします。
または ``generate_vs.bat 2027`` を使います(年を省略すると 2027)。構成の変更は、生成されたプロジェクトではなく
``CMakeLists.txt`` に反映してください。

テスト
------

リポジトリ直下から実行します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_tests.py 2022 2024 2025 2026 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_startup.py 2022 2024 2025 2026 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_gui.py 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_session.py 2024 2027

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - スクリプト
     - 内容
   * - ``run_tests.py``
     - 版ごとに、補完・静的解析の単体テスト(``test_completion.py``)、Maya standalone での ``.mod`` の解決・
       プラグインのロード/アンロード・実在する補完候補(``maya_smoke.py``)、同じ C++ ウィジェットの offscreen 描画
       (``hedit_ui_smoke.exe``)を実行する
   * - ``run_startup.py``
     - 同じ専用設定で 3 回起動する(``startup_smoke.py``)。プラグインのロードだけで Window メニューの項目と
       アイコンが追加されること、メニューのコマンドで開けること、右ドック・Python / MEL 本文の復元、
       閉じた場合に再表示しないこと、アンロードでメニュー項目が消えることを確認
   * - ``run_gui.py``
     - 専用の空シーン・専用設定の Maya GUI で、``userSetup.py`` による自動ロード、表示・ドッキング・実行・出力・補完・
       検索・ショートカットなどを確認(``--suite`` で ``gui_smoke.py`` / ``completion_output_smoke.py`` /
       ``formatting_spelling_smoke.py`` / ``output_format_smoke.py`` を選ぶ。既定は ``gui_smoke.py``)
   * - ``run_session.py``
     - 2 回起動し、未保存タブの自動保存と、次の起動での本文・パス・選択位置・未保存状態の復元を確認(``session_smoke.py``)
   * - ``test_rename.py``
     - 旧名 ``heditor`` の保存先からのコピーを確認。mayapy で単体実行する(``MAYA_MODULE_PATH`` に ``maya/modules`` が必要)

* ``hedit`` の Python は ``hedit.mll`` に同梱されているため、テストは ``import hedit`` の前に
  ``cmds.loadPlugin('hedit')`` を行います(``.mod`` の ``MAYA_PLUG_IN_PATH`` からプラグイン名で解決)。
* GUI テストのランナーは全ての ``userSetup`` を抑止します。そのため、起動時の入口
  (``scripts/userSetup.py`` と同じ ``loadPlugin``)は各テストが明示的に実行します。
* GUI テストのモジュールディレクトリには hedit の ``.mod`` だけを用意します(ワークスペース全体の外部モジュールは読み込みません)。
  普段の起動バッチ・ユーザー設定・信頼設定は変更しません。
* ログ・画像は ``.maya-output/`` の下に保存します。
* 期限: ``run_gui.py`` は起動・テストが 120 秒、終了待ちが 30 秒(``--timeout`` / ``--shutdown-timeout`` で変更可)。
  ``run_startup.py`` / ``run_session.py`` は 120 秒 / 60 秒の固定です。
* Maya 2024 は起動直後に Arnold(mtoa)の遅延登録が GUI スレッドを約 5 秒止めます。GUI テストで待機する場合は、
  壁時計ではなくイベントループが回った回数で数えてください(``session_smoke.py`` 参照)。

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
