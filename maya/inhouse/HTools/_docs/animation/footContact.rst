足の接地と滑りを測る
============================================================

HTools > animation > footContact

#. 足裏の接地点に置いたTransformを選択します。複数の足を一度に選べます。

#. Loop framesに歩行周期、Contact framesに接地している区間、Sample stepに測定間隔をフレーム単位で入力します。

#. 平面の床は高さと法線を指定します。メッシュを使う場合はFloor mesh shapeにShapeのDAGパスを入力します。移動・回転する剛体床ではFollow moving rigid meshを有効にします。

#. Inspect selected feetを押します。slideは接地開始位置からの最大の滑り、clearanceは最大の浮き、penetrationは最大の貫通で、単位はcmです。剛体床では接地開始時のローカル形状を固定して測ります。loopDistanceとloopDegreesは周期両端のワールド位置・回転の差です。
