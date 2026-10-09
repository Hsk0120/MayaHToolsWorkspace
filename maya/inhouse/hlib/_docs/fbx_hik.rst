FBXとHumanIK
============

標準同梱プラグインを必要な操作時だけロードします。hlibのimportではロードしません。
プラグインの永続autoloadやSecurityの許可リストは変更しません。

FBXファイル
-----------

.. code-block:: python

    from hlib.common.fbx import exportFbx, importFbx
    exportFbx('C:/work/motion.fbx', selection=['rootJoint'], animation=True)
    nodes = importFbx('C:/work/motion.fbx', namespace='source')

書き出しは既定で上書きを拒否します。書き出し対象を省略するとシーン全体を出力します。
選択とAnimation設定を復元し、それ以外のFBX設定は現在値を使います。
読み込みはImportModeをaddへ変更して復元します。新規ノードを返します。
ファイル操作の完全なUndoは保証しません。

fbxmayaがプラグイン検索パスから見つかる必要があります。Maya 2022の一部環境では
FBXのモジュール設定が不足するため、呼出側でインストール済みfbxmayaをロードしてください。

HumanIKノード
-------------

``hlib.nodes`` に ``HIKCharacterNode``、``HIKSolverNode``、``HIKRetargeterNode``、
``HIKControlSetNode``、``HIKSkeletonGeneratorNode`` を公開しています。
これらの型をhlib経由で生成する際にmayaHIKをロードします。

.. code-block:: python

    from hlib.nodes import HIKCharacterNode
    character = HIKCharacterNode.createCharacter('Character')
    character.setJoint('Hips', 'hipsJoint')
    hips = character.joint('Hips')

骨割当は標準MELを使うため、HumanIK用アトリビュート・ラベルなども更新されます。
定義の妥当性確認とロックはHumanIK UIで行ってください。
ロック済みの既存キャラクター間では ``target.setSource(source)`` が標準MELへ
リターゲット接続を依頼します。未ロックや自己接続は拒否します。
``target.getSource()`` または省略入口の ``target.source()`` で現在の入力を取得できます。
返却はHIKCharacterNode、未接続はNoneです。setSourceは設定後もこの正式getterで
要求した入力へ接続されたことを確認し、異なる入力ならRuntimeErrorになります。

四足や任意骨格の自動キャラクタライズ、UIなしでの定義ロック、自動ベイクはこのAPIに含みません。
Maya 2022でFBXの骨アニメーション往復、HumanIKの生成・割当・型登録を検証しています。
実制作キャラクター間のリターゲット品質は個別に確認してください。
