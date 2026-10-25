書き出し用の枝と葉のjoint(LeafJoints)
=====================================

``mlrig.setups.LeafJoints`` は、節を不均一に拡大縮小するリグ(つぶし・伸ばし、squash & stretch)を、
親の scale を子へそのまま掛ける書き出し先(segmentScaleCompensate の無いゲームエンジンなど)へ渡すための、
書き出し用の骨格を作ります。入力の節ごとに、位置と回転だけを受け持つ **枝のjoint** と、その子(階層の末端)で
scale だけを受け持つ **葉のjoint** を作り、入力のワールド行列へ追従させます。スキンのウェイトを葉のjointへ
付ければ、肘を太くしても前腕より先は太りません(scale が階層を伝わるのは葉の1段だけです)。
Maya標準ノード( ``pickMatrix`` ・ ``multMatrix`` ・ ``decomposeMatrix``)のみで構築し、独自プラグインや
フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import LeafJoints

   graph = LeafJoints.create(
       ["shoulder", "elbow", "wrist", "hand"],   # 入力の節(リグの骨・コントロール)
       name="armExport", parent="exportRoot")
   branches, leaves = graph.getJoints()           # スキンは leaves へ付ける

引数
----

* ``sources``: 入力の節(transformまたはjoint)。枝の親子は、各節のDAGの祖先のうち最も近い入力の節を親にします
  (間に入力でないtransformがあってもよく、枝分かれも可。列の順は問いません)。入力の祖先が無い節は ``parent`` の直下です。
* ``name``: 一意なcontainer名。jointは ``<name>_branch<番号>`` ・ ``<name>_leaf<番号>`` (番号は ``sources`` の順)。
* ``parent``: 枝の階層の根を置くtransform(書き出しの根)。 ``None`` ならワールド。scale 1 を前提とします。
* ``shear``: ``True`` なら葉のjointへ shear も渡します。既定の ``False`` は scale だけを渡します(下の「剪断」)。

出力
----

* 枝のjoint ``<name>_branch<i>`` ・葉のjoint ``<name>_leaf<i>`` (どちらもcontainerのメンバー、jointOrient 0、
  segmentScaleCompensate オフ)。 ``getJoints()`` で (枝の列, 葉の列) を返します。
* containerの ``branch<i>`` ・ ``leaf<i>`` (message)、 ``branchMatrix<i>`` (枝のローカル行列)、
  ``leafMatrix<i>`` (葉のローカル行列)。

計算
----

行ベクトル規約で、入力の節iのワールド行列を ``W_i`` とします。

1. ``pickMatrix`` で ``W_i`` から scale と shear を除き、位置と回転だけの ``N_i`` を作ります。
2. 枝のローカル行列 ``B_i = N_i * N_p^-1`` ( ``N_p^-1`` は枝のjointの ``parentInverseMatrix`` 。親の枝・ ``parent`` ・
   ワールドのいずれかの逆行列)を ``decomposeMatrix`` して、枝の ``translate`` ・ ``rotate`` へ接続します。
3. 葉のローカル行列 ``F_i = W_i * N_i^-1`` ( ``N_i^-1`` は葉の ``parentInverseMatrix``)には scale と shear だけが残るので、
   ``decomposeMatrix`` して葉の ``scale`` (と ``shear``)へ接続します。

枝と葉は jointOrient 0・segmentScaleCompensate オフなので、 ``translate`` ・ ``rotate`` ・ ``scale`` を親子で掛けるだけの
書き出し先でも、枝のワールド行列は ``N_i`` (scale 1)、葉のワールド行列は ``W_i`` になります。入力は
segmentScaleCompensate 付きのjointでも、普通のtransformの階層でも構いません(ワールド行列だけを読みます)。

剪断
----

segmentScaleCompensate を使わないtransformの階層で、親を不均一に拡大縮小して子を回すと、子のワールド行列に
剪断(shear)が生じます。多くの書き出し先は剪断を表せないため、既定( ``shear=False``)では葉へ scale だけを渡し、
葉のワールド行列は ``W_i`` から剪断を除いたものになります。 ``shear=True`` なら葉の ``shear`` へも接続して
``W_i`` と一致させます。

参考にした考え方
----------------

* 不均一な scale を扱えない書き出し先のために、骨格を「階層を作る枝のjoint」と「末端で scale を受け持つ葉のjoint」に
  分け、葉の scale が子へ伝わらないようにする一般的な方法(ある節の scale を、その節の複製の末端のjointに持たせる)。
  segmentScaleCompensate( ``inverseScale``)を使うMayaの階層と、使わない書き出し先との違いを吸収します。

試験と検証
----------

* 試験: ``mlrig/__tests__/test_setup_leaf_joints.py`` (作成直後と乱数の12姿勢で、枝・葉のワールド行列がOpenMayaで
  独立に求めた行列と、 ``translate`` ・ ``rotate`` ・ ``scale`` ・ ``shear`` の親子の積(書き出し先と同じ計算)の両方に一致・
  肘の scale が葉にしか現れない・剪断の有無・親の判定と枝分かれと書き出しの根・UI単位・所有とUndo/Redo・引数検査)。
* メニューの **Setup Samples > LeafJoints - squash arm for export** で試せます(:doc:`setup_samples`)。
* 検証動画: ``tools/demo_leaf_joints.py`` (:doc:`verification_video`)。

制限
----

* 枝・葉のjointは作成時の入力の数と親子で固定です(入力の階層を後から変えたら作り直します)。
* ``parent`` に scale があると、枝のローカル行列の scale は捨てるため枝が ``N_i`` からずれます。書き出しの根は scale 1 にします。
* 葉の回転は0、位置は枝と同じです。葉を回したり動かしたりする補正は、入力の側で行います。
* スキンのウェイトの付け替え(枝から葉への移動)は行いません。
