IK用の平面チェーンで解くIK
============================

``mlrig.setups.PlanarIK`` は、付け根・膝・足首の回転中心へ、向きの整ったIK用のjointを3本作ってIKで解き、
元のjointへ回転だけを渡します。元のjointは、途中にずれた骨(オフセットの骨)が挟まっていても、
向き(``jointOrient``)がばらばらでもかまいません。機械の脚でよく使う「IK用の骨と見た目の骨を分ける」構成です。

.. code-block:: python

   from mlrig.setups import PlanarIK

   # hip → thighOffset → knee → shinOffset → ankle のように、間に別のjointがあってよい
   ik = PlanarIK.create("hip_jnt", "knee_jnt", "ankle_jnt", name="legIK")
   cmds.parent(ik.handle, "foot_ctrl")
   cmds.parent(ik.pole, "kneePole_ctrl")
   cmds.orientConstraint("foot_ctrl", "ankle_jnt", maintainOffset=True)   # 足首の向きは必要なら別に付ける

仕組み
------

1. 付け根 ``P`` ・膝 ``K`` ・足首 ``A`` (元のjointの位置)へ、IK用のjoint ``<name>_rootDriver`` ・
   ``<name>_midDriver`` ・ ``<name>_endDriver`` を作ります。3点は必ず一平面上にあり、その法線
   ``n = normalize((K - P) × (A - K))`` を各jointのローカルZ、次のjointへの向きをローカルXにします。
2. IK用の膝の自由度をZの1軸にし、``preferredAngle`` を今の姿勢にして、Rotate Plane IKとポールベクターを作ります
   (:doc:`hinge_ik` と同じ方法で、作った瞬間に姿勢は跳ねません)。IK用の膝は ``n`` まわりだけで曲がります。
3. 元の付け根と膝へ、IK用のjointの回転をオフセット付きの ``orientConstraint`` で渡します。
   回転の中心(``P`` ・ ``K``)が同じなので、途中のずれた骨を含めて、元の膝・足首の位置はIK用のjointと一致します。

IK用のjointは元の付け根の親の子として作るので、骨盤などの親の動きに付いていきます。
ikHandle・locator・IK用のjoint・コンストレイントは ``<name>`` のcontainerが所有します。

HingeIKとの違い
---------------

* :doc:`hinge_ik` は元の膝のjointの向きと自由度を書き換え、膝を任意のヒンジ軸(模型の関節の軸)で曲げます。
  元のjointは直接の親子に限ります。
* PlanarIKは元のjointの値を書き換えず(``orientConstraint`` を接続するだけ)、途中に別のjointがあってもよい代わりに、
  膝の曲がる軸は生成時の3点の平面の法線 ``n`` です。模型の軸と違う軸で曲げたい場合はHingeIKを使います。

引数
----

* ``root`` / ``mid`` / ``end``: 元の付け根・膝・足首のjoint(回転中心)。``root`` → … → ``mid`` → … → ``end`` の同じ階層。
* ``poleDistance``: 付け根からポールベクターのlocatorまでの距離。省略するとチェーンの全長です。
* ``showDrivers``: IK用のjointを表示するか(既定は非表示)。

制限
----

* 生成時の姿勢を基準にします。bindポーズ(膝を少し曲げた状態)で実行してください。3点が一直線だと平面を決められません。
* 元の付け根と膝の ``rotate`` は ``orientConstraint`` に接続されるため、直接キーを打てません。
* 足首の向きは膝からの親子関係のままです。フットコントロールに合わせる場合は、足首へ別に ``orientConstraint`` を付けます。
* 足首の目標が脚の長さより遠いと届きません。ストレッチは含みません。

テスト
------

``mlrig/__tests__/test_setup_planar_ik.py`` (``setups`` スイート)で、途中にずれた骨が2本あり、向きがばらばらの脚について、
作成前後で元のjointの行列が変わらないこと、足首を5通りに動かしたとき元の足首が目標に届き、元の付け根・膝・足首の位置がIK用のjointと一致し、
IK用の膝の回転がZだけで、元の膝の曲がり(付け根の回転を除いたもの)の軸が ``n`` と平行なこと、途中の骨の長さが変わらないこと、
骨盤を動かしたときの追従、引数の検査、生成のUndoを確認します。Maya 2025・2027で確認しています。

検証動画
--------

:doc:`hinge_ik` の検証動画の青い脚がPlanarIKです。途中にずれた骨を2本挟んだ脚で、細い線のjointがIK用のチェーンです。
HUDの ``bind knee bend axis . n`` は、元の膝の曲がりの軸と ``n`` の内積(1なら ``n`` まわりだけで曲がっている)で、全フレーム1.00000でした。

`検証動画をGoogle Driveで見る <https://drive.google.com/file/d/1HhmutqWWEFX2RL5ozvd_ovTxpY4tu8DW/view?usp=drivesdk>`_
