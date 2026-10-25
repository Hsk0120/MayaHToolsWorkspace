中手骨の分配(MetaSpread)
==========================

``mlrig.setups.MetaSpread`` は、同じ親の下に並ぶjointのうち両端の回転を、間のjointへ割合に応じて分配します。
手のひらの中手骨(人差し指〜小指の付け根)や足の中足骨で、両端だけを動かせば間が付いてくる
「手のひらを広げる(spread)・丸める(cup)」動きを、少ないコントロールで作るための部品です。
Maya標準ノード(``pickMatrix`` ・ ``multMatrix`` ・ ``blendMatrix``)のみで構築し、
独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import MetaSpread

   graph = MetaSpread.create("index_meta_jnt", "pinky_meta_jnt", ["middle_meta_jnt", "ring_meta_jnt"],
                             name="palmSpread")
   owner = graph.container
   # 間のjointと同じ親の下の、TRSが単位の出力jointへ接続する
   owner.getPlug("matrix0").connectTo("middle_meta_out_jnt.offsetParentMatrix")
   owner.getPlug("matrix1").connectTo("ring_meta_out_jnt.offsetParentMatrix")

引数
----

* ``first`` ・ ``last``: 両端のtransform(例: 人差し指と小指の中手骨)。回転を分配の元にします。
* ``middles``: 間の1つ以上のtransform(firstからlastの順)。
* ``name``: 一意なcontainer名。
* ``weights``: 間のjointごとの、lastの回転を使う割合(0〜1)。省略時は等間隔 ``(i+1)/(n+1)``。
  後からcontainerの ``weight<番号>`` で変更できます。

全てのjointは同じ親の下にあることが条件です。jointOrientはjointごとに違ってかまいません。

出力(containerのアトリビュート)
---------------------------------

* ``matrix0`` 〜 ``matrix<n-1>``: 間のjointの親空間の行列。生成時のローカル行列に、両端の回転の差を補間した
  回転を加えたもの。位置は生成時のまま。
* ``weight0`` 〜 ``weight<n-1>``: 補間の割合。

計算
----

1. 両端のローカル行列(jointOrientを含む)から回転だけを取り出し( ``pickMatrix``)、生成時の回転との
   親空間での差 ``P0 = R0^-1 * R0'`` ・ ``P1 = R1^-1 * R1'`` を求めます(行ベクトル規約)。
2. 間のjoint i ごとに ``blendMatrix`` で ``slerp(P0, P1, weight_i)`` を求めます(クォータニオンの補間)。
3. 出力 = ``Ri * slerp(P0, P1, weight_i) * Ti``。 ``Ri`` ・ ``Ti`` は生成時のローカルの回転・位置(定数)。
   生成時は差が単位行列なので、作成時に姿勢が跳ねません。

差を親空間で扱うので、jointごとにjointOrient(ローカルの軸の向き)が違っても、両端と同じ向きへ回ります。

参考にした考え方
----------------

* mGear(``maya/external/mgear5`` 、MITライセンス)の ``meta_01`` 部品: 1つのコントロールの回転を、
  中手骨ごとに段階的な割合( ``pairBlend`` の重み 0, 1/(n-1), …, 1)で分ける考え方。
  ここではそれを両端のjointからの補間に広げ、親空間の回転の差を ``blendMatrix`` で補間します(コードは流用していません)。

試験と検証
----------

* 試験: ``mlrig/__tests__/test_setup_meta_spread.py`` (作成時に跳ねない・OpenMayaのクォータニオンの
  球面線形補間との一致・一方の端だけの回転で角度が割合に比例・weightの変更・引数検査・Undo)。
* メニューの **Setup Samples > MetaSpread - palm metacarpals** で試せます(:doc:`setup_samples`)。
* 検証動画: ``tools/demo_meta_spread.py`` (:doc:`verification_video`)。

制限
----

* 両端の位置の移動・scaleは分配しません(回転だけ)。
* 両端の回転の差が互いに180度に近いと、補間の向きが不定になります。
* 指の付け根から先(基節骨など)は含みません。出力jointの子として既存の指のリグを付けます。
