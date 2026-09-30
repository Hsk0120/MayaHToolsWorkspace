ショートカット一覧
==================

hedit にフォーカスがあるときだけ有効です(Windows のキー表記)。編集操作はコード欄が対象で、
Maya のシーンの Undo ではなく **テキストの Undo** で戻せます。VS Code の Windows 向けショートカットを参考にしていますが、
全機能の互換ではありません(マルチカーソル(Ctrl+D など)、コード整形、定義ジャンプは未対応)。

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
   * - Enter / Tab(候補表示中)
     - 候補を確定
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
     - コピー / 切り取り。選択がなければ現在行
   * - Ctrl+Z / Ctrl+Shift+Z
     - テキストの Undo / Redo
   * - Alt+Z
     - コード欄の折り返しを切り替える(タブごと。保存しません)

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
   * - Escape(検索バーの中)
     - 検索バーを閉じてコードへ戻る
   * - Ctrl+G
     - 操作中のコード欄・出力欄で指定行へ移動(番号を入力して Enter、Esc で取り消し)

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
