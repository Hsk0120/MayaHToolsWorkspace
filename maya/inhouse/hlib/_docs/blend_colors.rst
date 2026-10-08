色の補間（BlendColors）
============================

Mayaの ``blendColors`` ノードは ``BlendColors`` ラッパーとして取得できます。
各RGB成分を ``color1 * blender + color2 * (1 - blender)`` で補間します。

.. code-block:: python

   import hlib

   blend = hlib.createNode("blendColors", name="colorBlend")
   blend.setColor(1, (1, 0, 0))
   blend.setColor(2, (0, 0, 1))
   blend.setBlender(0.25)
   print(blend.getResult())           # (0.25, 0.0, 0.75)
   print(blend.getColor(1))      # 入力1のRGB値
   print(blend.getBlenderPlug().get())    # 補間係数

番号はMayaのアトリビュート名に合わせて1と2です。``blender=0`` はcolor2、
``blender=1`` はcolor1、``blender=0.5`` は均等な混合になります。
``setColor()`` は有限な3要素を受け付け、色の値を0～1には制限しません。
``setBlender()`` は0～1の有限値を受け付けます。

Plugの接続
----------------

.. code-block:: python

   source = hlib.getNode("sourceBlend")   # 既存のblendColors
   control = hlib.getNode("ctrl")
   material = hlib.getNode("lambert1")

   blend.connectColor(1, source.getOutputPlug())
   blend.connectBlender(control.getPlug("blendWeight"))
   blend.getOutputPlug().connectTo(material.getPlug("color"))

``getColorPlug()``・``getBlenderPlug()``・``getOutputPlug()`` はPlugを返します。
``getResult()`` は評価済みのRGBタプルを返します。
接続元はPlugを指定し、``force=True`` の場合だけ既存接続を置き換えます。
接続した補間係数の値はラッパーで制限せず、Mayaの評価に従います。

値の設定と接続はUndo/Redoに対応します。接続済み・ロック済みアトリビュートへの値の設定は
Mayaのエラーをそのまま通知し、既存接続を自動解除しません。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
