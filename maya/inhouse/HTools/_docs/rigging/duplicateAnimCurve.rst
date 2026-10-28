duplicateAnimCurve
==================

選んだノードのキー可能なアトリビュートにつながったアニメーションカーブを複製し、複製の方へつなぎ替えるツールです。
元のカーブは接続を外して残します。ほかのノードと共有しているカーブを、このノードだけ別にしたいときなどに使います。

開き方
------

HTools > rigging > duplicateAnimCurve。

画面
----

画面はありません。選ぶとすぐに処理します。

使い方
------

1. キーの付いたノード(コントローラーなど)を選びます(複数可。シェイプを選ぶと親の transform を対象にします)。
2. メニューから選びます。
3. キー可能なアトリビュート(translate などは X・Y・Z に分けて)ごとに、直接つながったアニメーションカーブを調べ、

   - 同じ種類のカーブ ``<元の名前>_bak`` を作ってキーをすべてコピーし(前後の Infinity・Weighted Tangents の設定も写します)、
   - 元のカーブの接続を外して、複製したカーブをつなぎます。

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - 実行前
     - 実行後
   * - .. image:: ../_static/images/rigging/duplicateAnimCurve_before.png
          :alt: ノードエディター。arm_ctrl_rotateX と arm_ctrl_translateY の2本のカーブが arm_ctrl につながっている
     - .. image:: ../_static/images/rigging/duplicateAnimCurve_after.png
          :alt: 実行後。arm_ctrl_rotateX_bak と arm_ctrl_translateY_bak が arm_ctrl につながり、元のカーブは接続が外れて残っている

複製の名前は ``_bak`` が付きますが、\ **つながっているのは複製の方** です。\ ``_bak`` の無い元のカーブが、どこにもつながらない状態で残ります。
同じ名前があるときは末尾に番号を付けます(``_bak1`` など)。

注意・制限
----------

- 何も選んでいないときは ``Nothing is selected.`` の警告を出します。
- 対象はアニメーションカーブが **直接** つながったアトリビュートだけです。pairBlend・ブレンドノードなどを挟んだもの、
  ロックされたアトリビュート、マルチアトリビュートは飛ばします。
- ドリブンキーのカーブ(animCurveUL など)も対象になりますが、ドライバーからの入力接続は複製しません。
  実行するとドライバーで動かなくなるため、ドリブンキーの付いたノードには使わないでください。
- キーのコピーやつなぎ替えに失敗したアトリビュートは警告を出して飛ばし、元のカーブの接続を残します。
- 全ノードの処理を1回の Undo で戻せます。
- スクリプトからは ``duplicate_anim_only_and_rewire_selected_v2(suffix="_bak", disconnect_old=True, keep_old_curve=True)`` を呼べます。
  ``keep_old_curve=False`` にすると、外した元のカーブを削除します(メニューからは既定値で実行します)。
