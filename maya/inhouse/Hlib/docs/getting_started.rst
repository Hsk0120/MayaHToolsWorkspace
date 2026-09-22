使い始める
==========

実行環境
--------

ワークスペースのバージョン別起動バッチから Maya を起動すると、
``maya/inhouse`` が Python の検索パスに追加されます。
以下は Maya の Script Editor の Python タブで実行する例です。
ノード作成例は現在のシーンにノードを追加します。

ノードと属性
------------

.. code-block:: python

   import Hlib
   from Hlib.decorators.undo import undo_chunk

   with undo_chunk("Hlib example"):
       node = Hlib.create_node("transform", name="hlibExample")
       node.attr("visibility").set(False)

   print(node.name())
   print(node.attr("visibility").get())
   print(Hlib.ls(type="transform"))

``create_node`` は ``maya.cmds.createNode`` にキーワード引数を渡し、
対応するラッパーを返します。既存ノードは ``Hlib.Node("ノード名")`` で取得できます。
``ls`` は ``maya.cmds.ls`` の引数を受け取り、通常はラッパーのリストを返します。
``type="joint"`` と ``type="skinCluster"`` は、それぞれ ``Joints`` と
``SkinClusters`` コレクションを返します。

シーン情報
----------

.. code-block:: python

   from Hlib import Scene

   scene = Scene()
   print(scene.path())  # 未保存なら None
   print(scene.is_modified())

数学型
------

.. code-block:: python

   from Hlib.maths import Vector

   result = Vector(1, 2, 3) + Vector(4, 5, 6)
   print(tuple(result))  # (5.0, 7.0, 9.0)

``maths`` の実装は Maya に依存しません。ただし通常の
``from Hlib.maths import ...`` は親パッケージ ``Hlib`` の初期化を通るため、
この import には Maya 環境が必要です。

再読み込み
----------

.. code-block:: python

   import Hlib
   Hlib.reload_all()

再読み込みは Hlib 内の依存関係をもとに行われます。
古いクラスのインスタンスや ``from ... import ...`` で取得済みの参照は
自動では置き換わらないため、必要な参照・ラッパーを取得し直してください。
