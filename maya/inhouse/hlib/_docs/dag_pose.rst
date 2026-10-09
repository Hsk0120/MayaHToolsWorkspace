保存姿勢とバインドポーズ
============================

``dagPose`` ノードは :class:`~hlib.nodes.dagPose.DagPose` として取得できます。
通常の保存姿勢とバインドポーズは同じクラスで扱い、``bindPose()`` で区別します。

既存のバインドポーズを取得する
--------------------------------

Mesh・NURBSカーブ/サーフェス等のShape、またはそのTransformから取得できます。

.. code-block:: python

   import hlib

   geometry = hlib.node("pCube1")
   skins = geometry.skinClusters()  # list[SkinCluster]
   poses = geometry.bindPoses()     # list[DagPose]

   # 複数形状のポーズをまとめる場合
   other = hlib.node("nurbsSurface1")
   if poses:
       sources = other.bindPoses()
       if sources:
           poses[0].merge(sources)

``skinClusters()`` は対象Shapeが出力先であるSkinClusterを返します。
Transformでは直下の非中間Shapeだけを検索し、子Transform以下は検索しません。
Shape順・各Shapeの上流幅優先順で返し、重複を除きます。
単なる履歴検索と異なり、BlendShapeターゲット等の別形状側のSkinClusterは除外します。
Shapeを直接指定した場合は中間ShapeでもそのShape自身を対象にします。
``bindPoses()`` は取得したSkinClusterの順にポーズを返し、共有ポーズの重複と未接続を
除きます。どちらも対象なしは ``[]`` で、選択やUndo履歴を変更しません。
Jointの既存 ``skinClusters()`` はinfluence接続照会のままで、Jointの
``bindPoses()`` もその結果を使用します。

.. code-block:: python

   import hlib

   pose = hlib.node("bindPose1")
   print(pose.bindPose())
   print(pose.members())          # 保存されているTransform・Joint
   print(pose.skinClusters())    # bindPoseとして参照するSkinCluster
   print(pose.atPose())
   print(pose.notAtPose())      # 保存姿勢と異なるメンバー

skinClusterから接続先を取得する場合は、次のように指定します。
未接続なら ``None`` を返します。

.. code-block:: python

   skin = hlib.node("skinCluster1")
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

   pose = hlib.nodes.DagPose.create("root_joint", name="rigPose")
   pose.restore()                 # 保存時のローカル姿勢へ復元
   pose.restore(ws=True)          # Mayaのglobalオプションで復元

``create()`` は現在の選択に依存しません。既定では指定対象の階層を保存し、
``hierarchy=False`` なら指定したメンバーのみを保存します。
バインドポーズとして保存する場合は ``bindPose=True`` を指定します。
これだけではskinClusterの作成や、既存skinClusterへの接続は行いません。
復元はMayaの ``dagPose`` コマンドを使用し、ロックや入力接続を解除しません。

保存行列とメンバーの編集
----------------------------

.. code-block:: python

   local_matrix = pose.matrix("root_joint")
   world_matrix = pose.matrix("root_joint", ws=True)
   indices = pose.memberIndices()
   index = pose.memberIndex("root_joint")

   pose.addMembers("extra_joint")        # 現在の姿勢で追加
   pose.reset("extra_joint")      # このメンバーの保存姿勢を現在の姿勢に更新
   pose.reset()                   # 全メンバーの保存姿勢を更新
   pose.removeMembers("extra_joint")     # ポーズから除外。Joint自体は削除しない

``matrix()`` が返すのは保存時の :class:`~hlib.maths.matrix.Matrix` の複製です
(om2.MMatrix の派生で、変更してもポーズには反映されません)。
配列の論理番号は欠番を含むため、``members()`` のリスト位置とは区別してください。
``remove()`` で指定したノードが残るメンバーの親として必要な場合は、Mayaが保持することがあります。

``restore()`` はノードを保存姿勢へ戻し、``reset()`` は保存内容を更新します。
**reset()はskinClusterのbindPreMatrixを変更しません。**
スキニングの基準を再設定する操作とは異なります。

作成・復元・更新・メンバー追加/削除は、それぞれ1回のUndo/Redoに対応します。
通常の呼び出しで外側に ``undoChunk`` を指定する必要はありません。

複数のポーズを統合する
------------------------------

``merge(sources, *, currentPose=False, deleteSources=True)`` は、自身を統合先として
メンバーと保存情報をまとめ、統合元を参照するskinClusterの接続先を自身へ変更します。
戻り値は自身です。sourcesは単体の名前/Node、またはそれらの同種のリストを受け付けます。
名前とNodeの混在・空入力は拒否し、自身と重複指定は無視します。

.. code-block:: python

   import hlib

   target = hlib.node("bindPose1")
   target.merge(["bindPose2", "bindPose3"])

   # 現在姿勢で統合し、元のポーズを削除する場合
   target.merge(
       ["bindPose4", "bindPose5"],
       currentPose=True,
       deleteSources=True,
   )

既定では **保存済みの姿勢** を引き継ぎます。現在バインド姿勢へ戻す必要はありません。
ワールド行列だけでなく、ローカルのxform情報（jointOrient・pivot・回転順等）、
保存時の親関係と復元範囲を保持します。同じメンバーの保存情報が競合した場合は、
変更前にValueErrorを出します。数値比較の絶対許容誤差は ``1e-10`` です。
通常ポーズ同士も統合できますが、通常ポーズとバインドポーズの混在は拒否します。

``currentPose=True`` は **統合先の既存メンバーを含む全対象** を現在の姿勢・階層で
保存します。保存済み姿勢の競合は無視し、復元に必要な親をMaya標準処理で含めます。
現在のジョイント姿勢、スキンウェイト、skinClusterの ``bindPreMatrix`` は変更しません。
スキニングのバインド基準を再設定する操作ではありません。
``joint.bindPose`` からの標準入力は保存行列として読み取り、追加/更新する行は
独立した値として保存します。joint側の ``bindPose`` アトリビュートは変更しません。

既定の ``deleteSources=True`` はskinClusterの再接続後に元ポーズを削除します。
``False`` を明示すると元ポーズを残します（skinClusterの参照先は統合先へ変更）。
``True`` では、メンバー・保存親・joint.bindPoseの標準接続とskinCluster.bindPose以外の
外部接続がある元ポーズは変更前に拒否します。
編集対象のポーズ/skinClusterのロック・参照、削除対象のロック・参照、
インスタンスのメンバーや標準外の保存データ入力は未対応です。

統合全体は1回のUndo/Redoに対応し、途中の編集失敗時はUndoで巻き戻します。
Undoが有効な状態で使用してください。``fast`` フラグはありません。
