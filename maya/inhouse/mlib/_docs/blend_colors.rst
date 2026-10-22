色の補間（BlendColors）
============================

Mayaの ``blendColors`` ノードは ``BlendColors`` ラッパーとして取得できます。
各RGB成分を ``color1 * blender + color2 * (1 - blender)`` で補間します。

.. code-block:: python

   import mlib

   blend = mlib.createNode("blendColors", name="colorBlend")
   blend.setColor(1, (1, 0, 0))
   blend.setColor(2, (0, 0, 1))
   blend.setBlender(0.25)
   print(blend.getResult())           # (0.25, 0.0, 0.75)
   print(blend.getColor(1))      # 入力1のRGB値
   print(blend.getPlug("blender").get())  # 補間係数

番号はMayaのアトリビュート名に合わせて1と2です。``blender=0`` はcolor2、
``blender=1`` はcolor1、``blender=0.5`` は均等な混合になります。
``setColor()`` は有限な3要素を受け付け、色の値を0～1には制限しません。
``setBlender()`` は0～1の有限値を受け付けます。

Plugの接続
----------------

.. code-block:: python

   import mlib

   blend = mlib.createNode("blendColors", name="connectedColorBlend")
   source = mlib.createNode("blendColors", name="sourceColorBlend")
   control = mlib.createNode("transform", name="colorControl")
   control.addAttr("blendWeight", attributeType="double", defaultValue=0.5)
   material = mlib.createNode("lambert", name="colorMaterial")

   blend.connectColor(1, source.getPlug("output"))
   control.getPlug("blendWeight").connectTo(blend.getPlug("blender"))
   blend.getPlug("output").connectTo(material.getPlug("color"))

``getColorPlug(index)`` は入力番号を検証してRGBのPlugを返します。
補間係数と出力は ``getPlug("blender")``・``getPlug("output")`` で参照します。
``getResult()`` は評価済みのRGBタプルを返します。
この例では接続元・接続先をPlugで指定しています。``force=True`` の場合だけ既存接続を置き換えます。
接続した補間係数の値はラッパーで制限せず、Mayaの評価に従います。

値の設定と接続はUndo/Redoに対応します。接続済み・ロック済みアトリビュートへの値の設定は
Mayaのエラーをそのまま通知し、既存接続を自動解除しません。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
``setColor()``・``setBlender()`` と一般のPlugの値更新・接続は、
``fast=True`` を指定するとUndoなしでOpenMayaを使用します。
``connectColor()`` にはfast引数がないため、Undo不要の接続には
``source.getPlug("output").connectTo(blend.getColorPlug(1), fast=True)`` を使います。
対応範囲と制限は :doc:`fast_edit` を参照してください。
