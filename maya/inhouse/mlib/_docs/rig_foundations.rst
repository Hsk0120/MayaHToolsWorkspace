リグ構築の共通処理
==================

これらのAPIはモジュール名やmlrigのレイヤー構造に依存せず、単体で使用できます。
Maya標準ノードを使用し、独自プラグインを作成・ロードしません。

計算ノードの所有と演算
----------------------

.. code-block:: python

   from mlib.nodes import Container
   from mlib.common.scalarGraph import ScalarGraph

   owner = Container.create("myGraph")
   builder = ScalarGraph(owner)
   total = builder.sum("sum", 2, 3)
   result = builder.multiply("scale", total, 0.5)
   print(result.get())

``Container.createNode(type, name=None)`` は作成と所有登録を一つのUndoへまとめます。
``addMembers(*members)`` は既存ノードを追加し、``getMembers()`` は直接所属するノードを取得します。
削除には既存の ``mlib.delete(owner)`` を使用します。Mayaの削除規則に従うため、
接続が失われた上流network等の自動削除を抑止する機能ではありません。

``ScalarGraph`` は定数、Plugまたはプラグ名を受け取り、改名に追従する出力Plugを返します。
``sum(role, left, right, subtract=False)`` は加減算、
``multiply(role, left, right, operation=1)`` は乗算（1）・除算（2）・累乗（3）、
``condition(role, left, right, yes, no)`` はleft > rightによる選択です。
単位なし数値用であり、ゼロ除算等の数式条件は呼出側で処理します。

Soft IKなどのリグセットアップは ``mlrig.setups`` がこれらの基礎APIを組み合わせて構築します。

保存参照とアトリビュート型
------------------------------

``node.getPlug("members").getSourceNodes()`` は配列の接続元を
``{論理インデックス: Node}`` として返します。未接続の要素は含めません。
message配列の ``appendMessage(node)`` は既存の最大インデックスの次へ追加し、
その番号を返します。途中の穴を再利用せず、追加操作はUndo対象です。
Mayaが削除した末尾の要素の過去の番号までは記憶しません。

``Plug.getDataType()`` はアトリビュート定義からdoubleLinear等のMaya型名を読み、
値や未作成配列要素を評価しません。型が値に依存するgeneric等はNoneです。
``Plug.getType()`` は従来どおりPythonのラッパークラスを返します。

操作形状と単位
--------------

円・カーブの標準作成は ``cmds.circle`` / ``cmds.curve`` を使います。
``mlib.getNode(cmds.circle()[0]).getShape()`` はNurbsCurve、
``mlib.getNode(cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0)]))`` はTransformです。
標準作成コマンドへ渡す距離はUI単位です。
リグ操作形状の命名・色・親への配置は ``mlrig.setups.ControlShape`` の責務です。

``from mlib.common import units`` で読み込む
``units.distanceToUi(cm)`` / ``distanceFromUi(value)`` は距離、
``angleToUi(rad)`` / ``angleFromUi(value)`` は角度の単位境界で使います。
``secondsPerFrame()`` は現在の時間単位での1フレームの秒数を返します。
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

``getNode``・``getPlug``・``createNode``・``ls``・``delete``・``duplicate``・``select`` の
7入口を ``mlib.cmds`` と ``mlib`` に同じ関数として公開します。
取得・生成結果のNode/Plugは実型に対応する参照です。
形状等の専用生成は標準cmdsを使い、必要な参照型へ明示的に変換します。

.. code-block:: python

   import mlib
   from maya import cmds
   from mlib.decorator import undoChunk

   with undoChunk("sampleGeometry"):
       transform = mlib.getNode(cmds.polyCube(name="sample")[0])
       mesh = transform.getShape()  # Mesh
       attribute = transform.addAttr("amount", attributeType="double")
   attributes = mlib.ls("*.amount", recursive=True)  # list[Plug]

``cmds.sets`` はセット名、``cmds.ikHandle`` はハンドル・effector等の名前を返します。
結果を ``mlib.getNode`` で個別に参照へ変換し、形状にはTransformから ``getShape()`` で進みます。
アトリビュートの追加は ``node.addAttr``、拘束の作成は
``target.addConstraint(sources, type="parent", maintainOffset=False)`` を使用します。
Constraintの照会には ``getWeightPlugs()`` / ``getTargets()`` を使います。
標準コマンドと複数のオブジェクト操作を1回のUndoにまとめる場合は、外側を
例の ``undoChunk`` で囲みます。参照取得はUndoを追加しません。
Maya固有の履歴・接続照会、親子付け・時刻/キー・メニュー操作は ``maya.cmds`` を直接使用します。
``cmds.listConnections(connections=True)`` は文字列の平坦なペア列を返します。
必要なNode/Plug変換は使用側で行います。
``getPlug(target)`` は型付きPlugを返します。値は ``get()`` で内部単位、
``get(uiUnits=True)`` でUI単位として取得します。状態には ``isLocked()`` 等の
専用照会を使います。Maya固有のtime等の照会は ``cmds.getAttr`` を使用します。
コンポーネントは ``Selection.capture()`` や ``ObjectSet.getMembers()`` から取得できます。

メニューは ``cmds.menu`` / ``cmds.menuItem``、削除は ``cmds.deleteUI`` を使います。
