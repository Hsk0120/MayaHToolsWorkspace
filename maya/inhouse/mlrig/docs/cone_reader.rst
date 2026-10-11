コーンの一致度
==============

``mlrig.setups.ConeReader`` は、ドライバーの向き（矢印）がコーンの軸にどれだけ一致しているかを
0〜1で出力します。コーンの中心と完全に一致すると1、なす角がコーンの半角に達すると0です。
標準ノードのみを使い、計算ノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import ConeReader

   reader = ConeReader.create("l_upperArm", "l_shoulder", name="armForward", coneAngle=60)
   # l_upperArm の X 軸が矢印、コーンは l_shoulder に追従する。
   # armForward_cone を回して、weight を1にしたい向きへコーンを向ける。
   reader.container.getPlug("weight")   # 0〜1

作られるもの
------------

* ``<name>_driver_GRP`` → ``<name>_driver``: 矢印（黄色）。GRPを ``driverJoint`` に重ねて
  ``parentConstraint`` します。矢印は ``<name>_driver`` のローカル +X です。
  ``driverAxis`` でジョイントのどの軸を矢印にするか選べます（x/y/z/-x/-y/-z）。
* ``<name>_cone_GRP`` → ``<name>_cone``: コーン（水色）。GRPを ``coneJoint`` に
  ``parentConstraint`` します。コーンの軸は ``<name>_cone`` のローカル +X です。
  作成直後は矢印と同じ位置・向きなので、 ``weight`` は1から始まります。
* ``<name>``（container）: 入力と出力のアトリビュートを持ちます。

ジョイントを指定しなければ、GRPはどこにもコンストレイントされません。後から任意の
ジョイントへコンストレイントしても同じように動きます。

アトリビュート
--------------

* ``coneAngle``: コーンの半角。度。0.01〜180。コーンの表示も連動して開きます。
* ``falloff``: ``linear`` は ``clamp(1 - angle / coneAngle, 0, 1)``、 ``smooth`` はその値 ``t`` を
  ``t²(3 - 2t)`` にして中心と端をなめらかにします。
* ``size``: 矢印とコーンの表示の長さ。計算には影響しません。
* ``weight``: 出力。0〜1。
* ``angle``: 出力。矢印とコーンの軸のなす角。度。シーンの角度単位に依存しません。

計算
----

矢印とコーンのローカル +X を ``vectorProduct`` でワールドへ移し、 ``angleBetween`` でなす角を
求めます。向きだけを比べるので、位置・距離・矢印まわりのねじれは結果に影響しません。
コーンの表示は、単位コーンを x方向 ``cos(coneAngle)·size``、yz方向 ``sin(coneAngle)·size`` に
伸縮します。標準ノードにcos・sinがないため、Z軸まわりに ``coneAngle`` 回した ``composeMatrix`` で
X軸を変換して得ます。

制限
----

* 出力は左右の区別を持ちません。コーンのどちら側へ外れても同じ値になります。
* ``coneAngle`` が180のときは、真後ろだけが0になります。
* 作成後に ``<name>_driver`` ・ ``<name>_cone`` の親を変えると、container の参照
  （ ``driver`` ・ ``cone`` のmessage接続）は保たれますが、コンストレイントは自分で付け直します。

HToolsの「rigging > coneReaderUI」で、選択したジョイントから作成できます。1つ目に選んだ
ジョイントが矢印、2つ目がコーンの追従先です。
