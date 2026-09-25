ドリブンキーの関係を扱う
============================

``DrivenKey`` はドライバーPlugと駆動先Plugの組を表します。
単独のMayaノードではなく、関連するAnimCurveの接続を照会するオブジェクトです。

.. code-block:: python

   import hlib

   relation = hlib.drivenKey(driver="ctrl.rotateY", driven="joint.rotateZ")
   relation.set_key(driver_value=0, value=0)
   relation.set_key(driver_value=90, value=45)

   print(relation.driver())
   print(relation.driven())
   print(relation.exists())
   print(relation.curves())

``hlib.drivenKey()`` は既存の属性を保持し、取得だけではシーンを変更しません。
``set_key()`` でMayaのsetDrivenKeyframeを実行し、キーを作成・更新します。
引数は現在のMaya UI単位で、ドライバーの現在値は変更しません。
接線は既定でlinearです。通常、外側にundo_chunkを指定する必要はありません。

カーブを詳しく編集する
--------------------------

.. code-block:: python

   for curve in relation.curves():
       print(curve.key_inputs(), curve.values())
       curve.set_tangent(0, outTangentType="flat")

カーブ単体の補間やキー削除は :doc:`animation_nodes` のAnimCurveメソッドで行います。
カーブの生の入力値は、単位変換がある場合にドライバーのUI単位と異なります。
``set_key()`` はドライバーのUI単位で設定できます。

複数の関係を扱う
--------------------

.. code-block:: python

   from hlib.animation import DrivenKeys

   relations = DrivenKeys.find("joint.rotateZ")
   print(relations.driver())      # ドライバーPlugのリスト
   print(relations.curves())      # 関係ごとのカーブリスト
   relations.set_key(0, 0)        # 同じ値を一括設定、1回のUndoで戻せる

``DrivenKeys([relation1, relation2])`` で明示的にまとめることもできます。
``call_each()`` では既存のコレクションと同様に要素別の引数を指定できます。
途中の失敗は例外として通知し、それ以前の変更は自動で取り消しません。

対応する接続構成
--------------------

直接接続、単位変換ノード、blendWeighted経由に対応します。
複数ドライバーのカーブは区別して取得し、blendWeightedのweight入力は検索しません。
キーに指定する出力値と最終的な駆動先の値は、他ドライバーや合成ウェイトによって異なります。

pairBlend、アニメーションレイヤー、任意の計算ノード経由は対象外です。
照会では対象外の経路を含めず、キー設定時は対象外の接続があれば例外にします。
同じ組に複数カーブが対応する場合も、曖昧な編集を避けるためキー設定を拒否します。
