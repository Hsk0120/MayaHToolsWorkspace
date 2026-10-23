HumanIKノード
=============

必要な型の生成時だけmayaHIKをロードします。永続autoloadやSecurityの許可リストは変更しません。

``mlib.nodes`` に ``HIKCharacterNode``、``HIKSolverNode``、``HIKRetargeterNode``、
``HIKControlSetNode``、``HIKSkeletonGeneratorNode`` を公開しています。
これらの型をmlib経由で生成する際にmayaHIKをロードします。

.. code-block:: python

    from mlib.nodes import HIKCharacterNode
    character = HIKCharacterNode.createCharacter('Character')
    character.setJoint('Hips', 'hipsJoint')
    hips = character.getJoint('Hips')

骨割当は標準MELを使うため、HumanIK用アトリビュート・ラベルなども更新されます。
定義の妥当性確認とロックはHumanIK UIで行ってください。
ロック済みの既存キャラクター間では ``target.setSource(source)`` が標準MELへ
リターゲット接続を依頼します。未ロックや自己接続は拒否します。
``target.getSource()`` で現在の入力を取得できます。
返却はHIKCharacterNode、未接続はNoneです。setSourceは設定後もこの正式getterで
要求した入力へ接続されたことを確認し、異なる入力ならRuntimeErrorになります。

四足や任意骨格の自動キャラクタライズ、UIなしでの定義ロック、自動ベイクはこのAPIに含みません。
HumanIKの生成・割当・型登録は対応するMayaで確認してください。
実制作キャラクター間のリターゲット品質は個別に確認してください。
