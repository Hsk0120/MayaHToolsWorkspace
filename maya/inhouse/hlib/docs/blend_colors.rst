色の補間（BlendColors）
============================

Mayaの ``blendColors`` ノードは ``BlendColors`` ラッパーとして取得できます。
各RGB成分を ``color1 * blender + color2 * (1 - blender)`` で補間します。

.. code-block:: python

   import hlib

   blend = hlib.createNode("blendColors", name="colorBlend")
   blend.set_color(1, (1, 0, 0))
   blend.set_color(2, (0, 0, 1))
   blend.set_blender(0.25)
   print(blend.result())           # (0.25, 0.0, 0.75)
   print(blend.color(1).get())      # 入力1のRGB値
   print(blend.blender().get())    # 補間係数

番号はMayaの属性名に合わせて1と2です。``blender=0`` はcolor2、
``blender=1`` はcolor1、``blender=0.5`` は均等な混合になります。
``set_color()`` は有限な3要素を受け付け、色の値を0～1には制限しません。
``set_blender()`` は0～1の有限値を受け付けます。

Plugの接続
----------------

.. code-block:: python

   source = hlib.node("sourceBlend")   # 既存のblendColors
   control = hlib.node("ctrl")
   material = hlib.node("lambert1")

   blend.connect_color(1, source.output())
   blend.connect_blender(control.plug("blendWeight"))
   blend.output().connect(material.plug("color"))

``color()``・``blender()``・``output()`` はPlugを返します。
``result()`` は評価済みのRGBタプルを返します。
接続元はPlugを指定し、``force=True`` の場合だけ既存接続を置き換えます。
接続した補間係数の値はラッパーで制限せず、Mayaの評価に従います。

値の設定と接続はUndo/Redoに対応します。接続済み・ロック済み属性への値の設定は
Mayaのエラーをそのまま通知し、既存接続を自動解除しません。
