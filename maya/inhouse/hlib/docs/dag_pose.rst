保存姿勢とバインドポーズ
============================

``dagPose`` ノードは :class:`~hlib.nodes.dagPose.DagPose` として取得できます。
通常の保存姿勢とバインドポーズは同じクラスで扱い、``is_bind_pose()`` で区別します。

既存のバインドポーズを取得する
--------------------------------

.. code-block:: python

   import hlib

   pose = hlib.node("bindPose1")
   print(pose.is_bind_pose())
   print(pose.members())          # 保存されているTransform・Joint
   print(pose.skin_clusters())    # bindPoseとして参照するSkinCluster
   print(pose.is_at_pose())
   print(pose.not_at_pose())      # 保存姿勢と異なるメンバー

skinClusterから接続先を取得する場合は、次のように指定します。
未接続なら ``None`` を返します。

.. code-block:: python

   skin = hlib.node("skinCluster1")
   pose = skin.bind_pose()
   if pose is not None:
       skin.restore_bind_pose()   # 既定ではワールド姿勢を復元

``skin.reset_bind_pose()`` は、このskinClusterのinfluenceだけの保存姿勢を更新します。
ポーズに含まれないinfluenceがある場合は、更新前に例外を出します。
``restore_bind_pose()`` は接続されたポーズの全メンバーを復元します。
ポーズを共有している場合、他のskinClusterにも影響します。
どちらもポーズ未接続時は ``RuntimeError`` となり、ポーズの自動作成はしません。
``reset_bind_pose()`` は ``bindPreMatrix`` やウェイトを変更しません。

``SkinClusters`` からも同名メソッドを呼べます。戻り値は保持順のリストで、
一括編集は1回のUndoにまとまります。
クラスから直接取得する ``hlib.nodes.DagPose.from_skin_cluster("skinCluster1")`` も利用できます。

姿勢の保存と復元
----------------------

.. code-block:: python

   pose = hlib.nodes.DagPose.create("root_joint", name="rigPose")
   pose.restore()                 # 保存時のローカル姿勢へ復元
   pose.restore(ws=True)          # Mayaのglobalオプションで復元

``create()`` は現在の選択に依存しません。既定では指定対象の階層を保存し、
``hierarchy=False`` なら指定したメンバーのみを保存します。
バインドポーズとして保存する場合は ``bind_pose=True`` を指定します。
これだけではskinClusterの作成や、既存skinClusterへの接続は行いません。
復元はMayaの ``dagPose`` コマンドを使用し、ロックや入力接続を解除しません。

保存行列とメンバーの編集
----------------------------

.. code-block:: python

   local_matrix = pose.get_matrix("root_joint")
   world_matrix = pose.get_matrix("root_joint", ws=True)
   indices = pose.member_indices()
   index = pose.member_index("root_joint")

   pose.add("extra_joint")        # 現在の姿勢で追加
   pose.reset("extra_joint")      # このメンバーの保存姿勢を現在の姿勢に更新
   pose.reset()                   # 全メンバーの保存姿勢を更新
   pose.remove("extra_joint")     # ポーズから除外。Joint自体は削除しない

``get_matrix()`` が返すのは保存時の :class:`~hlib.maths.matrix.Matrix` です。
配列の論理番号は欠番を含むため、``members()`` のリスト位置とは区別してください。
``remove()`` で指定したノードが残るメンバーの親として必要な場合は、Mayaが保持することがあります。

``restore()`` はノードを保存姿勢へ戻し、``reset()`` は保存内容を更新します。
**reset()はskinClusterのbindPreMatrixを変更しません。**
スキニングの基準を再設定する操作とは異なります。

作成・復元・更新・メンバー追加/削除は、それぞれ1回のUndo/Redoに対応します。
通常の呼び出しで外側に ``undo_chunk`` を指定する必要はありません。
