mlib入門
========

参照を取得して編集する
----------------------

以下はMaya内で実行する例です。

.. code-block:: python

   import mlib

   node = mlib.createNode("transform", name="example")
   plug = node.getPlug("translateX")
   plug.set(10)
   print(plug.get())

既存ノードは ``mlib.getNode("名前")`` で取得します。完全DAGパスも指定できます。
``node.tx`` もPlugを返します。値の変更には ``node.tx.set(10)`` を使います。
ノード・プラグ・単一コンポーネントを種類に応じて取得する入口は
:class:`~mlib.core.object.Object` です。

距離・角度・時刻
----------------

オブジェクトと数学型の値は、距離cm・角度rad・時刻秒を基本とします。
Plugの値を現在のUI単位で扱う場合は ``get(uiUnits=True)``・``set(..., uiUnits=True)`` を使います。
``maya.cmds`` のフラグ値はMayaの単位規則に従います。

.. code-block:: python

   node.getPlug("rotateX").set(90, uiUnits=True)  # 現在のUI角度単位
   angle = node.getPlug("rotateX").get()  # 内部単位のrad

.. _tool-undo-chunk:

Undoとfast・safe
--------------------

通常の編集はUndo有効時に記録します。複数の呼出しを1回で戻す場合はまとめます。

.. code-block:: python

   from mlib.decorator import undoChunk

   with undoChunk("editControl"):
       node.setTranslate((1, 2, 3))
       node.getPlug("visibility").set(False)

対応するAPIの ``fast=True`` はUndoなしの直接更新です。Undo設定は変更しません。
未対応条件は各APIを参照してください。
``Plug.set(safe=True)`` は対応する書込み失敗数を返し、成功した成分の更新は残します。
fastがbool以外、または未対応のfast条件では例外になります。

長名と短名
----------

``worldSpace`` と ``ws`` はどちらか一方を指定します。同時指定は値が同じでもTypeErrorです。
他の長短名の併用規則は各APIを参照してください。
署名の ``_UNSET``・``Ellipsis`` は省略判定用の内部値です。

複数のノード
------------

``mlib.ls(type="joint")`` はJoints、``type="skinCluster"`` はSkinClustersを返します。
その他の結果型は :func:`~mlib.cmds.ls` を参照してください。

.. code-block:: python

   joints = mlib.ls(type="joint")
   joints.setRadius(1)

複数形は保持順に実行します。後続の処理が失敗すると先行の変更は残ります。
通常処理は同じUndoチャンクにまとまります。要素別の引数は ``callEach`` で渡します。

クラスと再読み込み
------------------

クラスは ``from mlib.nodes import Joint``、``from mlib.maths import Matrix`` のように取得します。
``Joint("joint1")`` は既存取得、``Joint("newJoint", create=True)`` は新規作成です。
``mlib.reload()`` の後は、import済みのクラスや保持した参照を必要に応じて取得し直します。

API一覧は :doc:`modules`、公開入口は :doc:`autoapi/mlib/index` を参照してください。
