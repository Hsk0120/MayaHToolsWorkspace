ノードの複数形API
============================================================

Joints・SkinClustersに、単体の公開インスタンスメソッドを
同名で一括実行する入口を追加しました。JointsではJointが継承するTransform・Nodeの
メソッドも使えます。登録時にクラスへメソッドを追加するため、dirでも確認できます。

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import hlib

   joints = hlib.nodes.Joints(["joint1", "joint2"])
   positions = joints.getTranslation(space=MSpace.kWorld)
   joints.setTranslation((1, 2, 3), space=MSpace.kWorld)
   matrices = joints.getMatrix(space=MSpace.kWorld)
   joint_orients = joints.getJointOrient()
   joints.setAttributeFlags(["visibility"], keyable=False)

引数は単体メソッドと同じで、全要素へ同じ引数を渡します。
同じ実装のメソッドには引数の形の検証を共有しますが、派生クラスで異なる
メソッドが呼ばれる場合は個別に検証し、全件の検証後に実行します。
ノードの有効性・ロックなどの状態は、各操作時に確認します。
公開対象を明示した転送メソッドは、照会・生成結果が必要な操作では保持順の結果リスト、
通常の更新ではコレクション自身を返します。callEachも同じ規則です。
照会結果がリストなら二重リストを保持し、Noneも除外しません。
空コレクションでも照会は空リスト、更新は自身です。
アトリビュート名の暗黙アクセスは転送しません。アトリビュート取得には ``joints.plug("translateX")`` を使います。

要素別の引数
------------------------------------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   joints.callEach(
       "setTranslation",
       [((1, 2, 3),), ((4, 5, 6),)],
       [{"space": MSpace.kWorld}, {"space": MSpace.kWorld}],
   )
   joints.callEach("rename", [("arm_joint",), ("leg_joint",)])

callEachのargumentsは、各要素への位置引数タプルを並べた列です。
引数列・キーワード引数列の件数とシグネチャは実行前に全件確認します。
値の意味やMaya側の制約は単体メソッドで検証するため、途中で失敗する場合があります。
共有引数には再利用可能なlist/tupleを推奨します。消費されるiteratorは各要素用に分けます。

コレクション固有の操作
------------------------------------------------------------

* Joints.delete: ウェイト移送と子の退避を行う既存の削除処理。
* Joints.skinClusters: 重複を除いたSkinClustersを返す。
* Joints.names()、sortedByDepth(): 名前の一覧・階層順のコレクションを返す。
* Joints.jointOrientToRotate、freezeRotation: 全対象を事前検証し、Joints自身を返す。
* SkinClusters.removeInfluences: 保持するskinClusterのinfluence解除。戻り値は自身です。joint削除はJoints.deleteを使います。

自動追加APIより既存メソッドを優先します。同名で意味が異なる場合は、
callEachで単体メソッドを明示できます。
単体のclassmethod・staticmethod・非公開メソッド・特殊メソッドは一括転送しません。
全クラスにlen・添字・同型sliceを用意しています。

SkinClusters
------------------------------------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   skins = joints.skinClusters()
   influences_by_skin = skins.influences()
   flags = skins.hasInfluence("joint1")
   skins.callEach("dumpWeights", [("C:/data/skinA.json",), ("C:/data/skinB.json",)])

dumpWeights/loadWeightsはパスの取り違えを避けるため、同一引数の一括転送から除外し、
callEachで要素別に指定します。パスの重複や上書きの判断は呼び出し側で行います。

失敗とUndo
------------------------------------------------------------

ノードの一括操作は内部で1回のUndoチャンクにまとめます。失敗時は要素番号と
メソッド名を含むRuntimeErrorを返し、元の例外を原因として保持します。
後続要素は実行しません。完了済み操作の自動ロールバックは行いません。
Pluginのロード・アンロードとファイル入出力はシーンUndo対象外です。

コンポーネントの一括座標編集は :doc:`component_collections` を参照してください。
Selectionは異種対象の取得時点の集合で、単一の単体型に対応しないため、この自動転送の対象外です。
ノードの集合はNodes → DagNodes → Transforms → Jointsの順で継承します。
単体メソッドの追加だけでは公開APIは増えず、bulk_apiのreads/writesで明示登録します。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。


ジョイントを残してinfluenceを解除
------------------------------------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   joints = hlib.ls(selection=True, type="joint")
   skins = joints.skinClusters()
   skins.removeInfluences(joints)  # jointノード・親子関係は残す

``removeInfluences(joints)`` と同じ処理です。保持するskinClusterだけを対象にし、
未登録の組は無視します。既定では最も近い祖先influenceへウェイトを加算し、
祖先がない場合はMaya標準の再配分を使います。
``transfer_to_parent=False`` で標準解除のみを指定できます。
各skinClusterに最低1つのinfluenceが残るか編集前に検査します。
全体は一回のUndoで戻せます。実行途中の例外は伝播し、自動ロールバックはしません。
ノード自体を削除する場合は ``joints.delete()`` を使用してください。
