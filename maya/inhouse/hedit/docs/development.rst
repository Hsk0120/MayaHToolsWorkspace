開発ガイド
==========

構成
----

.. code-block:: text

   hedit/
   ├ CMakeLists.txt          C++ プラグインのビルド定義(Maya devkit の pluginEntry.cmake を利用)
   ├ cmake/embed_python.cmake  src/python/ の .py を C++ の配列へ変換する(ビルド時に自動実行)
   ├ generate_vs.bat         Visual Studio のプロジェクトだけを生成する
   ├ src/
   │  ├ version.h            版(HEDIT_VERSION)。版の定義はここだけ
   │  ├ core/                Maya にも画面にも依存しない処理(Maya 無しでテストできる)
   │  │  ├ output_message.h   出力 1 件の型(OutputKind / OutputMessage)
   │  │  ├ history_text.*     起動前の出力履歴の整形と、行の種類の判定
   │  │  ├ module_scanner.*   import の行のトップレベル名の補完と、sys.path の別スレッド走査
   │  │  ├ text_search.*      検索・置換の一致箇所の計算と、$1 などの展開
   │  │  └ session_data.*     未保存タブの復元ファイル(tabs.json)の形と JSON との変換
   │  ├ editor/              Qt の編集画面(Maya に依存しない)
   │  │  ├ editor.h/.cpp      画面の入口。EditorServices(Maya 側の処理の一式)と createEditor
   │  │  ├ main_window.*      画面全体。部品の組み立て・メニュー・タブ・保存と復元
   │  │  ├ code_editor.*      1 タブのコード欄(キー操作・自動インデント・補完の一覧・スペルの波線)
   │  │  ├ edit_commands.*    VS Code 風の行編集(コメント・インデント・行の移動や複製)
   │  │  ├ numbered_text_edit.*  行番号付きのテキスト欄(コード欄と出力欄の土台)
   │  │  ├ output_panel.*     出力欄(保持・表示モードでの絞り込み・色付け)
   │  │  ├ find_bar.*         検索・置換バー
   │  │  ├ problems_panel.*   構文チェックの結果の一覧
   │  │  ├ syntax_highlighter.*  Python / MEL の色分け
   │  │  ├ editor_tabs.*      ホイールで移動できるタブ欄
   │  │  ├ editor_preferences.*  Preferences の設定の表と preferences.ini への保存
   │  │  ├ session_store.*    tabs.json の読み書きとロック
   │  │  ├ explorer.*         Explorer(フォルダーツリー)
   │  │  ├ spelling.*         Windows の辞書を使った英語スペルチェック
   │  │  ├ ui_scale.*         画面の拡大率(4K など)とアイコンの取り出し方
   │  │  └ theme.h            配色(Dark+)。色はここだけで定義する
   │  ├ plugin/              Maya API を使う部分
   │  │  ├ plugin.cpp         プラグインの入口(initializePlugin / uninitializePlugin)
   │  │  ├ hedit_command.*    Maya コマンド hedit とフラグ
   │  │  ├ editor_host.*      編集画面を 1 つだけ作り、Maya の処理(実行・補完・出力)とつなぐ
   │  │  ├ output_capture.*   Maya の出力の購読と、画面へ渡すまでのキュー
   │  │  ├ python_bridge.*    Maya 内の Python / MEL の呼出し(実行・補完・構文チェック)
   │  │  ├ dock.*             workspaceControl へのドッキング、開閉状態(ui.json)の保存と起動時の復元
   │  │  ├ window_menu.*      Window メニューの項目とアイコン
   │  │  ├ user_paths.*       hedit のファイルを置く場所(tabs.json など)と旧名 heditor からのコピー
   │  │  ├ embedded_python.*  同梱の Python を配る import フックの登録
   │  │  └ mel.h              C++ から MEL を実行する補助(mel / melInt / melBool / melQuote)
   │  └ python/              hedit.mll に同梱する Python(普通の .py として編集する)
   │     ├ hedit/__init__.py   show() / restore()(C++ の hedit コマンドを呼ぶ互換用の窓口)
   │     ├ hedit/completion.py 補完の索引(ast で読むだけで、対象のコードは実行しない)
   │     ├ hedit/bridge.py     C++ から呼ばれる補完の窓口
   │     ├ hedit/analysis.py   構文チェック(compile だけ)
   │     └ heditor/__init__.py 旧名 heditor の uiScript 互換
   ├ scripts/userSetup.py    起動時に cmds.loadPlugin('hedit') を1回呼ぶだけの最小ブートストラップ
   ├ release/plug-ins/       ビルド済みの hedit.mll(windows/<Mayaの年>/<版>/)
   ├ tests/                  補完・standalone・GUI・復元の自動テスト(hedit_host.py は GUI テスト用の補助)
   ├ icons/                  アイコンの元データ(実行時は window_menu.cpp に同梱した SVG を使う)
   └ docs/                   このドキュメント

依存の向きは ``plugin/`` → ``editor/`` → ``core/`` の一方向です。\ ``editor/`` と ``core/`` は Maya のヘッダーを
読みません。そのため ``tests/ui_smoke.cpp``\ (``hedit_ui_smoke.exe``)が、本番と同じ ``editor/`` と ``core/`` の
ソースを Maya 無しでそのまま検証できます。

コードを読む順番
~~~~~~~~~~~~~~~~

C++ に慣れていない場合は、次の順に読むと全体がつかめます。

#. ``src/plugin/plugin.cpp``\ : Maya がプラグインをロード・アンロードしたときに何が起きるか。
#. ``src/plugin/hedit_command.cpp``\ : ``hedit -show`` などのコマンドが、どの関数を呼ぶか。
#. ``src/plugin/editor_host.cpp``\ : 画面を作るときに、Maya の処理を ``EditorServices`` に詰めて渡すところ。
#. ``src/editor/editor.h``\ : 画面が Maya に求める処理の一覧(``EditorServices``)。
#. ``src/editor/main_window.h`` → ``.cpp``\ : 画面の部品の配置図(ヘッダーのコメント)と、メニュー・タブの処理。
#. 興味のある部品(``code_editor``\ ・\ ``output_panel``\ ・\ ``find_bar`` など)。

書き方の約束
~~~~~~~~~~~~

* 1 行に 1 つの文を書きます。\ ``if`` の本体も ``{ }`` で囲みます(キーと操作の対応表のような短い表は例外)。
* クラスのメンバー変数は、名前の最後に ``_`` を付けます(例: ``tabs_``)。ローカル変数と見分けるためです。
* 色は ``editor/theme.h``\ 、拡大率は ``scaled()``\ 、版は ``version.h`` のように、同じ値は 1 か所で定義します。
* Qt の部品は親(レイアウトやタブ欄を含む)に所有させ、\ ``delete`` はなるべく書きません。
  タブ欄から外した部品のように、自分で ``delete`` するところにはコメントで理由を書きます。
* コメントは日本語の Doxygen 形式です(親リポジトリの ``docs/cpp-documentation.md``)。

C++ と Python の分担
~~~~~~~~~~~~~~~~~~~~

hedit は ``hedit.mll`` だけで動きます。ディスク上の ``.py`` ファイルは ``scripts/userSetup.py``\ (起動時に
``cmds.loadPlugin('hedit')`` を呼ぶだけ)しかありません。Maya の UI・ファイル・状態を扱う処理は C++ で、
Python 言語そのものの解析が必要な処理だけを、Maya 同梱の Python で行います。

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 処理
     - 実装
   * - Window メニューの項目追加・削除
     - ``plugin/window_menu.cpp`` の ``installWindowMenu`` / ``uninstallWindowMenu``\ 。\ ``MGlobal::executeCommand`` で MEL を実行する。
       メインメニューがあれば同期的に登録し、起動初期でまだ無い場合だけ ``evalDeferred -lowestPriority`` に回す。
       項目のコマンドは MEL の ``hedit -show``\ 。
   * - メニューの緑の H アイコン
     - ``plugin/window_menu.cpp`` の ``kMenuIconSvg`` に SVG を同梱。\ ``menuItem -image`` はファイルパスしか受け付けないため、
       ロード時に ``<userPrefDir>/hedit/hedit.svg`` へ書き出して使う(内容が同じなら書き直さない)。
   * - ドッキング・再表示
     - ``plugin/dock.cpp`` の ``show``\ 。MEL の ``workspaceControl`` を作り、\ ``MQtUtil::addWidgetToMayaLayout`` で
       編集画面(QMainWindow)を直接入れる。uiScript は ``kUiScript``\ (未ロードなら ``loadPlugin hedit`` してから
       ``hedit -restore``)。保存済みの workspaceControl がある場合は **先に表示してから** 中身を作る
       (表示で Maya が uiScript を実行し、先に入れた画面を作り直して壊すのを避ける)。
   * - 開閉状態の保存(ui.json)
     - ``plugin/dock.cpp`` の ``saveState``\ (表示中は 1 秒ごと)。閉じる操作は ``closeCommand``\ (``kCloseCommand``)の
       ``hedit -closed``\ 。プラグインがロードされているときだけ呼ぶ(未ロードのまま Maya が保存済みの
       浮動ドックを閉じても ``Cannot find procedure "hedit"`` を出さないため)。
       Maya の終了は ``quitApplication`` の scriptJob(``hedit -quitting``)で受け取る。
   * - 前回画面の復元
     - ``plugin/dock.cpp`` の ``restorePrevious``\ (ロード後の次のイベントループ)。保存済みの空の workspaceControl が
       残っている場合は、表示するだけにして Maya 自身の uiScript に中身を作らせる。
   * - 画面の大きさ(4K など)
     - ``editor/ui_scale.cpp`` の ``setUiScale`` / ``scaled`` / ``setIconProvider``\ 。\ ``plugin/editor_host.cpp`` が画面の作成前に
       ``MQtUtil::dpiScale(1.0f)`` を ``setUiScale`` へ渡し、文字の px・余白・幅・アイコンの大きさはすべて
       ``scaled(100% のときの px)`` で決める(Maya は Qt の高 DPI 拡大を止めて自前で拡大するため)。
       アイコンは ``MQtUtil::createIcon`` で拡大率に合った画像を受け取る(``QIcon(":/name.png")`` は常に 20 px)。
       Zoom の文字サイズは 100% 基準で保存する。Maya 無しの ``tests/ui_smoke.cpp`` では 2 倍を与えて検証する。
   * - 起動時の出力履歴・出力の購読
     - ``plugin/output_capture.cpp`` の ``OutputCapture``\ 。非表示の ``cmdScrollFieldReporter`` を MEL で作り、
       ``MQtUtil::findControl`` で表示文書を購読する。履歴の整形は ``core/history_text.cpp`` の ``compactHistory``\ 。
   * - タブ復元先の決定
     - ``plugin/user_paths.cpp`` の ``sessionFilePath``\ (``hedit -sessionPath`` でも取得できる)。旧名 ``heditor`` からのコピーもここで行う。
   * - Maya 終了時の出力転送の停止
     - ``plugin/plugin.cpp`` の ``onMayaExiting``\ (``kMayaExiting``)→ ``OutputCapture::stopForExit``\ 。
       終了処理中の reporter 追記を hedit 画面へ描画しない。
   * - ``import xxx`` / ``from xxx`` のトップレベル名の補完
     - ``core/module_scanner.cpp`` の ``ModuleScanner``\ 。\ ``sys.path`` の各フォルダーを C++ のスレッド(GIL 不要)で走査する。
       編集画面の作成時に走査を始め、初回は最大 0.5 秒待つ。以後の再走査は 5 秒間隔で裏で行う。
       Python からは ``sys.path`` と組み込み・読み込み済みの名前(``hedit.bridge.module_names``)だけを受け取る
       (``plugin/python_bridge.cpp``)。Maya に依存しないため ``tests/ui_smoke.cpp`` で検証する。
   * - それ以外の補完(Python)
     - ``src/python/hedit/completion.py`` / ``bridge.py``\ 。読み込み済みモジュールの
       公開名と、未読込のソースの ``ast`` 解析から候補を作る。
   * - 構文チェック(Python)
     - ``src/python/hedit/analysis.py``\ 。\ ``compile()`` だけを使い、コードは実行しない。
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

Python のソースは ``src/python/`` に普通の ``.py`` として置きます。ビルドのたびに ``cmake/embed_python.cmake`` が
それを C++ の配列(ビルドフォルダーの ``generated/embedded_python_sources.h``\ 、Git の対象外)に変換し、
``hedit.mll`` に入れます。モジュール名はフォルダー構成から決まります(``hedit/bridge.py`` → ``hedit.bridge``\ 、
``__init__.py`` はパッケージ)。

``initializePlugin`` が ``hedit::embedded::installModules()``\ (``plugin/embedded_python.cpp``)で ``sys.meta_path`` の先頭へ
import フックを登録し、\ ``import hedit`` などは通常の ``.py`` と同じく import した時点で同梱ソースから読み込まれます
(バッチ/mayapy でも登録するため、補完などの Python API は standalone でも使えます)。

* ``hedit.__version__`` は、ロード時に ``src/version.h`` の値が設定されます(``__init__.py`` には書きません)。
* フックを ``sys.meta_path`` の先頭に置くのは、\ ``PYTHONPATH`` 上に同名のフォルダー(旧版の ``__pycache__``
  だけが残った ``scripts/hedit`` など)があっても、空の名前空間パッケージとして先に解決させないためです。
  そうした同梱以外で読まれた ``hedit`` 系のモジュールは、ロード時に取り除きます。
* プラグインをアンロードしてロードし直しても、同梱から読み込み済みのモジュールは残します(補完のキャッシュを保つため)。
  新しいソースを反映するには Maya を再起動してください(ディスク上の ``.py`` を読むわけではないため ``reload()`` では更新できません)。

C++ から MEL を呼ぶときの注意
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``MGlobal::executeCommandStringResult`` は、整数・真偽値を返すコマンド(``-exists`` / ``-q -visible`` など)では
  失敗して空を返します。\ ``plugin/mel.h`` の ``melInt`` / ``melBool`` を使ってください。
* ``MQtUtil::addWidgetToMayaLayout`` の戻り値の型は Maya の版で異なります。取り付けたかは Qt の親子関係で確かめます。
* 遅延実行(``QTimer::singleShot`` など)やシグナルに渡す C++ のラムダは ``hedit.mll`` の中にあります。実行前に
  プラグインがアンロードされると解放済みのコードを呼んで Maya が落ちるため、\ ``dock::lifetime()`` などプラグインと
  同じ寿命のオブジェクトを文脈に渡し、解除時に取り消されるようにしてください。
* ``plugin/dock.cpp`` の手順の順番には、Maya の版ごとの落ちる不具合を避けるための理由があります。
  コメントの理由を確かめずに順番を入れ替えないでください(変えた場合は ``tests/run_startup.py`` で確かめます)。

エディターの役割分担
~~~~~~~~~~~~~~~~~~~~

``editor/`` は「画面と入力」を担当し、Maya に触れる処理(コード実行・補完・静的解析・出力の取得)は、
``plugin/editor_host.cpp`` が ``EditorServices`` に **関数として詰めて渡します**\ 。エディターは Maya の API を直接呼びません。
そのため、画面の部分を Maya なしで(offscreen で)テストできます(``tests/ui_smoke.cpp``)。

テストや PySide から参照される名前(``objectName`` とアクションの表示名)は、GUI テストが画面を探すのに使っています。
変える場合は ``tests/`` も合わせて直してください。主なもの: ``hedit``\ ・\ ``codeEditor``\ ・\ ``output``\ ・\ ``outputPanel``\ ・
``outputMode``\ ・\ ``editorSplitter``\ ・\ ``scriptToolbar``\ ・\ ``findBar``\ ・\ ``findText``\ ・\ ``replaceText``\ ・\ ``searchCase``\ ・
``searchWord``\ ・\ ``searchRegex``\ ・\ ``searchCount``\ ・\ ``replaceAll``\ ・\ ``analysisProblems``\ ・\ ``languageMode``\ ・
``explorerDock``\ ・\ ``explorerTree``\ ・\ ``toggleExplorer``\ ・\ ``option_<設定名>``\ ・\ ``lineJump``\ 。
コード欄の動的プロパティ ``language``\ ・\ ``path``\ ・\ ``spellCheckAvailable``\ ・\ ``spellCheckMilliseconds`` も同様です。

設定項目を追加する
------------------

Preferences のチェック項目は、\ ``src/editor/editor_preferences.cpp`` の ``optionDefinitions()`` の表に
1 行足すと追加できます。

#. ``{"myOption", "My option", false},`` を、メニューに並べたい位置へ追加する(前に区切り線を入れるなら 4 番目に ``true``)。
   メニュー項目・保存(``preferences.ini``)は、この表から自動で作られます。
#. 動作を実装する場所で ``preferences_.option("myOption")`` を読む(``MainWindow`` の中)。
#. 切り替えた瞬間に反映すべき処理があれば、\ ``MainWindow::onOptionToggled`` のキーごとの ``if`` の並びに足す。
#. 1 タブごとに反映するものは、\ ``MainWindow::applyPreferences`` に足す(新しいタブと切り替え時の両方で呼ばれる)。
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
* ``src/python/`` の Python ソースも ``.mll`` に含まれるため、Python 部分だけを直した場合も再ビルドが必要です。

版を上げるときは、次の箇所をそろえて更新します(このドキュメントの版は 1 の値を自動で読みます)。

#. ``src/version.h`` の ``HEDIT_VERSION``\ 。プラグインの版・ドックのタイトル・Python の ``hedit.__version__``\ ・
   ``CMakeLists.txt`` の出力先 ``release/plug-ins/windows/<Mayaの年>/<版>`` は、すべてこの値を使います
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
       閉じた場合に再表示しないこと、閉じた後もメニューのコマンドで保存済みのドックへ開き直せること、
       アンロードでメニュー項目が消えることを確認。続けて別の設定で 2 回起動し、浮動のドックを保存した次の起動で
       ``Cannot find procedure "hedit"`` が出ずに開けることも確認
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
* 出力欄の内容は ``hedit_host.output_text()`` で取得します(起動時のエラーが出ていないことの確認に使う)。
* コピーの確認は Windows のクリップボードを使います。ほかのアプリがクリップボードを開いたままだと読み書きできないため、
  テストは最初に書き込みを試し、使えない場合はコピー内容の確認だけ飛ばします(``gui_smoke.py`` は結果の ``skipped`` に記録)。
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
     - 色の値は ``src/editor/theme.h`` に書かれているため、移動は不要
   * - ``WORK_LOG.md`` などの運用ファイル
     - 移さない(親リポジトリ側の運用)

切り出したあとは、\ ``docs/`` を単独でビルドできます(``docs/README.md``)。
