保存姿勢とバインドポーズ
============================

``dagPose`` ノードは :class:`~hlib.nodes.dagPose.DagPose` として取得できます。
通常の保存姿勢とバインドポーズは同じクラスで扱い、``isBindPose()`` で区別します。

既存のバインドポーズを取得する
--------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import hlib

   pose = hlib.getNode("bindPose1")
   print(pose.isBindPose())
   print(pose.members())          # 保存されているTransform・Joint
   print(pose.skinClusters())    # bindPoseとして参照するSkinCluster
   print(pose.isAtPose())
   print(pose.notAtPose())      # 保存姿勢と異なるメンバー

skinClusterから接続先を取得する場合は、次のように指定します。
未接続なら ``None`` を返します。

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   skin = hlib.getNode("skinCluster1")
   pose = skin.bindPose()
   if pose is not None:
       skin.restoreBindPose()   # 既定ではワールド姿勢を復元

``skin.resetBindPose()`` は、このskinClusterのinfluenceだけの保存姿勢を更新します。
ポーズに含まれないinfluenceがある場合は、更新前に例外を出します。
``restoreBindPose()`` は接続されたポーズの全メンバーを復元します。
ポーズを共有している場合、他のskinClusterにも影響します。
どちらもポーズ未接続時は ``RuntimeError`` となり、ポーズの自動作成はしません。
``resetBindPose()`` は ``bindPreMatrix`` やウェイトを変更しません。

``SkinClusters`` からも同名メソッドを呼べます。戻り値は保持順のリストで、
一括編集は1回のUndoにまとまります。
クラスから直接取得する ``hlib.nodes.DagPose.fromSkinCluster("skinCluster1")`` も利用できます。

姿勢の保存と復元
----------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   pose = hlib.nodes.DagPose.create("root_joint", name="rigPose")
   pose.restore()                 # 保存時のローカル姿勢へ復元
   pose.restore(space=MSpace.kWorld)          # Mayaのglobalオプションで復元

``create()`` は現在の選択に依存しません。既定では指定対象の階層を保存し、
``hierarchy=False`` なら指定したメンバーのみを保存します。
バインドポーズとして保存する場合は ``bindPose=True`` を指定します。
これだけではskinClusterの作成や、既存skinClusterへの接続は行いません。
復元はMayaの ``dagPose`` コマンドを使用し、ロックや入力接続を解除しません。

保存行列とメンバーの編集
----------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   local_matrix = pose.getMatrix("root_joint")
   world_matrix = pose.getMatrix("root_joint", space=MSpace.kWorld)
   indices = pose.memberIndices()
   index = pose.memberIndex("root_joint")

   pose.addMembers("extra_joint")        # 現在の姿勢で追加
   pose.reset("extra_joint")      # このメンバーの保存姿勢を現在の姿勢に更新
   pose.reset()                   # 全メンバーの保存姿勢を更新
   pose.removeMembers("extra_joint")     # ポーズから除外。Joint自体は削除しない

``getMatrix()`` が返すのは保存時の :class:`~hlib.maths.matrix.Matrix` の複製です
(om2.MMatrix の派生で、変更してもポーズには反映されません)。
配列の論理番号は欠番を含むため、``members()`` のリスト位置とは区別してください。
``remove()`` で指定したノードが残るメンバーの親として必要な場合は、Mayaが保持することがあります。

``restore()`` はノードを保存姿勢へ戻し、``reset()`` は保存内容を更新します。
**reset()はskinClusterのbindPreMatrixを変更しません。**
スキニングの基準を再設定する操作とは異なります。

作成・復元・更新・メンバー追加/削除は、それぞれ1回のUndo/Redoに対応します。
通常の呼び出しで外側に ``undo_chunk`` を指定する必要はありません。
