ショートカット一覧
==================

hedit にフォーカスがあるときだけ有効です(Windows のキー表記)。編集操作はコード欄が対象で、
Maya のシーンの Undo ではなく **テキストの Undo** で戻せます。VS Code の Windows 向けショートカットを参考にしていますが、
全機能の互換ではありません(マルチカーソル(Ctrl+D など)、コード整形、画面の分割、コマンドパレットは未対応)。

実行
----

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+Enter(テンキー Enter、Ctrl+テンキー Enter も可)
     - 選択範囲を実行。選択がなければタブ全体
   * - F5
     - タブ全体を実行(Run all)
   * - Ctrl+Space
     - 補完候補を手動で出す(自動補完の設定にかかわらず使える)
   * - Ctrl+K → Ctrl+I
     - カーソル位置の名前の説明(ホバー)を出す(:ref:`hover`)。マウスを重ねて止めても出る
   * - Ctrl+Shift+Space
     - 引数のヒントを出す(:ref:`signature-help`)。``(``\ ・\ ``,`` を打つと自動で出る
   * - Enter / Tab(候補表示中)
     - 候補を確定(選んでいる候補が打った名前と同じなら、Enter は改行)
   * - Escape(候補表示中)
     - 候補の一覧を閉じる

ファイル・タブ
--------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+N / Ctrl+O / Ctrl+S
     - 新規(Python)/ 開く / 保存
   * - Ctrl+Shift+S
     - 名前を付けて保存
   * - Ctrl+P
     - ファイル名で開く(最近開いたものと Explorer のフォルダーのファイル)
   * - Ctrl+K → D
     - 保存前との差分を表示(File → Compare with saved)
   * - Ctrl+W / Ctrl+F4
     - 現在のタブを閉じる(未保存なら確認)
   * - Ctrl+Tab / Ctrl+Shift+Tab
     - 次 / 前のタブ
   * - Ctrl+PgDown / Ctrl+PgUp
     - 次 / 前のタブ
   * - Ctrl+B
     - Explorer の表示・非表示

編集
----

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+/
     - 選択行 / 現在行のコメント切り替え(Python は ``#``\ 、MEL は ``//``)
   * - Alt+↑ / Alt+↓
     - 選択行 / 現在行を上下へ移動
   * - Shift+Alt+↑ / Shift+Alt+↓
     - 選択行 / 現在行を複製
   * - Ctrl+Shift+K
     - 選択行 / 現在行を削除
   * - Ctrl+L
     - 現在行を選択(繰り返すと次の行まで拡張)
   * - Tab / Shift+Tab
     - 選択行のインデント / 解除。選択なしの Tab は空白 4 文字
   * - Ctrl+] / Ctrl+[
     - 現在行 / 選択行のインデント / 解除
   * - Ctrl+C / Ctrl+X
     - コピー / 切り取り。選択がなければ現在行(貼り付けるとカーソルの行の上へ行として入る)
   * - Home / Shift+Home
     - 行頭の空白の後へ移動。もう一度押すと行の先頭へ(Shift で選択)
   * - Ctrl+↑ / Ctrl+↓
     - カーソルを動かさずに 1 行スクロール
   * - Ctrl+Z / Ctrl+Shift+Z
     - テキストの Undo / Redo
   * - Alt+Z
     - コード欄の折り返しを切り替える(タブごと。保存しません)
   * - Shift+Alt+→ / Shift+Alt+←
     - 選択範囲を、名前 → 文字列 → 括弧の中 → 行 → ブロックの順に広げる / 広げる前へ戻す
   * - ``(``\ ・\ ``[``\ ・\ ``{``\ ・引用符
     - 自動で閉じる。選択中なら選択を囲む。自動で入れた閉じ括弧は、同じ文字を打つと上書きする(:ref:`pref-autoClosing`)

検索・移動
----------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+F / Ctrl+H
     - 検索バー / 置換バーを表示
   * - F3 / Shift+F3
     - 次 / 前の一致箇所(末尾・先頭で折り返す)
   * - Enter / Shift+Enter(検索欄)
     - 次 / 前の一致箇所
   * - Enter(置換欄)
     - 選択中の一致を置換して、次の一致へ
   * - Escape(検索バーの中・コード欄)
     - 検索バーを閉じてコードへ戻る(コード欄では、小窓・補完の一覧が無いとき)
   * - Alt+C / Alt+W / Alt+R / Alt+P(検索欄・置換欄)
     - 大文字小文字の区別 / 単語単位 / 正規表現 / 大文字小文字を保つ置換 を切り替える
   * - Ctrl+G
     - 操作中のコード欄・出力欄で指定行へ移動(番号を入力して Enter、Esc で取り消し)
   * - Ctrl+Shift+O
     - 記号へ移動(タブの中のクラス・関数・変数を名前で選ぶ。選んでいる間はその行を下見する)
   * - F12 / Ctrl+クリック
     - 名前の定義へ移動(別のファイルならそのファイルを開く)
   * - Alt+F12
     - 定義の周りのコードを、その場で小窓に出す(Esc で閉じる)
   * - F8 / Shift+F8
     - 次 / 前の問題へ移動し、行の下に説明を出す(静的解析がオンのとき)

表示
----

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+= / Ctrl++
     - 文字を大きくする
   * - Ctrl+-
     - 文字を小さくする
   * - Ctrl+0
     - 文字サイズを標準に戻す
   * - Ctrl+Shift+[ / Ctrl+Shift+]
     - カーソルを含む範囲を畳む / 開く
   * - Ctrl+K → Ctrl+0 / Ctrl+K → Ctrl+J
     - すべて畳む / すべて開く

出力欄
------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - キー
     - 操作
   * - Ctrl+C
     - 選択した出力をコピー
   * - Ctrl+A
     - 出力欄の全選択
   * - Shift+矢印
     - キーボードで選択範囲を広げる

.. note::

   キーの参考: `VS Code の Windows 公式ショートカット
   <https://code.visualstudio.com/shortcuts/keyboard-shortcuts-windows.pdf>`_
