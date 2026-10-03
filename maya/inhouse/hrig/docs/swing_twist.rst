Swing / Twistとドリブンキー
================================

``hrig.setups.SwingTwist`` は親transformを持つjointのローカル回転を分解します。
``matrix * offsetParentMatrix`` を使用し、生成時の姿勢をゼロ基準とします。
標準ノードのみを使い、生成した計算ノードと単位変換ノードをcontainerで所有します。

.. code-block:: python

   from hrig.setups import SwingTwist

   from hlib.scene import DrivenKey

   graph = SwingTwist.create("elbow_jnt", name="elbowDriver", axis="x")
   relation = DrivenKey(graph.container.plug("swingZ"), "corrective_jnt.translateY")
   relation.setKey(-90, -1)
   relation.setKey(0, 0)
   relation.setKey(90, 1)

``axis`` はTwistの長手軸です。 ``rest=False`` なら生成時の姿勢を差し引かずに扱います。
出力は以下です。

* ``twist``: 指定軸まわりの符号付き角度。
* ``swingX`` / ``swingY`` / ``swingZ``: Twistを除いたSwingをXYZ Euler角へ変換した成分。
* ``twistMatrix`` / ``swingMatrix``: 純粋な回転行列。

角度スカラーはすべて **度単位のdouble** で、シーンの角度単位に依存しません。
DrivenKeyの入力キーも度で指定し、出力キーは駆動先の現在のUI単位で指定します。
Mayaの行ベクトル規約で ``twistMatrix * swingMatrix`` が基準からの回転になります。
SwingのXYZ成分は独立した解剖学的な曲げ角ではなく、Euler表現の特異点があります。

TwistはQuaternionを指定軸へ射影して抽出します。指定軸に直交する180度のSwingでは
Twistが不定となるため、Twistを恒等回転とします。180度境界を越える連続回転・多回転・
負スケール・シアーは対象外です。構築後に参照jointの親を変更しないでください。

駆動先から分解元へ依存が戻らない構成にしてください。hlibの分解オブジェクト自体は
駆動先やLODを管理しません。hrigのレイヤー登録を使う場合は ``LimbRig.add_driven`` を利用します。
上記のhlib単体例で作成したSDKカーブは分解containerの所有物ではありません。
