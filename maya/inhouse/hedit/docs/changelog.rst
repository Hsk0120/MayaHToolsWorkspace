変更履歴
========

各版の主な変更です(新しい順)。詳細な検証内容はリポジトリの作業履歴を参照してください。

.. list-table::
   :header-rows: 1
   :widths: 12 88

   * - 版
     - 内容
   * - 0.2.10
     - 専用の非表示 Maya reporter が整形した表示文書の追記だけを取得。標準スクリプトエディターと同じ記号・改行にそろえた。
       ドックのタイトルに版を表示。
       hedit 本体の Python(``scripts/hedit/*.py``)を ``hedit.mll`` に同梱し、プラグインのロードだけで
       Window メニュー登録(C++/MEL、アイコンの SVG も同梱)と前回画面の復元まで完了するようにした。
       ``scripts/userSetup.py`` は起動時に ``loadPlugin`` を呼ぶだけ。Maya 終了時に閉じた画面へ出力を描画して
       クラッシュする問題を修正。
       さらにドッキング・開閉状態の保存と復元・起動時の出力履歴・出力用 reporter・タブ復元先の決定を Python から C++ へ移し、
       ``MayaQWidgetDockableMixin`` を使わない構成にした。Python は補完と構文チェックだけ。
       Window メニューと uiScript は MEL の ``hedit -show`` / ``hedit -restore``\ 。\ ``hedit`` コマンドに
       ``-show`` / ``-floating`` / ``-restore`` / ``-saveState`` / ``-sessionPath`` を追加。
       ``import xxx`` のトップレベル名の補完を C++ へ移し、\ ``sys.path`` の走査を GIL を取らない C++ のスレッドで
       編集画面の作成時から行うようにした。最初の Ctrl+Space から未読込のパッケージが候補に出る
       (以前は候補が空で約 0.5 秒後に出直し、走査中は Python のスレッドが画面を引っかからせていた)
       文字・アイコン・余白・幅を Maya のインターフェースの拡大率(\ ``MQtUtil::dpiScale``\ )に合わせ、
       4K 画面などで標準スクリプトエディターと同じ大きさで表示するようにした(アイコンは ``MQtUtil::createIcon``\ )。
       前回ドックが保存された直後の ``hedit -show`` でのクラッシュと、プラグイン未ロードのまま Maya がフロートの
       ドックを閉じたときの ``Cannot find procedure "hedit"`` を修正
   * - 0.2.9
     - Maya メインスレッドのログ通知を、タイマーを待たず最大約 40 fps で反映
   * - 0.2.7
     - Output の表示モード(Normal / Output only / Warnings + Errors / Errors only)
   * - 0.2.6
     - 検索・置換バーを入力欄の右上に重ねて表示
   * - 0.2.5
     - 英語スペルチェック(Windows 標準辞書)を追加。自動補完を入力停止から 250 ms 後に。Output を 12 px に
   * - 0.2.3
     - 初回表示時に Maya が保持する履歴を最大 512 Ki 文字取り込む
   * - 0.2.2
     - ツールバーを Maya 標準スクリプトエディターと同じアイコン中心の表示に。File・Edit・History・View・Command メニュー
   * - 0.2.1
     - 出力欄の行番号を初期で非表示にし、Preferences で切り替え可能に
   * - 0.2.0
     - MEL タブ、Explorer(Open folder / Add folder)、タブのスクロール、Ctrl+G、検索置換の拡張、Window メニュー、起動時の画面復元
   * - 0.1.14
     - Ctrl+G で指定行へ移動
   * - 0.1.12
     - 出力欄の選択とコピー
   * - 0.1.11
     - 出力の種別ごとの色(Warning / Error / Result / Info / History)
   * - 0.1.10
     - 表示倍率(Zoom)
   * - 0.1.9
     - 外観を Maya 標準の Qt スタイルに合わせ、コード欄・出力欄だけ Dark+ 配色に
   * - 0.1.8
     - 静的解析(構文診断)
   * - 0.1.7
     - 補完が対象モジュールの現在の公開名と ``sys.path`` に追従
   * - 0.1.6
     - 未保存タブの自動復元(``tabs.json``)
   * - 0.1.5
     - Ctrl+Enter の選択実行(Maya 形式)をコード欄が直接処理
   * - 0.1.4
     - VS Code 系のショートカット
   * - 0.1.3
     - 補完を Maya と同じプロセス内で直接実行(別プロセスを廃止)
   * - 0.1.2
     - Maya 標準の Python 実行経路で実行し、標準スクリプトエディターと変数・出力を共有

名称
----

フォルダー・Python パッケージ・プラグイン・メニューと画面の名称は、小文字の ``hedit`` です(旧名 ``HEditor`` / ``heditor``)。
旧名の保存先にあるタブ・UI 状態・設定は、新しい保存先に同名のファイルがまだない場合だけコピーします(旧データは削除しません)。
保存済みワークスペースの旧 ``uiScript`` に限り、互換用の ``heditor.restore()`` を残しています。
