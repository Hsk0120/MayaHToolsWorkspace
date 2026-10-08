開発ガイド
==========

構成
----

.. code-block:: text

   hedit/
   ├ CMakeLists.txt          C++ プラグインのビルド定義(Maya devkit の pluginEntry.cmake を利用)
   ├ cmake/embed_python.cmake  src/python/ の .py を C++ の配列へ変換する(ビルド時に自動実行)
   ├ cmake/hedit_version.rc.in  hedit.mll のファイル情報(版・製品名)の元(ビルド時に版を埋め込む)
   ├ .gitattributes / .gitignore  .mll をバイナリとして扱う設定と、0.2.x の版ごとの出力フォルダーの除外
   ├ generate_vs.bat         Visual Studio のプロジェクトだけを生成する
   ├ src/
   │  ├ version.h            版(HEDIT_VERSION)。版の定義はここだけ
   │  ├ core/                Maya にも画面にも依存しない処理(Maya 無しでテストできる)
   │  │  ├ script_lexer.*     Python / MEL の字句解析(色分けと宣言の抽出が共通で使う)
   │  │  ├ python_declarations.*  Python の本文から宣言(def・class・import・代入)を取り出す
   │  │  ├ symbols.*          補完に使う「名前とその情報」の表(Symbol / SymbolTable)
   │  │  ├ completion_engine.*  補完エンジン(補完する位置の判定・モジュールの解決・ファイルのキャッシュ)
   │  │  ├ completion_types.*  補完・ホバー・構文チェックの結果の型(CompletionResult / HoverInfo / AnalysisResult)
   │  │  ├ docstrings.*       文字列リテラルの値と docstring の整形(ホバー用)
   │  │  ├ python_literal.*   C++ から Python のコードを組み立てるときの文字列のエスケープ(ここだけで行う)
   │  │  ├ json_file.*        状態ファイル(tabs.json・ui.json・preferences.json)の読み書き(1 項目だけの書き換えを含む)
   │  │  ├ script_file.*      スクリプトファイルの読み書き(UTF-8 の確認・保存時の整形)
   │  │  ├ output_message.h   出力 1 件の型(OutputKind / OutputMessage)
   │  │  ├ history_text.*     起動前の出力履歴の整形と、行の種類の判定
   │  │  ├ module_scanner.*   import の行のトップレベル名の補完と、sys.path の別スレッド走査
   │  │  ├ text_search.*      検索・置換の一致箇所の計算と、$1 などの展開
   │  │  └ session_data.*     未保存タブの復元ファイル(tabs.json。本文は tabs/<id>.txt)の形と JSON との変換
   │  ├ editor/              Qt の編集画面(Maya に依存しない)
   │  │  ├ editor.h/.cpp      画面の入口。EditorServices(Maya 側の処理の一式)と createEditor
   │  │  ├ main_window.*      画面全体。部品の組み立て・タブ・ファイル・保存と復元・実行
   │  │  ├ code_assist.*      入力の補助(補完・ホバー・構文チェック・スペルチェックの予約と問い合わせ)
   │  │  ├ main_window_menus.cpp  MainWindow のうち、メニュー・ツールバーと Preferences のリセット
   │  │  ├ code_editor.*      1 タブのコード欄(キー操作・自動インデント・補完の一覧・スペルの波線)
   │  │  ├ edit_commands.*    VS Code 風の行編集(コメント・インデント・行の移動や複製)
   │  │  ├ numbered_text_edit.*  行番号付きのテキスト欄(コード欄と出力欄の土台)
   │  │  ├ output_panel.*     出力欄(保持・表示モードでの絞り込み・色付け)
   │  │  ├ find_bar.*         検索・置換バー(配置・大きさは VS Code の検索ウィジェットに合わせる)
   │  │  ├ find_icons.*       検索バーのアイコン(QPainter で描く。画像ファイルは使わない)
   │  │  ├ hover_popup.*      名前の説明(ホバー)の小窓
   │  │  ├ problems_panel.*   構文チェックの結果の一覧
   │  │  ├ syntax_highlighter.*  Python / MEL の色分け
   │  │  ├ editor_tabs.*      タブ欄(ホイールで移動、タブのコード欄の取り出し・見出しの更新)
   │  │  ├ editor_preferences.*  Preferences の設定の表と preferences.json への保存(0.2.x の preferences.ini から移行)
   │  │  ├ session_store.*    tabs.json とタブごとの本文(tabs/<id>.txt)の読み書きとロック
   │  │  ├ explorer.*         Explorer(フォルダーツリー。フォルダーの中身は別スレッドで読む)
   │  │  ├ spelling.*         Windows の辞書を使った英語スペルチェック
   │  │  ├ ui_scale.*         画面の拡大率(4K など)とアイコンの取り出し方
   │  │  └ theme.h            配色(Dark+)。色はここだけで定義する
   │  ├ plugin/              Maya API を使う部分
   │  │  ├ plugin.cpp         プラグインの入口(initializePlugin / uninitializePlugin)
   │  │  ├ hedit_command.*    Maya コマンド hedit とフラグ
   │  │  ├ test_command.*     テスト専用のコマンド heditTest(環境変数 HEDIT_TEST_COMMANDS=1 のときだけ登録)
   │  │  ├ editor_host.*      編集画面を 1 つだけ作り、Maya の処理(実行・補完・出力)とつなぐ
   │  │  ├ output_capture.*   Maya の出力の購読と、画面へ渡すまでのキュー
   │  │  ├ python_bridge.*    Maya 内の Python / MEL の呼出しと、補完エンジンへの情報の受け渡し
   │  │  ├ dock.*             workspaceControl へのドッキング、開閉状態(ui.json)の保存と起動時の復元
   │  │  ├ window_menu.*      Window メニューの項目とアイコン
   │  │  ├ user_paths.*       hedit のファイルを置く場所(tabs.json など)
   │  │  ├ embedded_python.*  同梱の Python を配る import フックの登録
   │  │  └ mel.h              C++ から MEL を実行する補助(mel / melInt / melBool / melQuote)
   │  └ python/              hedit.mll に同梱する Python(普通の .py として編集する)
   │     ├ hedit/__init__.py   show() / restore()(C++ の hedit コマンドを呼ぶ互換用の窓口)
   │     ├ hedit/bridge.py     Python でしか分からない情報(公開名・sys.path・組み込みの名前・docstring)を返す窓口。
   │     │                     C++ からの呼出しは safe_call を通し、例外は {"error": ...} として返す
   │     └ hedit/analysis.py   構文チェック(compile だけ)
   ├ scripts/userSetup.py    起動時に cmds.loadPlugin('hedit') を1回呼ぶだけの最小ブートストラップ
   ├ release/plug-ins/       ビルド済みの hedit.mll(windows/<Mayaの年>/hedit.mll。版のフォルダーは作らない)
   ├ tests/                  補完・standalone・GUI・復元の自動テスト(hedit_host.py は GUI テスト用の補助)
   ├ icons/                  アイコンの元データ(実行時は window_menu.cpp に同梱した SVG を使う)
   └ docs/                   このドキュメント
      └ tools/               画面の撮影と VS Code との見比べ(:ref:`dev-capture`)

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
     - ``plugin/window_menu.cpp`` の ``drawMenuIcon`` が QPainter で描き、\ ``MQtUtil::findMenuItem`` で取り出した
       メニュー項目の QAction へ直接付ける(``menuItem -image`` はファイルしか受け付けないため使わない。
       DLL が埋め込みのデータをディスクへ書き出す形は、ウイルス対策ソフトに怪しまれやすい)。
       メニュー項目がまだ無い(起動の初期)ときは、プラグインと同じ寿命のタイマーで少し後に付け直す。
   * - ドッキング・再表示
     - ``plugin/dock.cpp`` の ``show``\ 。MEL の ``workspaceControl`` を作り、\ ``MQtUtil::addWidgetToMayaLayout`` で
       編集画面(QMainWindow)を直接入れる。uiScript は ``kUiScript``\ (ロード済みなら ``hedit -restore``\ 、未ロードなら
       空のドックを隠すだけ)。\ ``loadPlugin`` も ``-requiredPlugin`` も使わない(使うと、オートロードを切っていても
       Maya がワークスペースの復元でプラグインをロードしてしまう)。保存済みの workspaceControl がある場合は
       **先に表示してから** 中身を作る(表示で Maya が uiScript を実行し、先に入れた画面を作り直して壊すのを避ける)。
   * - 開閉状態の保存(ui.json)
     - ``plugin/dock.cpp`` の ``saveState``\ 。``DockWatcher`` がドックと編集画面の付け替え・表示・非表示を受け取り、
       0.5 秒後に 1 回だけ保存する(Maya へ毎秒問い合わせない)。閉じる操作は ``closeCommand``\ (``kCloseCommand``)の
       ``hedit -closed``\ 。プラグインがロードされているときだけ呼ぶ(未ロードのまま Maya が保存済みの
       浮動ドックを閉じても ``Cannot find procedure "hedit"`` を出さないため)。
       Maya の終了は ``quitApplication`` の scriptJob(``hedit -quitting``)で受け取る。Maya のワークスペースは保存し直さない。
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
     - ``plugin/output_capture.cpp`` の ``OutputCapture``\ 。既定は ``MCommandMessage`` の本文を ``core/history_text.cpp`` の
       ``formatCommandOutput`` で Script Editor と同じ形に整える(速い方式)。Preferences の ``exactOutput`` がオンなら、非表示の
       ``cmdScrollFieldReporter`` を MEL で作り、\ ``MQtUtil::findControl`` で表示文書を購読する(正確な方式。Maya が reporter への
       追記に時間をかけるため遅い)。起動時の履歴の取り込みはどちらも reporter で行い、整形は ``compactHistory``\ 。
   * - タブ復元先の決定
     - ``plugin/user_paths.cpp`` の ``sessionFilePath``\ (``hedit -sessionPath`` でも取得できる)。Maya への問い合わせは最初の 1 回だけ。
   * - Maya 終了時の出力転送の停止
     - ``plugin/plugin.cpp`` の ``onMayaExiting``\ (``kMayaExiting``)→ ``OutputCapture::stopForExit``\ 。
       終了処理中の reporter 追記を hedit 画面へ描画しない。
   * - ``import xxx`` / ``from xxx`` のトップレベル名の補完
     - ``core/module_scanner.cpp`` の ``ModuleScanner``\ 。\ ``sys.path`` の各フォルダーを C++ のスレッド(GIL 不要)で走査する。
       編集画面を作ってから 1 秒後に走査を始める(画面が閉じていれば始めない。それより前に import の行で補完すれば、
       補完の側で始める)。初回は最大 0.5 秒待つ。以後の再走査は 5 秒間隔で裏で行う。
       Python からは ``sys.path`` と組み込み・読み込み済みの名前(``hedit.bridge.module_names``)だけを受け取る
       (``plugin/python_bridge.cpp``)。Maya に依存しないため ``tests/ui_smoke.cpp`` で検証する。
   * - それ以外の補完
     - ``core/completion_engine.cpp`` の ``CompletionEngine``\ (C++)。補完する位置の判定、編集中の本文と未読込のソースの
       宣言の抽出(``core/python_declarations.cpp``\ 。以前の Python の ``ast`` と同じ結果になることを
       ``tests/test_declarations_parity.py`` で確かめる)、\ ``from X import Y`` や相対 import の解決、ファイルのキャッシュを行う。
       Python に問い合わせるのは ``ModuleSource`` の関数(``plugin/python_bridge.cpp`` → ``hedit.bridge``\ )だけ:
       読み込み済みのモジュールの公開名・\ ``sys.path``\ ・組み込みの名前と予約語。
   * - 色分け
     - ``editor/syntax_highlighter.cpp``\ 。\ ``core/script_lexer.cpp`` の字句解析の結果で塗る。行をまたぐ文字列・コメントは
       QSyntaxHighlighter の block state で次の行へ引き継ぐ。
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
   * - (なし)・\ ``-show``\ (``-sh``)と ``-floating``\ (``-f``)
     - 画面を開く。開いていれば一度閉じて(タブを保存して)開き直す。\ ``-floating`` を付けたときだけ浮動状態を変える。
   * - ``-restore``\ (``-r``)
     - workspaceControl の uiScript から呼ぶ。前回閉じていた場合は中身を作らず非表示に保つ。
   * - ``-saveState``\ (``-ss``)
     - 開閉状態をすぐに ui.json へ保存する。
   * - ``-sessionPath``\ (``-sp``)
     - タブ復元先(tabs.json)のパスを返す。画面を作らないため mayapy でも使える。
   * - ``-closed``\ (``-cl``)・\ ``-quitting``\ (``-qt``)
     - 内部用。ドックの ``closeCommand`` と終了通知の scriptJob から呼ばれる。

テスト用の入口は、製品のコマンドとは別の ``heditTest``\ (``plugin/test_command.cpp``)にあります。
環境変数 ``HEDIT_TEST_COMMANDS=1`` のときだけ登録するので、普段の Maya には出ません(テストのランナーが設定します)。

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - ``heditTest`` のフラグ
     - 動作
   * - ``-editor``\ (``-ed``)
     - 編集画面を(未作成なら作って)そのアドレスを返す。GUI テストが PySide から画面を参照するときに使う。
   * - ``-complete``\ (``-cp``)・\ ``-declarations``\ (``-dc``)と本文
     - C++ の補完の結果・宣言の抽出の結果を JSON で返す。画面を作らないため mayapy でも使える。
   * - ``-describe``\ (``-ds``)と本文
     - 本文の末尾の名前のホバーの説明(見出しと docstring)を JSON で返す。

同梱の Python について
~~~~~~~~~~~~~~~~~~~~~~

Python のソースは ``src/python/`` に普通の ``.py`` として置きます。ビルドのたびに ``cmake/embed_python.cmake`` が
それを C++ の配列(ビルドフォルダーの ``generated/embedded_python_sources.h``\ 、Git の対象外)に変換し、
``hedit.mll`` に入れます。モジュール名はフォルダー構成から決まります(``hedit/bridge.py`` → ``hedit.bridge``\ 、
``__init__.py`` はパッケージ)。

``initializePlugin`` が ``hedit::embedded::installModules()``\ (``plugin/embedded_python.cpp``)で ``sys.meta_path`` の先頭へ
import フックを登録し、\ ``import hedit`` などは通常の ``.py`` と同じく import した時点で同梱ソースから読み込まれます
(バッチ/mayapy でも登録するため、補完などの Python API は standalone でも使えます)。

ソースは Python の普通の文字列リテラルとして渡し、実行は標準の ``importlib.abc.InspectLoader``\ (``get_source`` →
``exec_module``\ )に任せます。ソースを符号化して戻したり、\ ``exec``\ ・\ ``compile`` を自前で呼んだりはしません。
「符号化した文字列を戻して実行する」形はマルウェアの典型で、ウイルス対策ソフトに誤検知されやすいためです。

* ``hedit.__version__`` は、ロード時に ``src/version.h`` の値が設定されます(``__init__.py`` には書きません)。
* フックを ``sys.meta_path`` の先頭に置くのは、\ ``PYTHONPATH`` 上に同名のフォルダー(旧版の ``__pycache__``
  だけが残った ``scripts/hedit`` など)があっても、空の名前空間パッケージとして先に解決させないためです。
  そうした同梱以外で読まれた ``hedit`` 系のモジュールは、ロード時に取り除きます。
* プラグインをアンロードしてロードし直しても、同梱から読み込み済みのモジュールは残します(補完のキャッシュを保つため)。
  ただし、作り直した ``hedit.mll`` をロードした場合(同梱の Python の本文と版から作る印が違う場合)は、前のビルドの
  ``hedit.*`` を取り除いて、新しいソースで読み直します(同じ Maya のまま古いコードが動き続けないように)。
  新しいソースを反映するには Maya を再起動してください(ディスク上の ``.py`` を読むわけではないため ``reload()`` では更新できません)。

設計上の決まり
~~~~~~~~~~~~~~

* **プラグイン全体で 1 つの状態は、作る順番と壊す順番を決めている。**
  ``initializePlugin`` が出力の取り込み(``createOutputCapture``)→ Python との受け渡し(``python::initialize``\ 。補完エンジン・
  公開名の控え・sys.path の走査)→ ドック(``dock::initialize``)の順に作り、\ ``uninitializePlugin`` が逆の順番で壊す
  (``plugin/plugin.cpp`` のコメントに番号付きで書いてある)。関数の中の static 変数で作ると、壊れる時期が DLL の解放まで
  遅れて分からなくなるので使わない。編集画面は 1 つだけ(Maya のスクリプトエディターと同じ考え)。
* **Python の呼出しは、全て Maya のメインスレッドで同期的に行う。** Python の GIL と Maya の API がメインスレッド前提のため、
  別スレッドへは移せない。その代わり、問い合わせの回数と量を減らしている: 補完・構文チェックは入力が止まってから、
  ホバーは同じ本文・同じ位置なら前回の結果を使う(``CodeAssist``)、公開名は印(signature)が同じなら受け取り直さない、
  sys.path のフォルダーの走査とファイルの宣言の抽出は C++ で行う。
* **Python 側の例外は、hedit.bridge.safe_call で受け止める。** C++ からの呼出しは全て ``safe_call`` を通し、例外は
  ``{"error": "..."}`` として返る。補完のときはステータスバーに「Completion: Python error: …」と出す
  (Script Editor に毎回トレースバックを流さない)。
* **出力は、既定では公式の通知の本文を自分で整えて取り込む**\ (``MCommandMessage``)。非表示の reporter を使う正確な方式は、
  Maya が reporter への追記に Script Editor を 1 つ開いているのと同じ時間をかけるため、Preferences で選んだときだけ使う
  (0.4.1 の計測: エラー 5,000 件の 8 行のトレースバックで 8.5 秒 → 4.7 秒)。正確な方式は reporter の部品の作りに頼っていて、
  Maya の版で作りが変わって文書が見つからない場合は速い方式で動く。環境変数 ``HEDIT_OUTPUT_FALLBACK=1`` で、正確な方式を
  選んでも reporter を使わない動きを試せる(``tests/output_fallback_smoke.py``)。両方式の見た目は
  ``tests/output_format_smoke.py`` が Maya の実物の reporter と突き合わせる。
* **名前の種類は SymbolType で表す。** 欄の組合せで種類を判断しない。作るときは ``Symbol::module`` などの関数を使う。
* **補完・ホバーの 1 回の問い合わせの中だけ使う情報は、問い合わせごとの構造体に入れる**\ (``CompletionEngine::Request``)。メンバー変数に持たない。
* **文字列を Python のコードへ埋め込むときは、専用の関数を使う**\ (``core/python_literal.h``)。MEL は ``plugin/mel.h`` の ``melQuote``\ 。
* **状態ファイルは、共通の読み書きの関数を使う**\ (``core/json_file.h``)。1 項目だけ変えるときは ``updateJsonFile``\ 。

C++ から MEL を呼ぶときの注意
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``MGlobal::executeCommandStringResult`` は、整数・真偽値を返すコマンド(``-exists`` / ``-q -visible`` など)では
  失敗して空を返します。\ ``plugin/mel.h`` の ``melInt`` / ``melBool`` を使ってください。
* ``MQtUtil::addWidgetToMayaLayout`` の戻り値の型は Maya の版で異なります。取り付けたかは Qt の親子関係で確かめます。
* 遅延実行(``QTimer::singleShot`` など)やシグナルに渡す C++ のラムダは ``hedit.mll`` の中にあります。実行前に
  プラグインがアンロードされると解放済みのコードを呼んで Maya が落ちるため、\ ``dock::lifetime()`` などプラグインと
  同じ寿命のオブジェクトを文脈に渡し、解除時に取り消されるようにしてください。
  ただし Qt5(Maya 2022〜2024)の ``QTimer::singleShot(時間, 文脈, ラムダ)`` は、時間が 1ms 以上だと、文脈の
  オブジェクトを破棄しても予約が時間まで Qt の中に残り、そのときに ``hedit.mll`` の中のラムダを片付けようとして
  アンロード後に落ちます。時間を指定する遅延実行は、画面やプラグインと同じ寿命のオブジェクトを親にした ``QTimer`` を
  作って使ってください(親が破棄されればタイマーと接続も消えます)。別のスレッドからの呼出しは、
  プラグインが所有する ``QObject`` を相手にした ``QMetaObject::invokeMethod(..., Qt::QueuedConnection)`` を使います
  (相手を消すと、まだ実行していない呼出しも取り消されます。例: ``OutputCapture`` の ``notifier_``\ )。
* コード欄の文書の通知(``QTextDocument::contentsChange``\ ・\ ``contentsChanged``\ )と、スクロールバーの値の変化の中では、
  ``QTextCursor``\ (\ ``ExtraSelection``\ の中のものを含む)を作ったり消したりしないでください。
  ``QTextDocument::clear()``\ (``setPlainText("")``\ ・\ ``clear()`` から呼ばれる)は、文書が持つカーソルの一覧を一時的に空にしている間に
  最初の行を入れるため、その途中でこれらの通知が出ます。そこでカーソルを消すと、一覧を戻したときに解放済みのカーソルが残り、
  後で別の場所が壊れて落ちます(0.5.0 の開発中に Maya 2022 で再現)。通知の中では印を付けるだけにし、
  ``CodeEditor`` の ``applyEditFollowUps``\ ・\ ``scheduleDecorations`` のように、イベントループへ戻ってから処理します。
* ``plugin/dock.cpp`` の手順の順番には、Maya の版ごとの落ちる不具合を避けるための理由があります。
  コメントの理由を確かめずに順番を入れ替えないでください(変えた場合は ``tests/run_startup.py`` で確かめます)。

エディターの役割分担
~~~~~~~~~~~~~~~~~~~~

``editor/`` は「画面と入力」を担当し、Maya に触れる処理(コード実行・補完・静的解析・出力の取得)は、
``plugin/editor_host.cpp`` が ``EditorServices`` に **関数として詰めて渡します**\ 。エディターは Maya の API を直接呼びません。
そのため、画面の部分を Maya なしで(offscreen で)テストできます(``tests/ui_smoke.cpp``)。

テストや PySide から参照される名前(``objectName`` とアクションの表示名)は、GUI テストが画面を探すのに使っています。
変える場合は ``tests/`` も合わせて直してください。主なもの: ``hedit``\ ・\ ``codeEditor``\ ・\ ``output``\ ・\ ``outputPanel``\ ・
``outputMode``\ ・\ ``editorSplitter``\ ・\ ``scriptToolbar``\ ・\ ``analysisProblems``\ ・\ ``languageMode``\ ・\ ``completionStatus``\ ・
``explorerDock``\ ・\ ``explorerTree``\ ・\ ``toggleExplorer``\ ・\ ``option_<設定名>``\ ・\ ``lineJump``\ ・
``hoverPopup``\ ・\ ``hoverText``\ (ホバーの小窓と本文。コード欄の子)。
0.4.0 で足した名前: ``signatureHelp``\ ・\ ``completionDetail``\ ・\ ``peekDefinition``\ ・\ ``problemPopup``\ (コード欄の子の小窓)・
``stickyScroll``\ (見出しの固定表示)・\ ``markerScrollBar``\ ・\ ``quickPick``\ ・\ ``quickPickInput``\ ・\ ``quickPickList``\ ・
``outlineDock``\ ・\ ``outline``\ ・\ ``toggleOutline``\ ・\ ``goToSymbol``\ ・\ ``quickOpen``\ ・\ ``recentMenu``\ ・
``compareWithSavedAction``\ ・\ ``compareWithSaved``\ ・\ ``diffView``\ ・\ ``revertFile``\ 。
検索バーは ``findBar``\ ・\ ``findField``\ ・\ ``findText``\ ・\ ``replaceField``\ ・\ ``replaceText``\ ・\ ``toggleReplace``\ ・
``searchCase``\ ・\ ``searchWord``\ ・\ ``searchRegex``\ ・\ ``preserveCase``\ ・\ ``searchCount``\ ・\ ``findPrevious``\ ・\ ``findNextMatch``\ ・
``findInSelection``\ ・\ ``closeFind``\ ・\ ``replaceOne``\ ・\ ``replaceAll``\ ・\ ``findError``\ (不正な正規表現の吹き出し。タブ欄の子)です。
ボタンは ``QToolButton`` なので、テストでは ``QAbstractButton`` として探します。
コード欄の動的プロパティ ``language``\ ・\ ``path``\ ・\ ``spellCheckAvailable``\ ・\ ``spellCheckMilliseconds``\ ・
``textPending``\ (復元したまま、まだ本文を文書へ入れていないタブなら true)も同様です。
速さの確認用に、編集画面(``hedit``)には ``openMilliseconds``\ (画面の作成)・\ ``sessionWrites``\ ・\ ``sessionTextWrites``\ ・
``sessionListings``\ (tabs.json・本文のファイルの書き込みと、``tabs/`` の一覧の回数)・\ ``fileListMilliseconds``\ ・
``fileListCount``\ (Ctrl+P の一覧)を、検索バー(``findBar``)には ``searchMilliseconds``\ ・\ ``searchComputations`` を入れています
(``tests/perf_smoke.py`` が読む)。

設定項目を追加する
------------------

Preferences のチェック項目は、\ ``src/editor/editor_preferences.cpp`` の ``optionDefinitions()`` の表に
1 行足すと追加できます。

#. ``{"myOption", "My option", false},`` を、メニューに並べたい位置へ追加する(前に区切り線を入れるなら 4 番目に ``true``)。
   メニュー項目・保存(``preferences.json``)は、この表から自動で作られます。
#. 動作を実装する場所で ``preferences_.option("myOption")`` を読む(``MainWindow`` の中)。
#. 切り替えた瞬間に反映すべき処理があれば、\ ``MainWindow::onOptionToggled`` のキーごとの ``if`` の並びに足す。
#. 1 タブごとに反映するものは、\ ``MainWindow::applyPreferences`` に足す(新しいタブと切り替え時の両方で呼ばれる)。
#. ``docs/preferences.rst`` の一覧表と、項目ごとの節(初期値・何をするか・詳しい動き・オフのとき・注意)を追加する。
#. ``tests/options_smoke.py`` に、切り替えの検証を追加する。

.. note::

   キーは ``preferences.json`` の保存名になります。一度公開したキーの名前は変えないでください
   (変えると、利用者の保存済みの設定が読み込まれなくなります)。

ビルド
------

Windows で、Visual Studio と Maya の devkit が必要です。親リポジトリ(MayaHToolsWorkspace)では、
``tools/build_maya_plugin.py`` が Visual Studio・CMake・ツールセットを自動検出し、必要な devkit を
インストール済みの Maya から生成します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hedit --versions 2022 2023 2024 2025 2026 2027

* ビルドフォルダーは ``.maya-output/plugin-build/`` の下(Git の対象外)です。
* 出力は ``release/plug-ins/windows/<Mayaの年>/hedit.mll`` です(版のフォルダーは作りません。Maya の信頼済みの場所と
  オートロードが、版を上げても外れないようにするため)。
* ``hedit.mll`` には版・製品名のファイル情報(``cmake/hedit_version.rc.in``)が入り、制御フローガード(``/guard:cf``)を有効にし、
  pdb の場所はファイル名だけを埋め込みます(作業フォルダーの絶対パスを入れない)。
* ``.mll`` はビルド環境の無い場所でも使えるようコミットします(``.gitattributes`` でバイナリ扱い)。ただしコミットのたびに
  5 版分が増えるので、利用者に届ける区切り(版を上げたとき)にまとめてビルドし直してコミットしてください。
* ロード済みの ``.mll`` は上書きできません。ビルドの前に、該当する Maya を終了してください。
* ``src/python/`` の Python ソースも ``.mll`` に含まれるため、Python 部分だけを直した場合も再ビルドが必要です。

版を上げるときは、次の箇所をそろえて更新します(このドキュメントの版は 1 の値を自動で読みます)。

#. ``src/version.h`` の ``HEDIT_VERSION``\ 。プラグインの版・ドックのタイトル・Python の ``hedit.__version__``\ ・
   ``hedit.mll`` のファイル情報は、すべてこの値を使います
#. 親リポジトリの ``maya/modules/hedit.mod`` の各バージョンの版(``MAYA_PLUG_IN_PATH`` は版を含まないので変えない)
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

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_tests.py 2022 2023 2024 2025 2026 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_startup.py 2022 2023 2024 2025 2026 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_gui.py 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/tests/run_session.py 2024 2027

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - スクリプト
     - 内容
   * - ``run_tests.py``
     - 版ごとに、補完・静的解析の単体テスト(``test_completion.py``)、Maya standalone での ``.mod`` の解決・
       プラグインのロード/アンロード・実在する補完候補(``maya_smoke.py``)、保存先の決定(``test_session_path.py``)、
       C++ の宣言の抽出と Python の ``ast`` の突き合わせ(``test_declarations_parity.py``\ 。hlib・hrig・HTools・標準ライブラリの約 400 ファイル)、
       同じ C++ ウィジェットの offscreen 描画と、Maya 非依存の C++ 部分(履歴の整形・import の行の補完・
       ``sys.path`` の走査・字句解析・宣言の抽出・補完エンジン・定義の場所・構成と折りたたみの範囲・行の差分・
       引数のヒントの解析・括弧と選択範囲の拡大・検索置換・tabs.json・行編集・ファイルの読み書き)と、コード欄の
       括弧の自動で閉じる・同じ名前の強調・折りたたみ・見出しの固定表示・記号へ移動などの
       テスト(``hedit_ui_smoke.exe``)を実行する
   * - ``run_startup.py``
     - 同じ専用設定で 3 回起動する(``startup_smoke.py``)。プラグインのロードだけで Window メニューの項目と
       アイコンが追加されること、メニューのコマンドで開けること、右ドック・Python / MEL 本文の復元、
       閉じた場合に再表示しないこと、閉じた後もメニューのコマンドで保存済みのドックへ開き直せること、
       アンロードでメニュー項目が消えることを確認。続けて別の設定で 2 回起動し、浮動のドックを保存した次の起動で
       ``Cannot find procedure "hedit"`` が出ずに開けることも確認
   * - ``run_gui.py``
     - 専用の空シーン・専用設定の Maya GUI で、``userSetup.py`` による自動ロード、表示・ドッキング・実行・出力・補完・
       検索・ショートカットなどを確認(``--suite`` で ``gui_smoke.py`` / ``completion_output_smoke.py`` /
       ``formatting_spelling_smoke.py`` / ``output_format_smoke.py`` / ``output_fallback_smoke.py`` /
       ``vscode_features_smoke.py`` / ``perf_smoke.py`` を選ぶ。既定は ``gui_smoke.py``\ 。
       ``perf_smoke.py`` は、画面を開く時間(タブ 1 枚と 30 枚)・カーソル移動だけでの保存の回数・大きな本文の検索・
       Ctrl+P の一覧・文字サイズの変更・新しいタブの時間を測って結果に残す。
       ``vscode_features_smoke.py`` は 0.4.0 で足した機能(差分の印・問題の波線と F8・折りたたみ・見出しの固定表示・
       記号へ移動・アウトライン・定義へ移動・保存前との差分・ファイル名で開く・引数のヒント・補完の説明)を操作して画面を撮る。
       ``output_fallback_smoke.py`` は、Maya の非表示 reporter が見つからない場合の代わりの出力の取り込みを確かめる)
   * - ``run_session.py``
     - 2 回起動し、未保存タブの自動保存と、次の起動での本文・パス・選択位置・未保存状態の復元を確認(``session_smoke.py``)
   * - ``test_session_path.py``
     - tabs.json の場所(既定の場所と環境変数 ``HEDIT_SESSION_FILE``\ )を確認。mayapy で単体実行する(``MAYA_MODULE_PATH`` に ``maya/modules`` が必要)
   * - ``test_declarations_parity.py``
     - C++ の宣言の抽出(``heditTest -declarations``\ )が、以前の Python の ``ast`` と同じ結果になるかを実在のファイルで突き合わせる

* テストのランナーは環境変数 ``HEDIT_TEST_COMMANDS=1`` を設定し、テスト専用の ``heditTest`` コマンドを使えるようにします。
* ``hedit_ui_smoke.exe`` は検査ごとに ``PASS`` / ``FAIL`` と名前を表示し、最後に合格数を出します(``run_tests.py`` の ui.log)。
* 速さの回帰は ``hedit_ui_smoke.exe`` の ``editorPerformance``\ (約 6,000 行の本文で、1 キーの入力・カーソルの点滅・
  カーソル移動・スクロール・同じ名前の強調・遠い括弧の対応・全て畳んだままの入力)で測り、1 回あたりのミリ秒を
  ``editor 名前: 値 ms`` の形で ui.log に出します。上限(200ms)は極端な回帰だけを見つける緩いものです。
  変更の前後を比べるときは、同じ PC で両方をビルドして続けて実行します(ほかのビルドと同時に測ると数値がぶれます)。
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
* ``QTest.keyClicks`` に改行文字(``\n``\ )を含めないでください。QtTest が扱えずに Maya ごと異常終了します。
  改行は ``QTest.keyClick(widget, Qt.Key_Return)`` で送ります。
* Maya 2027(Qt 6.8 以降)では、\ ``Q_OBJECT`` の無い独自のクラスを ``findChild<T>`` に渡せません(コンパイルエラー)。
  基底のQtのクラス(``QFrame`` など)で探してから変換します。
* Maya 2024 は起動直後に Arnold(mtoa)の遅延登録が GUI スレッドを約 5 秒止めます。GUI テストで待機する場合は、
  壁時計ではなくイベントループが回った回数で数えてください(``session_smoke.py`` 参照)。

.. _dev-capture:

画面の撮影と VS Code との見比べ
--------------------------------------

``docs/tools/`` に、画面を撮る開発用のスクリプトがあります(リポジトリ直下から実行。出力は ``.maya-output/`` の下)。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/docs/tools/run_capture.py 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/docs/tools/findbar_compare.py 2027
   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/hedit/docs/tools/vscode_capture/capture.py

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - スクリプト
     - 内容
   * - ``run_capture.py``\ (``capture_suite.py``)
     - このドキュメントの画像を、専用設定の Maya GUI で撮り直して ``docs/_static/images/`` へコピーする
   * - ``findbar_compare.py``\ (``findbar_suite.py``)
     - VS Code と hedit の検索バーを同じ5つの状態(検索欄に入力中・置換欄に入力中・切り替えボタンがオン・一致なし・
       不正な正規表現)で撮り、上下に並べた比較画像 ``compare_<状態>.png`` を作る。\ ``--no-vscode`` で hedit だけ
   * - ``vscode_capture/capture.py``
     - 隔離した VS Code を起動し、手順の JSON(例: ``find_replace.json``\ )どおりにコマンドを実行して窓を撮る。
       手順の書き方は ``vscode_capture/extension/extension.js`` の先頭を参照

* VS Code の撮影は、専用の ``--user-data-dir`` と ``--extensions-dir`` を一時フォルダーに作り、撮影用の拡張機能
  (``vscode_capture/extension/``\ 。配布はしない)だけを読み込みます。普段の VS Code・設定・拡張機能には触れず、
  終了時は自分が起動した VS Code だけを閉じます。\ ``Code.exe`` は既定のインストール先から探します
  (別の場所なら環境変数 ``HEDIT_VSCODE_EXE``\ )。
* 撮影は Windows の ``PrintWindow`` を使うので、VS Code の窓がほかの窓の後ろにあっても撮れます。
* 比較画像で VS Code 側から切り出す範囲は、\ ``find_replace.json`` の ``compareCrop``\ (窓の中の x, y, 幅, 高さ)です。
  窓の大きさ(``windowSize``\ )や VS Code の版で検索ウィジェットの位置が変わったら合わせてください。
* 検索バーの寸法は VS Code を 100% 表示で測った値です(``src/editor/find_bar.h`` の先頭)。
  アイコンは ``src/editor/find_icons.cpp`` が 16×16 の方眼に描いており、画像ファイルは使いません。

英語版のドキュメント
--------------------

ドキュメントは日本語で書き、英語版は Sphinx の多言語対応(gettext)で作ります。本文の文を
``docs/locale/en/LC_MESSAGES/docs.po`` に取り出し、英訳を保存しておきます。公開サイトでは日本語版を ``hedit/``\ 、
英語版を ``hedit/en/`` に置き、各ページの上の帯の右端の「日本語 | English」で切り替えます(``docs/_templates/layout.html``)。

英訳は自動では行いません(時間がかかるため)。本文を変えても、英訳を更新するまでは、変えた文が英語版に日本語のまま出ます。
英訳を更新したいときに、Maya を閉じた状態で、リポジトリ直下から次を実行し、\ ``docs.po`` もコミットします。

.. code-block:: powershell

   python tools/translate_docs.py hedit

* 英訳は手元の Ollama の ``qwen3-coder:30b`` で行います(無料。GPU のメモリを約 18 GB 使うので、Maya と同時に使わない)。
  GitHub Actions は保存した ``docs.po`` で英語版をビルドするだけで、LLM は使いません。
* 未訳の文だけを訳します。消えた文は ``docs.po`` からも消し、未訳の文は英語版に日本語のまま出ます。
* インラインのコード・ロール(``:ref:`` など)・URL は目印に置き換えてから訳させ、訳の後で元に戻します。
  記法が崩れた訳は使わず未訳のまま残し、最後に英語版を ``-W`` でビルドして警告が無いことを確かめます。
* 用語は ``tools/translate_docs.py`` の ``GLOSSARY`` でそろえます。誤訳は ``docs.po`` の ``msgstr`` を直接直して構いません
  (直した訳は、原文が変わらない限り上書きされません)。
* 英語版だけをビルドするには ``-D language=en`` を付けます。

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
