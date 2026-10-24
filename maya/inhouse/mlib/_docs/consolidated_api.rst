取得の統合とUndo・fast
======================

独自の取得操作はget付きの入口へ集約しました。取得の省略メソッド・短名コマンドは
公開しません。数学演算・判定・保持プロパティ・OpenMaya標準名は維持します。

接続と単位
------------

.. code-block:: python

   import mlib

   node = mlib.createNode("transform", name="queryExample")
   plug = node.getPlug("translateX")
   internal = plug.get()                    # cm/rad/秒
   ui_value = plug.get(uiUnits=True)          # 現在のUI単位
   plug.set(ui_value, uiUnits=True)
   direct = plug.getSource(skipConversionNodes=False)
   upstream = plug.getSource()               # 既定は変換ノードを飛ばす
   inputs = node.getConnections(source=True, destination=False)
   outputs = plug.getConnections(src=False, dst=True)

``getSource/getDestinations`` の ``skipConversionNodes`` は既定Trueです。
``getConnections`` の同フラグは従来どおり既定Falseです。
子・配列の展開、型、ペア、ノード、番号の指定は ``getConnections`` の引数で選択します。
参照は ``getPlug``、値は ``Plug.get``、状態は専用メソッドで取得します。
特定時刻などMaya固有の照会は ``maya.cmds.getAttr`` を直接使います。

``disconnect(src=None)`` は指定または現在の入力だけを解除して入力元Plugを返します。
方向のboolや ``dst`` は受け付けません。方向を選ぶ解除は ``disconnectAll``、
未接続時に何もしない入力解除は ``disconnectInput`` を使います。

``uiUnits=False`` は従来の内部単位と数学型を返します。
``uiUnits=True`` は単位を変換した数値、複合値のtuple、配列の論理番号をキーにした辞書を返します。
数学型の中にUI単位の数値を格納しません。
既存の ``unit="deg"`` と ``uiUnits=True`` の併用は曖昧なため更新前に拒否します。

階層と責務
------------

``getShapes`` と ``getChildren`` は別の取得操作です。

.. code-block:: python

   shapes = node.getShapes()
   children = node.getChildren()
   all_nodes = node.getChildren(shapes=True, intermediates=True)
   descendants = node.getChildren(allDescendents=True, order="breadthFirst")
   leaves = node.getChildren(leaves=True, includeSelf=True)

``getChildNodes/getLeaves/iterBreadthFirst/iterDepthFirst`` は上記のフラグへ統合しました。
リグ用途のオフセットグループ生成とチャンネル初期化は ``mlrig.setups`` に置きます。
Joint/Jointsの削除はNode/NodesのMaya標準削除を継承します。
ウェイト移送と子の保持を伴う削除は ``mlrig.setups.JointHierarchy.delete`` を使います。

.. code-block:: python

   from mlrig.setups import ControlHierarchy

   zero, offset = ControlHierarchy.createOffsetGroups(node, "zero", "offset")
   ControlHierarchy.unlockAndDisconnectTransformChannels(node, fast=True)

専用APIを終了した演算14型は、型登録を維持し、MayaのアトリビュートをPlugで扱います。
対象型と入力・出力の例は :doc:`calculation_nodes` を参照してください。
Transform・Jointと行列・TRS関連の専用アクセサーも維持します。
固定アトリビュートの参照だけを返す専用メソッドは増やさず、Mayaの名前で ``getPlug()`` を使います。
DecomposeMatrixの各出力も ``getPlug("outputTranslate")`` 等で取得します。
セットアップが保存する設定の一覧は、そのセットアップ側で選定します。

.. code-block:: python

   calculation = mlib.createNode("reverse")
   calculation.getPlug("input").set((0.2, 0.4, 0.8))
   result = calculation.getPlug("output").get()

既存の配列番号と参照の取得はArrayPlugへ集約します。
``getIndices()`` は論理番号のlist、``getElements()`` はPlugのlist、
``get()`` は値を評価した辞書です。参照取得のために ``get()`` を使う必要はありません。

通常の変更とfast
-----------------

通常のシーン更新はMayaコマンドでUndo/Redoできます。
対応する ``fast=True`` はAPI 2.0で直接変更し、Undo履歴を追加しません。
Undoのグローバル設定は変更しません。内部の更新呼出しにも ``fast=fast`` を明示し、
各呼出しへ渡された値で処理を選びます。省略値や ``fast=False`` を外側の状態で上書きしません。
fastでも型・ロック・参照・接続等の検査を行います。

.. code-block:: python

   group = mlib.createNode("transform", name="temporary", fast=True)
   group.setTranslate((1, 2, 3), at=1, fast=True)
   group.getPlug("visibility").set(False, fast=True)
   group.delete(fast=True)

対応範囲は各メソッドのdocstringを参照してください。特に次の操作は制限があります。

* ``Plug.setEnumNames`` とmuteのfast変更は未対応です。
* API 2.0にデータ生成機能がない型付き配列はfast書込みを変更前に拒否します。
* ``Plug.setKey(fast=True)`` は単一時刻・値・接線型と直接のAnimCurve接続に限定します。
  接線省略時はMayaのグローバル設定を使います。
* AnimCurve・Plugのfast接線指定では入力 ``stepnext`` は未対応です。
  未知の接線型、``setKey`` の ``fixed``・``global``、``setTangent`` の ``global`` も更新前に拒否します。
  入力 ``step`` は ``auto`` へ補正します。詳細は :doc:`animation_nodes` を参照してください。
* ``AnimCurve.scaleKeys`` の入力倍率が負の場合のfast反転は未対応です。
* Jointのfast親変更と ``JointHierarchy.delete`` の子保持は、中間Transformや独自inverseScale処理が必要な条件を変更前に拒否します。
* ShadingEngineのfast割当は単一インスタンスのポリゴン全体に限定します。

freeze/makeIdentity、matchTransform、Containerの公開設定編集、DagPoseの保存・復元などの
Maya標準の複合コマンドにはfastを提供していません。これらは通常のUndo経路を使用します。

同じ結果を返す公開OM2 APIがない照会はMayaコマンドを使用します。
プラグインの導入状態、参照編集情報、dagPoseのatPose判定、settable・表示名・アニメーションレイヤーの
標準照会などが該当します。Maya 2022/2023のdefaultLayer照会もこの対象です。
``Plug.setKey`` で接線を省略した場合のグローバル接線設定もMayaコマンドで照会します。
公開コマンドは ``getNode/getPlug/createNode/ls/delete/duplicate/select`` の7入口です。
``ls`` の検索フラグはMaya標準に合わせ、検索結果をmlib参照へ変換します。
それ以外のMaya固有の照会・生成コマンドは ``maya.cmds`` を直接使い、
必要なノードだけ ``mlib.getNode`` で包みます。
通常の読取りにUndo履歴は追加しません。
