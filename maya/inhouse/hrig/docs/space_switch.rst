参照空間の切替
========================

``hrig.setups.SpaceSwitch`` は専用transformを参照ノードまたはワールドへ
追従させる共通ライブラリです。標準の ``choice`` と ``multMatrix`` を使用し、
プラグインや実行スクリプトをシーンへ埋め込みません。

.. code-block:: python

   import hlib
   from hrig.setups import SpaceSwitch

   root = hlib.createNode("transform", name="root")
   buffer = hlib.createNode("transform", name="control_space", parent=root)
   control = hlib.createNode("transform", name="control", parent=buffer)
   switch = SpaceSwitch.create(buffer)
   switch.add("local", root)
   switch.add("world")
   switch.switch("world")
   print(switch.labels(), switch.current())

``create`` にはローカルTRSが恒等値で、offsetParentMatrixが未接続の専用transformを
渡します。初期オフセットと参照先ワールド行列、実親の逆行列から
offsetParentMatrixを計算します。親の付け替えやbufferのTRS編集は対象外です。
``switch`` は切替先のオフセットを更新し、bufferのワールド姿勢と子の
ローカルチャンネルを保持します。通常の移動追従はDGだけで評価されます。

保存後は ``SpaceSwitch(buffer)`` で再取得できます。名前の変更は接続から追跡します。
``nodes()`` は所有ノードを返し、外部の参照先は含めません。削除は利用側が管理します。
空間名は英字で始まる英数字・アンダースコアとし、重複名は拒否します。

制限
------------------------

これは停止中に行う構成操作です。選択先のオフセットを編集するため、アニメーション中の
切替キーや過去フレームの姿勢保持は実装していません。時系列の切替には別途ベイクや
キー付きオフセットの設計が必要です。

自己・子孫・通常のDG/DAG依存による循環は登録時に拒否します。IKソルバーなど
暗黙の内部依存まで汎用的に検出するものではありません。リグ側でも変形結果を
自身の操作空間へ入力しない制約を設けてください。参照先の削除・bufferの再親子付け・
インスタンス階層の利用はサポート対象外です。
