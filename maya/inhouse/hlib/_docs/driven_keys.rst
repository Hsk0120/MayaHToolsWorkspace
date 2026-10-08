ドリブンキーの関係を扱う
============================

``DrivenKey`` はドライバーPlugと駆動先Plugの組を表します。
単独のMayaノードではなく、関連するAnimCurveの接続を照会するオブジェクトです。

.. code-block:: python

   import math
   import hlib

   relation = hlib.getDrivenKey(driver="ctrl.rotateY", driven="joint.rotateZ")
   relation.setKey(driver_value=0, value=0)
   relation.setKey(driver_value=math.pi / 2, value=math.pi / 4)

   print(relation.getDriverPlug())
   print(relation.getDrivenPlug())
   print(relation.exists())
   print(relation.getCurves())

``hlib.getDrivenKey()`` は既存のアトリビュートを保持し、取得だけではシーンを変更しません。
``setKey()`` でMayaのsetDrivenKeyframeを実行し、キーを作成・更新します。
引数はアトリビュートに応じたcm/rad/秒で、ドライバーの現在値は変更しません。
接線は既定でlinearです。通常、外側にundo_chunkを指定する必要はありません。

カーブを詳しく編集する
--------------------------

.. code-block:: python

   for curve in relation.getCurves():
       print(curve.getKeyInputs(), curve.getKeyValues())
       curve.setTangent(0, outTangentType="flat")

カーブ単体の補間やキー削除は :doc:`animation_nodes` のAnimCurveメソッドで行います。
カーブの生の入力値は、単位変換がある場合にドライバーのUI単位と異なります。
``setKey()`` はドライバーの内部単位で設定できます。

複数の関係を扱う
--------------------

.. code-block:: python

   from hlib.common import DrivenKey

   relations = DrivenKey.find("joint.rotateZ")
   print([relation.getDriverPlug() for relation in relations])      # ドライバーPlugのリスト
   print([relation.getCurves() for relation in relations])      # 関係ごとのカーブリスト
   for relation in relations:
       relation.setKey(0, 0)

``[relation1, relation2]`` のように通常のリストで保持します。
各setKeyはそれぞれUndoできます。
途中の失敗は例外として通知し、それ以前の変更は自動で取り消しません。

対応する接続構成
--------------------

直接接続、単位変換ノード、blendWeighted経由に対応します。
複数ドライバーのカーブは区別して取得し、blendWeightedのweight入力は検索しません。
キーに指定する出力値と最終的な駆動先の値は、他ドライバーや合成ウェイトによって異なります。

pairBlend、アニメーションレイヤー、任意の計算ノード経由は対象外です。
照会では対象外の経路を含めず、キー設定時は対象外の接続があれば例外にします。
同じ組に複数カーブが対応する場合も、曖昧な編集を避けるためキー設定を拒否します。
