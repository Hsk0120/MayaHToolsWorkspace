基礎コマンドとMaya標準コマンド
================================

``mlib.cmds`` とルートの ``mlib`` は同じ7関数を公開します。
各関数の引数・返却型はAPIリファレンスを参照してください。

.. list-table::
   :header-rows: 1

   * - 関数
     - 役割
   * - ``getNode``
     - 既存対象の所有ノードを、実際の型に対応した参照として取得
   * - ``getPlug``
     - 既存アトリビュートの参照を取得
   * - ``createNode``
     - 型名からノードを作成して参照を返す
   * - ``ls``
     - 検索結果をmlib参照で取得
   * - ``delete``
     - ノードまたはコンポーネントを削除
   * - ``duplicate``
     - 複製結果をmlib参照で取得
   * - ``select``
     - 指定した対象を選択

.. code-block:: python

   import mlib

   a = mlib.createNode("transform", name="commandA")
   b = mlib.createNode("transform", name="commandB")
   a.getPlug("translateX").set(10)
   mlib.select([a, b])
   copy = mlib.duplicate(a, name="commandCopy")
   mlib.delete(copy)
   assert mlib.cmds.getNode is mlib.getNode

値は ``Plug.get()``、状態は ``isLocked()`` 等の専用メソッドで取得します。
``delete`` はPlugを受け付けません。動的アトリビュートは ``plug.delete()``、
所有ノードは ``mlib.delete(plug.getNode())`` で削除します。
入力解決・単位・Mayaとの併用は :doc:`cmds_interop` を参照してください。

Maya標準コマンドの結果を包む
----------------------------

その他のMayaコマンドは ``maya.cmds`` を直接使用し、必要な結果だけを包みます。
コマンド固有の戻り値から、対象ノード・シェイプ・履歴を明示的に選んでください。

.. code-block:: python

   import maya.cmds as cmds
   import mlib

   curve = mlib.getNode(cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0)]))
   mesh = mlib.getNode(cmds.polyCube(constructionHistory=False)[0]).getShape()
   group = mlib.getNode(cmds.group(empty=True, name="group"))
   group.addAttr(longName="amount", attributeType="double")
   curve.setParent(group)
   curve.getShape().getCVs().setPosition((0, 1, 0))

作成フラグの数値はMayaコマンドの単位に従います。
取得した位置やPlugの値は、既定で内部単位のcm・rad・秒です。
シーン全体の単位を変えて両者を同一視しないでください。

複数の更新をまとめる
--------------------

.. code-block:: python

   from mlib.decorator import undoChunk, viewportOff

   with undoChunk("Bake motion"):
       with viewportOff():
           cmds.bakeResults(curve.getFullName(), time=(1, 24), simulation=True)

``viewportOff`` はGUIのメインペインを一時的に非表示にし、元の状態へ戻します。
バッチでは表示を変更しません。Undoチャンクは失敗時の自動ロールバックを意味しません。

選択を保持する
--------------

.. code-block:: python

   from mlib.common import Selection

   saved = Selection.capture()
   for vertices in saved.filter("vertex").getComponents():
       print(vertices.shape, vertices.indices)
   saved.select(mode="replace", missing="skip")

``ls(type="joint")`` と ``ls(type="skinCluster")`` は対応する複数形クラスを返します。
他の型や複数型指定の返却規則は従来どおりです。詳細は :doc:`bulk_collections` と
:doc:`selection_and_channelbox` を参照してください。
