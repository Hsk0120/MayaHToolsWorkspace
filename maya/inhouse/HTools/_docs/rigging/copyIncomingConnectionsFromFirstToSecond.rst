copyIncomingConnectionsFromFirstToSecond
========================================

1つ目に選んだノードへの入力接続を、2つ目に選んだノードの同じ名前のアトリビュートにもつなぐツールです。
1つ目の接続はそのまま残ります(接続元を2つのノードで共有します)。

似たツールに :doc:`duplicateInputsFromFirstToSecond` があります。違いはそのページの表を見てください。

開き方
------

HTools > rigging > copyIncomingConnectionsFromFirstToSecond。

画面
----

画面はありません。選ぶとすぐに処理します。

使い方
------

1. 接続をコピーしたい元のノードを選び、続けてコピー先のノードを追加で選びます(1つ目 = 元、2つ目 = 先)。
2. メニューから選びます。
3. 元のノードの各アトリビュートについて、入力接続があれば、その接続元を先のノードの同じ名前のアトリビュートへつなぎます。
4. Script Editor に、つないだ接続(``=== copied ===``)、先に同じ名前のアトリビュートが無くて飛ばしたもの(``=== skipped ===``)、
   失敗したもの(``=== errors ===``)を一覧で出します。

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - 実行前
     - 実行後
   * - .. image:: ../_static/images/rigging/copyIncomingConnectionsFromFirstToSecond_before.png
          :alt: ノードエディター。driver_md と driver_pma が source_loc の Translate・Rotate・Scale につながり、target_loc には何もつながっていない
     - .. image:: ../_static/images/rigging/copyIncomingConnectionsFromFirstToSecond_after.png
          :alt: 実行後のノードエディター。同じ接続元が target_loc の Translate・Rotate・Scale にもつながっている

注意・制限
----------

- 2つ以上選んでいないとエラー(``Select two nodes: first = source, second = destination.``)になります。3つ目以降は使いません。
- 先のアトリビュートに別の入力が既にある場合は置き換えず、errors に記録します(先の既存の接続は残ります)。
  先のアトリビュートがロックされている場合も errors に記録します。同じ接続が既にあれば何もしません。
- unitConversion を挟んだ接続(角度のアトリビュートなど)は、その unitConversion ノードの出力をそのまま先へつなぎます。
- 全部の接続をまとめて1回の Undo で戻せます。
- スクリプトからは ``copy_incoming_connections_from_first_to_second(force=False, skip_conversion=False)`` を呼べます。
  ``force=True`` で先の既存の入力を置き換え、\ ``skip_conversion=True`` で unitConversion の手前の接続元を使います(メニューからはどちらも False)。
