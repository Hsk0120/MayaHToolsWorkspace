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

.. code-block:: python

   from mlrig.setups import ControlHierarchy

   zero, offset = ControlHierarchy.createOffsetGroups(node, "zero", "offset")
   ControlHierarchy.unlockAndDisconnectTransformChannels(node, fast=True)

単純な演算アトリビュートはPlugで扱います。検証やenum変換、範囲の一括操作は専用メソッドを残します。
Transform・Jointと行列・TRS関連の専用アクセサーも維持します。

.. code-block:: python

   calculation = mlib.createNode("reverse")
   calculation.getPlug("input").set((0.2, 0.4, 0.8))
   result = calculation.getPlug("output").get()

通常の変更とfast
-----------------

通常のシーン更新はMayaコマンドでUndo/Redoできます。
対応する ``fast=True`` はAPI 2.0で直接変更し、Undo履歴を追加しません。
Undoのグローバル設定は変更せず、外側のfast指定を対応する内側の操作へ引き継ぎます。
fastでも型・ロック・参照・接続等の検査を行います。

.. code-block:: python

   group = mlib.createGroup(name="temporary", empty=True, fast=True)
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
* Jointのfast親変更・削除は中間Transformや独自inverseScale処理が必要な条件を変更前に拒否します。
* ShadingEngineのfast割当は単一インスタンスのポリゴン全体に限定します。

freeze/makeIdentity、matchTransform、Containerの公開設定編集、DagPoseの保存・復元などの
Maya標準の複合コマンドにはfastを提供していません。これらは通常のUndo経路を使用します。

同じ結果を返す公開OM2 APIがない照会はMayaコマンドを使用します。
UI・設定・導入状態、参照編集情報、dagPoseのatPose判定、settable・表示名・アニメーションレイヤーの
標準照会などが該当します。Maya 2022/2023のdefaultLayer照会もこの対象です。
``Plug.setKey`` で接線を省略した場合のグローバル接線設定もMayaコマンドで照会します。
コマンド層の明示的な照会フラグはmaya.cmdsの仕様と値を維持します。
通常の読取りにUndo履歴は追加しません。
