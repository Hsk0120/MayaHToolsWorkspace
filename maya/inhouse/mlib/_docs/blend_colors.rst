色の補間（BlendColors）
============================

Mayaの ``blendColors`` ノードは ``BlendColors`` ラッパーとして取得できます。
型登録とNodeの共通操作を持ち、入力・出力はMaya標準名のPlugで扱います。
各RGB成分を ``color1 * blender + color2 * (1 - blender)`` で補間します。

.. code-block:: python

   import mlib
   from mlib.decorator import undoChunk

   blend = mlib.createNode("blendColors", name="colorBlend")
   with undoChunk("colorBlendInputs"):
       blend.getPlug("color1").set((1, 0, 0))
       blend.getPlug("color2").set((0, 0, 1))
       blend.getPlug("blender").set(0.25)
   print(tuple(blend.getPlug("output").get()))  # (0.25, 0.0, 0.75)
   print(blend.getPlug("color1").get())  # 入力1の値
   print(blend.getPlug("blender").get())  # 補間係数

``blender=0`` はcolor2、``blender=1`` はcolor1、``blender=0.5`` は均等な混合です。
番号を受け取る専用アクセサーや、色・補間係数の独自検証は提供しません。
値の型・制限・例外はMayaのアトリビュートとPlugの仕様に従います。
``get()`` の戻り値を専用のRGBタプルへ変換せず、タプルが必要な例では明示的に変換しています。

Plugの接続
----------------

.. code-block:: python

   blend = mlib.createNode("blendColors", name="connectedColorBlend")
   source = mlib.createNode("blendColors", name="sourceColorBlend")
   control = mlib.createNode("transform", name="colorControl")
   control.addAttr("blendWeight", attributeType="double", defaultValue=0.5)
   material = mlib.createNode("lambert", name="colorMaterial")

   with undoChunk("colorBlendConnections"):
       source.getPlug("output").connectTo(blend.getPlug("color1"))
       control.getPlug("blendWeight").connectTo(blend.getPlug("blender"))
       blend.getPlug("output").connectTo(material.getPlug("color"))

入力は ``color1/color2``、補間係数は ``blender``、出力は ``output`` です。
``force=True`` の場合だけ既存接続を置き換えます。接続した値の計算はMayaに従います。
値の設定で既存接続を自動解除しません。ロックや入力接続による失敗は例外として伝播します。

通常のPlug設定・接続はUndo/Redoに対応します。複数の変更を1回で戻す場合は、
例のように利用側で ``undoChunk`` を使います。
Undoが不要な更新には ``set(..., fast=True)`` / ``connectTo(..., fast=True)`` を指定します。
外側のUndoチャンクがあってもfastの変更は取り消せません。
対応範囲と制限は :doc:`fast_edit` を参照してください。
