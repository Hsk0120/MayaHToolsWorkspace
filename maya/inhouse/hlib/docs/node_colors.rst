Outlinerとコントローラーの色
================================

各ノードからOutliner色とDrawing Overrides色を設定できます。
いずれも編集は1回のUndo/Redoに対応します。

Outliner色
----------------

.. code-block:: python

   import hlib

   ctrl = hlib.node("ctrl")
   ctrl.set_outliner_color((1, 0.5, 0))
   print(ctrl.outliner_color())
   ctrl.set_outliner_color(None)  # カスタム色を無効化

RGBは0～1の3要素です。``useOutlinerColor`` と ``outlinerColor`` を編集します。
Outliner側で色の表示を無効化している場合、ノード属性を変更しても表示されません。

Shapeの表示色
------------------

.. code-block:: python

   shape = hlib.node("ctrlShape")
   shape.set_override_color(13)             # Mayaのインデックス色
   shape.set_override_color((0, 0.5, 1))    # RGB色
   print(shape.override_color())
   shape.set_override_color(None)          # Drawing Overridesを無効化

色番号は0～31、RGBは0～1の3要素です。設定時は ``overrideEnabled`` を有効化し、
番号なら ``overrideRGBColors=False``、RGBなら ``True`` に切り替えます。
**NoneはoverrideEnabled自体を無効化するため、表示タイプ等のオーバーライドにも影響します。**

指定したノードだけを編集し、Transformから子Shapeへの自動転送はしません。
複数Shapeがある場合は明示的に指定できます。

.. code-block:: python

   for shape in ctrl.shapes():
       shape.set_override_color(17)

取得値はノード自身の設定です。親・表示レイヤー・選択ハイライトなどを含めた
画面上の最終色ではありません。対応属性を持たないノードやロックされた属性では
Mayaのエラーを通知します。Jointsなどのコレクションからも同名メソッドを一括実行できます。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
