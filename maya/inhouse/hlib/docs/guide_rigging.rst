コンストレイント・Joint・IK
============================================================

拘束・ジョイントチェーン・IKハンドルの操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

コンストレイント
----------------

``add_constraint`` は呼び出し元を拘束し、引数のノードを拘束元にします。
次の例はシーンにノードとコンストレイントを追加します。

.. code-block:: python

   driver = hlib.createNode("transform", name="hlibDriver")
   driven = hlib.createNode("transform", name="hlibDriven")
   constraint = driven.add_constraint(driver, "parent", maintainOffset=True)
   print(constraint.targets())
   print(constraint.weight_aliases(), constraint.weights())
   constraint.weight_plugs()[0].set(0.5)

   constraint.set_weight(1.0)             # 全ターゲットに一括設定
   constraint.set_weight(0.2, driver)      # 特定ターゲットのみ（Node/str/複数指定可）

複数の拘束元はリストで指定できます。型名は ``"parent"`` と
``"parentConstraint"`` の両方に対応します。戻り値は ``ParentConstraint`` などの
具象ラッパーで、既存ノードを ``hlib.nodes.Node`` で取得しても同じ型に解決されます。
一度の呼び出しを1つの Undo チャンクとして扱います。

対応する型は parent、point、orient、scale、aim、poleVector、geometry、normal、
tangent、pointOnPoly です。PoleVector は RP IK ハンドル、Tangent は NURBS カーブ、
Geometry／Normal／PointOnPoly は各 Maya コマンドに適した形状を指定してください。
IK ハンドルは ``hlib.node(handle_name)`` から ``IkHandle`` として取得でき、
``handle.add_constraint(driver, "poleVector")`` を使用できます。
``set_weight`` はターゲットを省略すると全ターゲット、指定すると該当ターゲットのみ
ウェイトを設定します。``targets()`` に含まれないターゲットを指定すると ``ValueError``
になります。

追加のキーワード引数は対応する Maya コマンドへ渡します。
例えば ``maintainOffset`` は全種類に共通するフラグではありません。
PointOnPoly のターゲットUV等も Maya の仕様に従い、必要に応じてプラグから設定します。
同じ種類の拘束が既にある場合は、Maya の規則で既存拘束へターゲットが追加される場合があります。

joint チェーンと IK ハンドル
------------------------------

jointOrientをrotateへ移す
^^^^^^^^^^^^^^^^^^^^^^^^^

現在の姿勢を保ち、jointOrientを0にするには次のように実行します。

.. code-block:: python

   joint = hlib.node("leg_RF_knee_IK_jnt")
   joint.joint_orient_to_rotate()

   joints = hlib.ls(selection=True, type="joint")
   joints.joint_orient_to_rotate()

XYZの値を単純加算せず、回転を合成してrotateOrderに合わせたrotateへ変換します。
rotateAxis・移動・スケールと子の姿勢を保持し、度・ラジアンのどちらの角度単位でも使えます。
単体はJoint自身、複数はJoints自身を返し、一回のUndoで戻せます。
複数の場合は全対象を事前検証します。jointOrientが既に0なら変更しません。
入力接続（アニメーションカーブやコンストレイントを含む）・ロックがある対象は
エラーになります。現在フレームの処理であり、アニメーションのベイクは行いません。

スキニング済みjointの回転フリーズ
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

逆方向の操作は ``freeze_rotation()`` です。現在のrotateをjointOrientへ合成し、
rotateを0にします。ジョイントと子の姿勢を保持するため、スキニング後でも使用できます。

.. code-block:: python

   joint = hlib.node("leg_RF_knee_IK_jnt")
   joint.freeze_rotation()

   joints = hlib.ls(selection=True, type="joint")
   joints.freeze_rotation()

回転だけが対象です。translate・scale・rotateAxis・rotateOrderは変更しません。
skinClusterのウェイト・bindPreMatrixや保存済みバインドポーズも変更せず、
現在のメッシュの変形を保ちます。バインドポーズの再設定やアニメーションのベイクではありません。
rotateが既に0の対象は何もしません。それ以外でrotate／jointOrientにロックや入力接続が
ある場合は変更前にエラーになります。単体はJoint自身、複数はJoints自身を返し、
複数jointも一回のUndoで戻せます。

チェーンの取得
^^^^^^^^^^^^^^

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Joint

   cmds.select(clear=True)

   root = Joint(cmds.joint(position=(0, 0, 0)))
   mid = Joint(cmds.joint(position=(2, 0, 0)))
   tip = Joint(cmds.joint(position=(4, 0, 0)))

   print(root.chain_from_here())        # [root, mid, tip]（子が1つの間だけ辿る）
   print(root.chain_from_here(tip))     # 同上。tip まで明示的に辿る

   handle_name = cmds.ikHandle(startJoint=root.name(), endEffector=tip.name(),
                                solver="ikRPsolver")[0]
   handle = hlib.node(handle_name)

   print(root.ik_handles())             # [IkHandle(...)]（自身が start joint の場合のみ）
   print(mid.ik_handles())              # []（途中の joint は対象外）

   print(handle.get_end_joint())            # tip
   print(handle.get_joint_list())            # [root, mid]（末端 joint は含まない）
   print(handle.get_joint_list(include_tip=True))  # [root, mid, tip]

``chain_from_here`` は ``to`` を省略すると、子 joint がちょうど1つの間だけ辿り、
分岐（子が0または2つ以上）に達したところで止まります。``to`` を指定した場合は
そこまでの経路を辿り、``to`` が自身の子孫でなければ ``ValueError`` になります。
``ik_handles`` は自身が **start joint** である IK ハンドルのみを対象にします。
Maya は IK ハンドルの ``startJoint`` への接続からしか joint 側を解決できないため、
チェーン途中の joint では常に空リストになります。``IkHandle.get_joint_list`` は
``cmds.ikHandle(query=True, jointList=True)`` をラップしており、これは仕様上
末端 joint を含まないため、必要なら ``include_tip=True`` を指定してください。
``get_end_joint`` は ikEffector ノードの translate 接続元を辿って解決します。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
