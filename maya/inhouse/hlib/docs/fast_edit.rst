Undo不要の値更新
================

対応する更新メソッドに ``fast=True`` を指定すると、OpenMayaで直接更新します。
省略時は従来のcmdsによるUndo対応処理です。シーン全体のUndo設定や既存履歴は変更しません。

.. code-block:: python

   import hlib

   node = hlib.node("pCube1")
   node.plug("translateX").set(10, fast=True)
   node.set_translate((1, 2, 3), fast=True)

   shape = hlib.node("pCubeShape1")
   shape.vertices().set_position((0, 1, 0), fast=True)
   shape.vertices().mirror(axis="x", fast=True)

   joints = hlib.ls(type="joint")
   joints.freeze_rotation(fast=True)

対応範囲
--------

* Plugの ``set`` / ``reset`` とロック・keyable・channelBoxの設定。
  配列は要素Plugを取得して設定します。
* Transformの行列・translate・rotate・scale・shear・show・hide・形状ミラー。
* Joint / Jointsの ``freeze_rotation`` と ``joint_orient_to_rotate``。
* NodeのOutliner色・override色・属性表示フラグ。
* 頂点・CVの単体／複数の座標設定とミラー、UVの単体／複数の座標設定。
* SkinClusterの ``set_weights`` / ``load_weights`` / ``normalize_weights`` /
  ``set_max_influences``。
* Locator、BlendColors、BlendWeighted、MultMatrix、DecomposeMatrix、
  DistanceBetween、Constraintの値設定メソッド。

対応メソッドから生成される複数形クラスの一括呼出しでも同じ引数を使用できます。
読み取りメソッドやプロパティ代入にはフラグはありません。
ノード作成・削除・接続変更、アニメーションキー編集、ファイル・UI操作などには
このフラグを追加していません。個々のAPIリファレンスのシグネチャで確認してください。

動作と制限
----------

``fast=True`` の変更は、外側を ``undo_chunk`` や ``undo_transaction`` で
囲んでも取り消せません。既存のUndo履歴が同じ値を操作すると、その値が上書きされる場合があります。
途中で例外が起きた場合も、完了済みの直接更新は自動では戻しません。

形状の直接編集は入力履歴のないメッシュ・非周期NURBSカーブに限定します。
スキニング等の入力履歴がある形状と周期カーブは ``NotImplementedError`` になります。
履歴付き形状の座標編集には通常モードを使用してください。
SkinClusterのウェイト更新は履歴付きメッシュでも使用できます。

Plugは数値・単位・enum・文字列・行列・対応するデータ配列を扱います。
未対応の型は ``NotImplementedError``、ロックや入力接続がある値はエラーになります。
OpenMayaの直接設定はcmdsの全フラグを置き換えるものではありません。

頂点・CV・UVではAPIの一括更新、ウェイトではMPlugの直接設定を使用します。
小さな属性更新まで常に高速になる保証はありません。
