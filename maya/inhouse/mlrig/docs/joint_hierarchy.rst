ジョイント階層の整理
====================

``mlrig.setups.JointHierarchy.delete`` は、ウェイト移送と子の保持を伴う
ジョイント削除です。Maya標準の削除を行う ``mlib.nodes.Joint.delete`` /
``mlib.delete`` とは入口を分けています。

使い方
------

.. code-block:: python

   from mlrig.setups import JointHierarchy

   JointHierarchy.delete(["armHelper_jnt", "legHelper_jnt"])

署名は ``delete(joints, *, safe=False, fast=False)``、戻り値はNoneです。
``joints`` はJoint、ジョイント名、またはその列です。同じ列で名前とNodeを混在させません。
対象の重複をノード単位で除き、深い階層から処理します。

削除するジョイントがskinClusterのinfluenceで、同じskinClusterの祖先influenceがある場合は、
最も近い祖先へウェイトを移送します。移送はsourceの値でtargetを置換する処理で、加算ではありません。
正規化はskinClusterの ``normalizeWeights`` 設定に従います。
移送先がない場合はMaya標準の削除に任せます。
子は削除対象の直接の親へ移し、親がなければworldへ移します。

標準削除との使い分け
--------------------

.. code-block:: python

   import mlib
   from mlrig.setups import JointHierarchy

   joint = mlib.getNode("helper_jnt")
   JointHierarchy.delete(joint)  # ウェイト移送・子の再親付けを伴う整理

``joint.delete()`` / ``mlib.delete(joint)`` はMaya標準の削除で、
ウェイトを移送せず、子階層も標準の規則で削除します。
influence登録だけを外してジョイントを残す場合は、mlibの ``removeInfluence`` を使います。

safe・fast・失敗時の動作
----------------------------------------

``safe=True`` は自身またはDAG子孫にDG接続のあるジョイントを処理から除外します。
スキニング・inverseScale・message等も判定対象なので、ウェイト移送を伴う削除を
保護付きで強制実行する指定ではありません。判定条件はmlibの標準削除と同じです。

通常はMayaコマンドを使用し、全体を一回のUndoで戻せます。
``fast=True`` は対応するOpenMayaの直接更新を使用し、Undoできません。
移送・親変更・削除の条件を事前検証し、fastでは単一geometryのスキンクラスター等の
対応範囲に限定します。中間Transformの生成や独自のinverseScale処理が必要な親変更は、
変更前に ``NotImplementedError`` になります。スキニングレイヤーを持つ
skinClusterの移送は拒否します。

実行中にMaya側のエラーが起きた場合は処理を止め、対象名と段階を含むRuntimeErrorを返します。
完了済みの変更は自動では戻しません。通常モードではUndoで戻してください。
