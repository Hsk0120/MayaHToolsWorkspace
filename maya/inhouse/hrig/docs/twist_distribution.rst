ツイストの分配
========================

``hrig.setups.TwistDistribution`` は二つのtransformの相対Quaternionから
指定軸のツイストだけを抽出し、位置と回転を同じ割合で補間します。
標準ノードのみを使い、生成ノードは ``container`` が所有します。
ジョイントの生成・LOD・スキニングは呼び出し側の責務です。

.. code-block:: python

   import hlib
   from hrig.setups import TwistDistribution

   start = hlib.createNode("transform", name="twistStart")
   end = hlib.createNode("transform", name="twistEnd", parent=start)
   end.set_translate((8, 0, 0))
   end.plug("rotateX").set(120)
   graph = TwistDistribution.create(start, end, name="twistGraph", axis="x")
   output = graph.sample(0.25, "quarter")
   print(output.get())  # 始点空間で位置X=2、回転X=30度の行列

``axis`` は始点のローカル長手軸 ``x`` / ``y`` / ``z`` です。
相対回転の軸成分とW成分を正規化し、純粋なツイスト行列を ``blendMatrix`` で補間します。
位置は両端間の線形補間です。始点と終点が直接の親子ならローカル行列と
offsetParentMatrixを使い、別階層ならワールド行列から始点空間へ変換します。
参照先の再親子付けは構築後に行わないでください。

回転は最短経路で、180度境界をまたぐ連続回転や複数回転の蓄積には対応しません。
長手軸に直交する180度の曲げではツイストの分解が不定となるため、恒等回転にします。
骨の曲げ方向へ自動で軸を向け直す機能や、ボリューム補正は含みません。
Maya 2022のblendMatrix成分選択boolと、2025以降の成分ウェイトの差を吸収します。

所有する計算ノードは ``hlib.delete(graph.container)`` で削除できます。
両端のtransformは削除対象に含めません。補間先を始点・終点やその上流へ接続して
循環を作らないようにしてください。
