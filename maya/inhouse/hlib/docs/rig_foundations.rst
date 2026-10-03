リグ構築の共通処理
==================

これらのAPIはモジュール名やhrigのレイヤー構造に依存せず、単体で使用できます。
Maya標準ノードを使用し、独自プラグインを作成・ロードしません。

計算ノードの所有と演算
----------------------

.. code-block:: python

   from hlib.nodes import Container
   from hlib.utils.scalarGraph import ScalarGraph

   owner = Container.create("myGraph")
   builder = ScalarGraph(owner)
   total = builder.sum("sum", 2, 3)
   result = builder.multiply("scale", total, 0.5)
   print(result.get())

``Container.createNode(kind, name=None)`` は作成と所有登録を一つのUndoへまとめます。
``add(*nodes)`` は既存ノードを追加し、``members()`` は直接所属するノードを取得します。
削除には既存の ``hlib.delete(owner)`` を使用します。Mayaの削除規則に従うため、
接続が失われた上流network等の自動削除を抑止する機能ではありません。

``ScalarGraph`` は定数、Plugまたはプラグ名を受け取り、改名に追従する出力Plugを返します。
``sum(role, left, right, subtract=False)`` は加減算、
``multiply(role, left, right, operation=1)`` は乗算（1）・除算（2）・累乗（3）、
``condition(role, left, right, yes, no)`` はleft > rightによる選択です。
単位なし数値用であり、ゼロ除算等の数式条件は呼出側で処理します。

Soft IKなどのリグセットアップは ``hrig.setups`` がこれらの基礎APIを組み合わせて構築します。

保存参照とアトリビュート型
------------------------------

``node.plug("members").sourceNodes()`` は配列の接続元を
``{論理インデックス: Node}`` として返します。未接続の要素は含めません。
message配列の ``appendMessage(node)`` は既存の最大インデックスの次へ追加し、
その番号を返します。途中の穴を再利用せず、追加操作はUndo対象です。
Mayaが削除した末尾の要素の過去の番号までは記憶しません。

``Plug.dataType()`` はアトリビュート定義からdoubleLinear等のMaya型名を読み、
値や未作成配列要素を評価しません。型が値に依存するgeneric等はNoneです。
``Plug.type()`` は従来どおりPythonのラッパークラスを返します。

操作形状と単位
--------------

円・カーブの標準作成は ``hlib.createNurbs(type="circle")`` / ``hlib.createCurve`` を使います。
前者はNurbsCurve、後者はTransformを返します。
リグ操作形状の命名・色・親への配置は ``hrig.setups.ControlShape`` の責務です。

``from hlib.utils import units`` で読み込む
``units.distance_to_ui(cm)`` / ``distance_from_ui(value)`` は距離、
``angle_to_ui(rad)`` / ``angle_from_ui(value)`` は角度の単位境界で使います。
``seconds_per_frame()`` は現在の時間単位での1フレームの秒数を返します。
いずれもシーンの単位設定自体は変更しません。

スキンの基本操作
----------------

``SkinCluster.bind(mesh, influences, max_influences=4)`` は未スキニングの
形状をバインドしてラッパーを返します。``deforms(geometry)`` で履歴内の所属を照会できます。
``source_skin.copyWeightsTo(target_skin)`` はclosestPoint、name/closestJointで
近似転送し、ウェイトを正規化します。別のバインド済みskinClusterを指定してください。
形状削減、異なる基準姿勢の補正、LODで使用する骨の選択は行いません。

型付きコマンド入口
------------------

コマンドは ``hlib.cmds`` と ``hlib`` に同じ関数として公開します。
既存の短縮フラグ正規化と入力解決を使い、ノード・アトリビュート名の生文字列を返しません。

.. code-block:: python

   import hlib

   mesh = hlib.createPolygon(type="cube", name="sample")
   attribute = hlib.addAttr(mesh, longName="amount", attributeType="double")
   attributes = hlib.ls("*.amount", recursive=True)  # list[Plug]
   transform = mesh.transform()                  # Transform

``createSet`` はObjectSet、``createIkHandle`` はNode列、
``createPolygon`` は単一のMesh、``addConstraint`` は単一のConstraintを返します。照会には ``weightPlugs()`` / ``targets()`` を使います。
検索・親子付け・時刻/キー・メニュー操作は ``maya.cmds`` を直接使用します。
``cmds.listConnections(connections=True)`` は文字列の平坦なペア列を返します。
必要なNode/Plug変換は使用側で行います。
``getAttr`` はUI単位を維持し、3成分はVector、行列はMatrixを返します。
数値・bool・ラベル等の照会は値を返します。Plug.getの固定単位とは区別してください。
コンポーネント検索はこの入口の対象外です。既存のSelectionやObjectSet.membersを使います。

メニューは ``cmds.menu`` / ``cmds.menuItem``、削除は ``cmds.deleteUI`` を使います。
