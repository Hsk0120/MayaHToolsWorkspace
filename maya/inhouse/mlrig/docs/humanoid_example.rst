全身骨格のサンプル
==================

``mlrig.examples.humanoid.build`` は、一般的な人間の全身骨格と、骨ごとの簡易プロキシメッシュを作ります。
検証用のシーンや、リグの機能を人型で試すときの土台に使います。

.. code-block:: python

   from mlrig.examples import humanoid

   result = humanoid.build()                 # 2体目以降は prefix="human2_" など
   result["joints"]["lowerarm_l"]            # 接頭辞なしの名前 → 関節

HToolsの「rigging > buildHumanoidSkeleton」でも作れます（同名があれば接頭辞を付けます）。

骨格
----

* 名前はUEのマネキン / MetaHuman風です。 ``root`` ・ ``pelvis`` ・ ``spine_01`` 〜 ``spine_03`` ・ ``neck_01`` ・ ``head`` 、
  左右の ``clavicle`` ・ ``upperarm`` ・ ``lowerarm`` ・ ``hand`` 、指（ ``thumb`` ・ ``index`` ・ ``middle`` ・ ``ring`` ・ ``pinky`` の
  ``_01`` 〜 ``_03`` ）、 ``thigh`` ・ ``calf`` ・ ``foot`` ・ ``ball`` です。左右は ``_l`` ・ ``_r`` 、全53関節（指なしは23関節）。
* 身長約170cm（cm単位）、Yが上、+Zが正面、キャラクターの左が+Xです。既定はTポーズで、
  ``pose="A"`` なら腕を肩（ ``upperarm`` の位置）から45度下ろしたAポーズを基準（回転0）にします。
* 各関節は子の方向をローカルXにそろえます。2番目の軸は、体幹と脚が前（Z）、腕・指・足先が上（Y）です。
  手は前腕と同じ向きで、末端の関節は親と同じ向きです。
* 右半身は左半身の鏡像（ ``mirrorBehavior`` ）なので、左右に同じ回転を入れると動きが鏡像になります。

プロキシメッシュ
----------------

骨ごとの円柱・箱・球を関節の子として置くので、関節と一緒に動きます。半透明で、リファレンス表示
（ビューポートで選択できない）にして関節を選びやすくしています。 ``proxy=False`` で作りません。
プロキシは ``<接頭辞>humanProxy_set`` にまとまっています。スキンではないので、関節の付近で形が割れて見えます。

``fingers=False`` で指を省けます。作成は1回のUndoで戻せます。
