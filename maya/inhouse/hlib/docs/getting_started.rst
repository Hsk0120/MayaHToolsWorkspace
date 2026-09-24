hlib入門
========

hlibの読み込みからノード・アトリビュート操作までの基本を説明します。
機能ごとの詳しい使用例は :doc:`usage` から参照できます。

実行環境
--------

ワークスペースのバージョン別起動バッチから Maya を起動すると、
``maya/inhouse`` が Python の検索パスに追加されます。
以下は Maya の Script Editor の Python タブで実行する例です。
ノード作成例は現在のシーンにノードを追加します。

使用例では ``import hlib`` を基本とし、コマンドは ``hlib.createNode()`` や
``hlib.ls()`` のように hlib 直下から呼び出します。クラスを直接利用する場合は、
``hlib.nodes.Node`` など所属パッケージから取得します。

ノードと属性
------------

通常の編集はコマンド・メソッドの内部でUndoをまとめるため、外側を
``undo_chunk`` で囲む必要はありません。各呼び出しを個別の操作として扱います。

.. code-block:: python

   import hlib

   node = hlib.createNode("transform", name="hlibExample")
   node.plug("visibility").set(False)

   print(node.name())
   print(node.plug("visibility").get())
   print(hlib.ls(type="transform"))

この例では、属性変更とノード作成は別々のUndoになります。
複数の呼び出し全体を一回で戻すツールを開発する場合のみ、
:ref:`tool-undo-chunk` の方法でまとめます。

``createNode`` は ``maya.cmds.createNode`` にキーワード引数を渡し、
対応するラッパーを返します。既存ノードは ``hlib.node("ノード名")`` で取得できます。
``ls`` は ``maya.cmds.ls`` の引数を受け取り、通常はラッパーのリストを返します。
``type="joint"`` と ``type="skinCluster"`` は、それぞれ ``Joints`` と
``SkinClusters`` コレクションを返します。

ノードのアトリビュートは、:meth:`~hlib.nodes.node.Node.plug` で取得した
:class:`~hlib.plugs.plug.Plug` オブジェクトを通して操作します。
本ドキュメントの使用例は ``plug()`` に統一しています。
``attr()`` は既存コードとの互換性のために残している ``plug()`` の別名です。

クラスを直接importして使う
---------------------------

``hlib.createNode``/``hlib.ls``/``hlib.node`` などのコマンドは ``hlib`` 直下で
使える一方、``Node``/``Joint``/``Matrix`` のようなクラス自体は ``hlib`` 直下には
公開されません。所属するサブパッケージから import します。

.. code-block:: python

   import hlib
   from hlib.nodes import Node, Joint
   from hlib.maths import Matrix

   nodes = hlib.ls(sl=True)      # 選択中のノードをラッパーのリストで取得
   joint = Joint("joint1")       # 既存ノードを直接ラップ
   matrix = Matrix()             # 単位行列

``Joint("joint1")`` のように具象クラスを直接呼び出しても、内部は ``Node`` と
同じファクトリパターンで動作します。指定した名前の実際の Maya nodeType が
``joint`` と一致しない場合は、呼び出したクラスではなく実際の型に対応する
ラッパー(例: ``Transform``)が返ります。型を確定させたい場合は
``isinstance()`` で確認するか、素直に ``hlib.node("ノード名")`` /
``Node("ノード名")`` を使ってください。

再読み込み
----------

.. code-block:: python

   import hlib
   hlib.reload()

再読み込みは hlib 内の依存関係をもとに行われます。
古いクラスのインスタンスや ``from ... import ...`` で取得済みの参照は
自動では置き換わらないため、必要な参照・ラッパーを取得し直してください。

次に読むページ
----------------

* :doc:`guide_commands` — シーン編集・選択・キー設定
* :doc:`guide_plugs` — アトリビュートの値・接続・配列
* :doc:`usage` — 機能別ガイドの一覧
