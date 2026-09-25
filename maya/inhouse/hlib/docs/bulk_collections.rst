ノード・プラグインの複数形API
============================================================

Joints・SkinClusters・Pluginsに、単体の公開インスタンスメソッドを
同名で一括実行する入口を追加しました。JointsではJointが継承するTransform・Nodeの
メソッドも使えます。登録時にクラスへメソッドを追加するため、dirでも確認できます。

.. code-block:: python

   import hlib

   joints = hlib.nodes.Joints(["joint1", "joint2"])
   positions = joints.get_translate(ws=True)
   joints.set_translate((1, 2, 3), ws=True)
   matrices = joints.get_matrix(ws=True)
   joint_orients = joints.joint_orient()
   joints.set_attr_flags(["visibility"], keyable=False)

引数は単体メソッドと同じで、全要素へ同じ引数を渡します。
自動追加されたメソッドの戻り値は保持順のリストです。設定メソッドも各単体の戻り値のリストを返します。
リストを返す単体メソッドでは二重リストになります。Noneも削除しません。
空コレクションでは空リストです。uuid/full_name等の読取プロパティもリストになります。
属性名の暗黙アクセスは転送しません。属性取得には ``joints.plug("translateX")`` を使います。

要素別の引数
------------------------------------------------------------

.. code-block:: python

   joints.call_each(
       "set_translate",
       [((1, 2, 3),), ((4, 5, 6),)],
       [{"ws": True}, {"ws": True}],
   )
   joints.call_each("rename", [("arm_joint",), ("leg_joint",)])

call_eachのargumentsは、各要素への位置引数タプルを並べた列です。
引数列・キーワード引数列の件数とシグネチャは実行前に全件確認します。
値の意味やMaya側の制約は単体メソッドで検証するため、途中で失敗する場合があります。
共有引数には再利用可能なlist/tupleを推奨します。消費されるiteratorは各要素用に分けます。

既存の固有メソッドは維持
------------------------------------------------------------

* Joints.delete: ウェイト移送と子の退避を行う既存の削除処理。
* Joints.skin_clusters: 重複を除いたSkinClustersを返す。
* Joints.names、sorted_by_depth: 既存の型・意味を維持する。
* Joints.joint_orient_to_rotate、freeze_rotation: 全対象を事前検証し、Joints自身を返す。
* SkinClusters.gather/apply/finalize/remove_joints/remove_influences: 既存の移送操作。
* Plugins.loaded: ロード済みプラグインからコレクションを作る既存classmethod。

自動追加APIより既存メソッドを優先します。同名で意味が異なる場合は、
call_eachで単体メソッドを明示できます。
単体のclassmethod・staticmethod・非公開メソッド・特殊メソッドは一括転送しません。
全クラスにlen・添字・同型sliceを用意しています。

SkinClustersとPlugins
------------------------------------------------------------

.. code-block:: python

   skins = joints.skin_clusters()
   influences_by_skin = skins.influences()
   flags = skins.has_influence("joint1")
   skins.call_each("dump_weights", [("C:/data/skinA.json",), ("C:/data/skinB.json",)])

   from hlib.plugins import Plugins
   plugins = Plugins(["pluginA", "pluginB"])
   states = plugins.is_loaded()
   # 実際にロードしたい場合:
   # plugins.ensure_loaded()

dump_weights/load_weightsはパスの取り違えを避けるため、同一引数の一括転送から除外し、
call_eachで要素別に指定します。パスの重複や上書きの判断は呼び出し側で行います。

失敗とUndo
------------------------------------------------------------

ノードの一括操作は内部で1回のUndoチャンクにまとめます。失敗時は要素番号と
メソッド名を含むRuntimeErrorを返し、元の例外を原因として保持します。
後続要素は実行しません。完了済み操作の自動ロールバックは行いません。
Pluginのロード・アンロードとファイル入出力はシーンUndo対象外です。

コンポーネントの一括座標編集は :doc:`component_collections` を参照してください。
Selectionは異種対象の取得時点の集合で、単一の単体型に対応しないため、この自動転送の対象外です。
今回、未存在のNodesやTransforms等の新しいコレクションは追加していません。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
