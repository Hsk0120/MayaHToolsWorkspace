Outlinerとコントローラーの色
================================

各ノードからOutliner色とDrawing Overrides色を設定できます。
いずれも編集は1回のUndo/Redoに対応します。

Outliner色
----------------

.. code-block:: python

   import hlib

   ctrl = hlib.getNode("ctrl")
   ctrl.set_outliner_color((1, 0.5, 0))
   print(ctrl.get_outliner_color())
   ctrl.set_outliner_color(None)  # カスタム色を無効化

RGBは0～1の3要素です。``useOutlinerColor`` と ``outlinerColor`` を編集します。
Outliner側で色の表示を無効化している場合、ノードアトリビュートを変更しても表示されません。

Shapeの表示色
------------------

.. code-block:: python

   shape = hlib.getNode("ctrlShape")
   shape.set_override_color(13)             # Mayaのインデックス色
   shape.set_override_color((0, 0.5, 1))    # RGB色
   print(shape.get_override_color())
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
画面上の最終色ではありません。対応アトリビュートを持たないノードやロックされたアトリビュートでは
Mayaのエラーを通知します。Jointsなどのコレクションからも同名メソッドを一括実行できます。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

Colorで番号とRGBを扱う
------------------------------

引数なしの ``Color()`` は ``Color(index=0)`` と同じ色番号0で初期化します。
無効状態は ``Color.disabled()`` で明示します。``Colors()`` は空のコレクションです。

``Color`` は表示色を保持する可変オブジェクトです。プロパティを変更すると、
もう一方の表現も同期します。変更だけではシーンには反映されません。

.. code-block:: python

   from hlib.general import Color

   color = Color(index=17)
   print(color.rgb)               # パレットのRGB
   color.rgb = (1, 0.45, 0)
   print(color.index)             # 最も近い色番号
   print(color.mode)              # "rgb"
   shape.set_override_color(color)
   ctrl.set_outliner_color(color)

``index`` を設定すると、その番号のRGBへ変更し ``mode="index"`` になります。
``rgb`` を設定するとRGBをそのまま保持し、最も近い番号を計算して
``mode="rgb"`` になります。近似はRGBの二乗距離で、同距離なら小さい番号を選びます。
色空間の変換は行いません。番号0はDrawing Overridesの既定色指定なので、
RGBからの近似対象は1～31です。番号0のRGBは最終的な画面表示色を表しません。

GUIでは生成時のMayaパレットを保持します。``palette_source`` は ``"maya"`` です。
バッチ・スタンドアロンではパレット照会が利用できないため、標準パレットを使い
``"default"`` になります。バッチではGUIのカスタムパレットを反映しません。
``refresh_palette()`` で明示的に再取得できます。通常のプロパティ操作と
``copy()`` はMayaに問い合わせません。

``get_outliner_color()`` と ``get_override_color()`` はどちらも ``Color`` を返します。
OutlinerはRGB形式、Drawing Overridesは設定中の形式です。無効な場合は
``mode="disabled"``、``index`` と ``rgb`` は ``None`` になります。
``Color.disabled()`` または ``None`` をsetterへ渡すと無効化できます。
従来どおりsetterへRGBタプルや色番号を直接渡すこともできます。
Outlinerへ色番号を渡した場合は対応RGBで設定されます。

取得したColorを変更しても、再度setterを呼ぶまではノードを変更しません。
``BlendColors`` は数値の補間ノードなので、この表示色クラスは使用しません。

複数の色を扱うColors
------------------------------

``Colors`` は ``Color`` と同じモジュールで定義し、順序と重複を保持します。
入力Colorはコピーされ、整数アクセスでは保持中のColorを取得できます。

.. code-block:: python

   from hlib.general import Colors

   colors = Colors([6, 17, (1, 0.45, 0)])
   print(colors.index)          # 各色の番号リスト
   print(colors.rgb)            # 各色のRGBリスト
   colors[0].rgb = (1, 0, 0)   # 一色を変更
   colors.index = [13, 17, 6]  # 全色の番号とRGBを同期
   colors.rgb = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
   copied = colors.copy()
   subset = colors[:2]

``index`` / ``rgb`` への代入は要素数と同じ長さの列を受け取り、
全入力を検証してから更新します。取得したリスト自体を書き換えても反映されません。
``mode`` / ``palette_source`` は各要素の値のリストを返します。
``copy()`` とスライスは、各Colorも独立したコピーになります。
``refresh_palette()`` は各Colorを順に更新し、戻り値はColorのリストです。
途中の照会失敗時は停止し、更新済みの色は自動では戻しません。
これらは保持値の操作で、ノードへの適用は各ノードのsetterで明示します。

ノードコレクションとColors
------------------------------

``Nodes`` と派生コレクション（``Transforms``・``Joints`` 等）の
``get_override_color()`` / ``get_outliner_color()`` は ``Colors`` を返します。
保持順に一色ずつ格納し、無効な色も省略しません。

.. code-block:: python

   joints = hlib.ls(type="joint")
   joints.set_override_color(17)        # 全対象を同じ色にする
   colors = joints.get_override_color()
   if colors:
       colors[0].rgb = (1, 0.45, 0)
   joints.set_override_colors(colors)   # 対応する対象へ一色ずつ反映
   joints.set_outliner_colors(colors)

``set_override_color`` / ``set_outliner_color`` は単一色を全対象へ設定し、
``set_override_colors`` / ``set_outliner_colors`` は色の列を一対一で設定します。
戻り値はコレクション自身です。RGB三要素と色番号三つを混同しないよう、
単色用と要素別用の入口を分けています。

値・件数・全対象のアトリビュートの存在、ロック・入力接続等を変更前に検証します。
異なるDAGインスタンスが同じ色アトリビュートを共有する場合、異なる更新値の指定は
``ValueError`` で拒否します。同じ更新内容なら一度だけ反映します。
空のコレクションへの適用は何もしませんが、不正な単色や件数は空でも拒否します。
通常モードは一回のUndo、``fast=True`` はUndo対象外です。
事前検証後の実行時エラーは停止し、完了済みの変更を自動では戻しません。
