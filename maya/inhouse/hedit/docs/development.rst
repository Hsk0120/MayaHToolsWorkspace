開発ガイド
==========

構成
----

.. code-block:: text

   hedit/
   ├ CMakeLists.txt          C++ プラグインのビルド定義(Maya devkit の pluginEntry.cmake を利用)
   ├ generate_vs.bat         Visual Studio のプロジェクトだけを生成する
   ├ src/                    C++ / Qt のエディター本体
   │  ├ plugin.cpp           プラグインの登録(コマンド hedit)、出力の購読、Window メニュー、保存先の決定
   │  ├ dock.h/.cpp          workspaceControl へのドッキング、開閉状態(ui.json)の保存と起動時の復元
   │  ├ editor.h/.cpp        画面全体(Window)、コード欄(Code)、出力欄(Output)、行番号(NumberedText)
   │  ├ explorer.h/.cpp      Explorer(フォルダーツリー)
   │  ├ spelling.h/.cpp      Windows の辞書を使った英語スペルチェック
   │  ├ modulescan.h/.cpp    import の行のトップレベル名の補完と、sys.path の別スレッド走査
   │  ├ embedded_python.h    補完・構文チェック用の Python を文字列として同梱し、import フックで配る
   │  ├ mayautil.h           C++ から MEL を実行する補助(mel / melInt / melBool / melQuote)
   │  └ version.h            版(HEDIT_VERSION)
   ├ scripts/userSetup.py    起動時に cmds.loadPlugin('hedit') を1回呼ぶだけの最小ブートストラップ
   ├ release/plug-ins/       ビルド済みの hedit.mll(windows/<Mayaの年>/<版>/)
   ├ tests/                  補完・standalone・GUI・復元の自動テスト(hedit_host.py は GUI テスト用の補助)
   ├ icons/                  アイコンの元データ(実行時は plugin.cpp に同梱した SVG を使う)
   └ docs/                   このドキュメント

C++ と Python の分担
~~~~~~~~~~~~~~~~~~~~

hedit は ``hedit.mll`` だけで動きます。\ ``.py`` ファイルは ``scripts/userSetup.py``\ (起動時に
``cmds.loadPlugin('hedit')`` を呼ぶだけ)しかありません。Maya の UI・ファイル・状態を扱う処理は C++ で、
Python 言語そのものの解析が必要な処理だけを、Maya 同梱の Python で行います。

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 処理
     - 実装
   * - Window メニューの項目追加・削除
     - ``plugin.cpp`` の ``installMenu`` / ``uninstallMenu``\ 。\ ``MGlobal::executeCommand`` で MEL を実行する。
       メインメニューがあれば同期的に登録し、起動初期でまだ無い場合だけ ``evalDeferred -lowestPriority`` に回す。
       項目のコマンドは MEL の ``hedit -show``\ 。
   * - メニューの緑の H アイコン
     - ``plugin.cpp`` の ``kMenuIconSvg`` に SVG を同梱。\ ``menuItem -image`` はファイルパスしか受け付けないため、
       ロード時に ``<userPrefDir>/hedit/hedit.svg`` へ書き出して使う(内容が同じなら書き直さない)。
   * - ドッキング・再表示
     - ``dock.cpp`` の ``show``\ 。MEL の ``workspaceControl`` を作り、\ ``MQtUtil::addWidgetToMayaLayout`` で
       編集画面(QMainWindow)を直接入れる。uiScript は MEL の ``hedit -restore``\ 。
   * - 開閉状態の保存(ui.json)
     - ``dock.cpp`` の ``record``\ (表示中は 1 秒ごと)。閉じる操作は ``closeCommand`` の ``hedit -closed``\ 、
       Maya の終了は ``quitApplication`` の scriptJob(``hedit -quitting``)で受け取る。
   * - 前回画面の復元
     - ``dock.cpp`` の ``restorePrevious``\ (ロード後の次のイベントループ)。保存済みの空の workspaceControl が
       残っている場合は、表示するだけにして Maya 自身の uiScript に中身を作らせる。
   * - 起動時の出力履歴・出力の購読
     - ``plugin.cpp`` の ``outputHistory`` / ``createOutputReporter``\ 。非表示の ``cmdScrollFieldReporter`` を MEL で作り、
       ``MQtUtil::findControl`` で表示文書を購読する。履歴の整形は ``editor.cpp`` の ``compactHistory``\ 。
   * - タブ復元先の決定
     - ``plugin.cpp`` の ``sessionPath``\ (``hedit -sessionPath`` でも取得できる)。旧名 ``heditor`` からのコピーもここで行う。
   * - Maya 終了時の出力転送の停止
     - ``plugin.cpp`` の ``onMayaExiting``\ (``kMayaExiting``)。終了処理中の reporter 追記を hedit 画面へ描画しない。
   * - ``import xxx`` / ``from xxx`` のトップレベル名の補完
     - ``modulescan.cpp`` の ``ModuleScanner``\ 。\ ``sys.path`` の各フォルダーを C++ のスレッド(GIL 不要)で走査する。
       編集画面の作成時に走査を始め、初回は最大 0.5 秒待つ。以後の再走査は 5 秒間隔で裏で行う。
       Python からは ``sys.path`` と組み込み・読み込み済みの名前(``hedit.bridge.module_names``)だけを受け取る。
       Maya に依存しないため ``tests/ui_smoke.cpp`` で検証する。
   * - それ以外の補完(Python)
     - ``embedded_python.h`` の ``hedit.completion`` / ``hedit.bridge``\ 。読み込み済みモジュールの
       公開名と、未読込のソースの ``ast`` 解析から候補を作る。
   * - 構文チェック(Python)
     - ``embedded_python.h`` の ``hedit.analysis``\ 。\ ``compile()`` だけを使い、コードは実行しない。
   * - ``import hedit``\ (Python)
     - ``hedit.show()`` / ``hedit.restore()`` は C++ の ``hedit`` コマンドを呼ぶだけの互換用の窓口。
       旧版で保存されたワークスペースの uiScript(``import hedit; hedit.restore()``)もここから C++ へ渡る。

``hedit`` コマンドのフラグ
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - フラグ
     - 動作
   * - (なし)
     - 編集画面を(未作成なら作って)そのアドレスを返す。GUI テストが PySide から画面を参照するときに使う。
   * - ``-show``\ (``-sh``)と ``-floating``\ (``-f``)
     - 画面を開く。開いていれば一度閉じて(タブを保存して)開き直す。\ ``-floating`` を付けたときだけ浮動状態を変える。
   * - ``-restore``\ (``-r``)
     - workspaceControl の uiScript から呼ぶ。前回閉じていた場合は中身を作らず非表示に保つ。
   * - ``-saveState``\ (``-ss``)
     - 開閉状態をすぐに ui.json へ保存する。
   * - ``-sessionPath``\ (``-sp``)
     - タブ復元先(tabs.json)のパスを返す。画面を作らないため mayapy でも使える。
   * - ``-closed``\ (``-cl``)・\ ``-quitting``\ (``-qt``)
     - 内部用。ドックの ``closeCommand`` と終了通知の scriptJob から呼ばれる。

同梱の Python について
~~~~~~~~~~~~~~~~~~~~~~

``initializePlugin`` が ``hedit::embedded::installModules()`` で ``sys.meta_path`` の先頭へ import フックを登録し、
``import hedit`` などは通常の ``.py`` と同じく import した時点で同梱ソースから読み込まれます
(バッチ/mayapy でも登録するため、補完などの Python API は standalone でも使えます)。

* フックを ``sys.meta_path`` の先頭に置くのは、\ ``PYTHONPATH`` 上に同名のフォルダー(旧版の ``__pycache__``
  だけが残った ``scripts/hedit`` など)があっても、空の名前空間パッケージとして先に解決させないためです。
  そうした同梱以外で読まれた ``hedit`` 系のモジュールは、ロード時に取り除きます。
* プラグインをアンロードしてロードし直しても、同梱から読み込み済みのモジュールは残します(補完のキャッシュを保つため)。
  新しいソースを反映するには Maya を再起動してください(対応する ``.py`` が無いため ``reload()`` では更新できません)。
* MSVC の制約で、生文字列リテラルの区切り子は 16 文字以内、1 つのリテラルは約 16KB 以内に保ってください。

C++ から MEL を呼ぶときの注意
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``MGlobal::executeCommandStringResult`` は、整数・真偽値を返すコマンド(``-exists`` / ``-q -visible`` など)では
  失敗して空を返します。\ ``mayautil.h`` の ``melInt`` / ``melBool`` を使ってください。
* ``MQtUtil::addWidgetToMayaLayout`` の戻り値の型は Maya の版で異なります。取り付けたかは Qt の親子関係で確かめます。
* 遅延実行(``QTimer::singleShot`` など)やシグナルに渡す C++ のラムダは ``hedit.mll`` の中にあります。実行前に
  プラグインがアンロードされると解放済みのコードを呼んで Maya が落ちるため、\ ``dock::lifetime()`` などプラグインと
  同じ寿命のオブジェクトを文脈に渡し、解除時に取り消されるようにしてください。

エディターの役割分担
~~~~~~~~~~~~~~~~~~~~

``editor.cpp`` は「画面と入力」を担当し、Maya に触れる処理(コード実行・補完・静的解析・出力の取得・保存先の決定)は、
``plugin.cpp`` が関数を **コールバックとして渡します**\ 。エディターは Maya の API を直接呼びません。
そのため、画面の部分を Maya なしで(offscreen で)テストできます(``tests/ui_smoke.cpp``)。

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

#. ``src/embedded_python.h`` の ``kInitSource`` 内の ``__version__``\ (Python の ``hedit.__version__``)
#. ``src/version.h`` の ``HEDIT_VERSION``\ (プラグインの版とドックのタイトル)
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
       プラグインのロード/アンロード・実在する補完候補(``maya_smoke.py``)、保存先の決定(``test_rename.py``)、
       同じ C++ ウィジェットの offscreen 描画と、Maya 非依存の C++ 部分(履歴の整形・import の行の補完・
       ``sys.path`` の走査)のテスト(``hedit_ui_smoke.exe``)を実行する
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
* ドッキングと開閉状態は C++ にあるため、GUI テストは ``tests/hedit_host.py`` を通して、編集画面(``editor()``)・
  ドック(``control()`` / ``docked_editor()``)・ui.json(``state_path()`` / ``save_state()``)を参照します。
  PySide で編集画面を ``QMainWindow`` 型として取り出すと、Maya が破棄した別のウィンドウとアドレスが重なったときに
  「削除済み」のラッパーが返ることがあります。補助は ``QApplication.allWidgets()`` から取り直して避けています。
* GUI テストのランナーは全ての ``userSetup`` を抑止します。そのため、起動時の入口
  (``scripts/userSetup.py`` と同じ ``loadPlugin``)は各テストが明示的に実行します。
* GUI テストのモジュールディレクトリには hedit の ``.mod`` だけを用意します(ワークスペース全体の外部モジュールは読み込みません)。
  普段の起動バッチ・ユーザー設定・信頼設定は変更しません。
* ログ・画像は ``.maya-output/`` の下に保存します。
* 期限: ``run_gui.py`` は起動・テストが 120 秒、終了待ちが 30 秒(``--timeout`` / ``--shutdown-timeout`` で変更可)。
  ``run_startup.py`` / ``run_session.py`` は 120 秒 / 60 秒の固定です。
* テスト用の Maya はデスクトップの前面にいないことがあります。Windows は前面でないアプリのポップアップ(補完の候補一覧)を
  すぐ閉じ、また ``activateWindow()`` による前面化は非同期です。補完の候補一覧を確かめる GUI テストは、前面化を待ってから
  Ctrl+Space を送り、表示されるまでやり直してください(``completion_output_smoke.py`` の ``show_popup``)。候補の中身だけを
  確かめる場合は、ポップアップの表示有無に左右されない ``completionModel()`` を見ます。
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
