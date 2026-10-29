変更履歴
========

mlib の版ごとの変更点です。版番号は ``mlib.__version__``・``maya/modules/mlib.mod``・
この文書の見出しに同じ値を置き、``__tests__/unit/test_static_version.py`` が三者の一致を検査します。

5.0.0 (2026-10-29)
------------------

リガー(Maya の操作には詳しく Python は初心者)の目線で mlib を使ったリギング作業の検証を行い、見つかった問題を直しました。
黙って間違った結果になっていた動作を止め、cmds に戻る必要があった作業(ジョイントの向き付け・IK・ミラー・
コントローラー・blendShape・スキンの頂点単位の編集)を mlib で書けるようにしました。既存コードの結果が変わる変更を含みます。

.. rubric:: 移行が必要な変更

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - 対象
     - 4.1.0 まで
     - 5.0.0
   * - 角度アトリビュートの数値(``Plug.get/set``・``CompoundPlug``/``MultiPlug`` の角度の子・要素、
       ``jointOrient``・``rotateAxis`` の ``get()``)
     - ラジアン
     - **度**。``unit="rad"`` でラジアン(``"deg"``・``"degree(s)"``・``"radian(s)"`` も可)。``uiUnits=True`` と ``unit`` は同時指定できない
   * - ``Transform.setRotate``
     - 既定 ``unit="rad"``
     - 既定 ``unit="deg"``。``EulerRotate``・``Quaternion`` は unit に関係なくそのまま
   * - ``Transform.getRotate``
     - ``EulerRotate``
     - 同じ。``unit="deg"``/``"rad"`` を指定するとその単位の tuple
   * - ``DrivenKey.setKey``・``Node.addAttr`` の角度の範囲と既定値・``AnimCurve`` の角度のキー値と接線・
       ``AimConstraint`` のオフセット・``common.units.angleToUi/angleFromUi``
     - ラジアン
     - 度(``unit=`` で指定可)。単位の無いドライバーは換算しない
   * - ``Plug.getMin/getMax/getSoftMin/getSoftMax/getDefault``
     - ``MAngle``
     - 既定は ``MAngle`` のまま。``unit=`` を指定すると数値
   * - ``EulerRotate(...)``・``Quaternion.fromAxisAngle``
     - ラジアン
     - 既定はラジアンのまま(om2 と同じ)。``unit="deg"`` を追加
   * - ``node.tx = 5``
     - 何も書き込まず、Python の属性が作られる
     - ``node.getPlug("tx").set(5)`` と同じ書き込み(Undo 1回、角度は度)。Maya のアトリビュートが無い名前は ``AttributeError``
   * - ``createNode("joint", parent=<joint>)``
     - inverseScale を接続しない
     - 親の scale を inverseScale へ接続する(``cmds.joint`` と同じ)
   * - ``connect/connectTo(nextAvailable=True)``
     - 0 から探して途中の空き要素へ接続
     - ``cmds.connectAttr(nextAvailable=True)`` と同じ(接続のある最後の要素の次)。``getNextAvailable()`` は変わらない
   * - 同じ接続をもう一度 ``connect/connectTo``
     - Maya のコマンドエラー
     - ``RuntimeError("Already connected")``。``safe=True`` で何もしない
   * - ``SkinCluster.setWeights(joints, [K個])``(頂点が2つ以上)
     - 全頂点に同じ値
     - ``ValueError``。``broadcast=True`` か ``vertices=`` を指定する
   * - ``SkinCluster.getWeights`` の未登録の influence・Component
     - ``TypeError: ... not convertable to int``
     - ``ValueError``(未登録)・``TypeError``(Component、``vertices=`` を案内)
   * - ``SkinCluster.copyWeightsTo``
     - ``None`` を返し、skinCluster だけ受け付ける
     - 転送先の ``SkinCluster`` を返し、形状も受け付ける(未バインドなら同じ influence でバインド)
   * - ``Transform.resetAttrs()``
     - translate・rotate・scale・shear だけ
     - ``Node.resetAttrs()`` と同じくキー設定可能な全アトリビュート(ユーザー定義を含む)
   * - ``createNode(name=)``・``rename()`` の ``|``
     - Maya が黙って置き換える
     - ``ValueError``
   * - 無効な参照の ``getName()``・``getNodeName()``
     - ``""``
     - ``RuntimeError``(``str()`` は ``""`` のまま)
   * - ``rename()``・``setNamespace()`` の戻り値
     - 文字列
     - 自身
   * - ``Plug.getName()``・``getAttrName()``
     - ``tt.wm``・``.wm``
     - ``tt.wm[0]``・``wm[0]``(要素番号を含め、先頭のドットなし)
   * - ``mlib.logger``
     - ``get_logger``・``raise_with_notify(exception_type, ..., from_exception=)``
     - ``getLogger``・``raiseWithNotify(exceptionType, ..., fromException=)``(旧名は残さない)
   * - ``multDoubleLinear``/``multDL``・``addDoubleLinear``/``addDL``
     - 版により一方だけ。2026 以降は旧名の ``ls(type=)``・``isType`` が外れる
     - どの版でも両方の名前を受け付ける。``MultDL is MultDoubleLinear``(``getType()`` はその版の名前)
   * - Undo の名前
     - ``mlibTransformSetTranslate``
     - ``mlib setTranslate L_arm_CTRL`` のように操作と対象
   * - ``progressBar``(Maya GUI)
     - Script Editor へテキスト
     - 画面下のメイン進捗バー(Esc で ``ProgressCancelled``)。``gui=False`` でテキスト
   * - ``Vector`` と 3 要素の tuple/list
     - ``+`` は ``TypeError``、``==`` は黙って ``False``
     - 加減算・比較ができる

.. rubric:: 追加

- ジョイント: ``Joint.orient()``・``Joints.orient()``(``cmds.joint -e -oj`` 相当)、``Joint.mirror(axis="YZ", behavior=True, searchReplace=)``
  (``cmds.mirrorJoint`` 相当)、``mlib.duplicate(..., suffix="_FK")``(複製した子孫にも接尾辞)。
- IK: ``IkHandle.create(startJoint, endJoint, solver=, name=, curve=)``、``IkHandle.getEffector()``・``getCurve()``。
- blendShape: 手書きの ``mlib.nodes.BlendShape``。``create``・``getTargetNames``・``getTargetIndex``・``getWeightPlug``・
  ``addTarget``・``removeTarget``(完全に取り除く)・``"name" in bs``・``getBaseGeometry``。
- スキン: ``getWeights(..., vertices=)``・``setWeights(..., vertices=, normalize=, broadcast=)``・``getVertexWeights``・
  ``setVertexWeights``・``mirrorWeights``・``pruneWeights``。
- コントローラー: ``NurbsCurve.create(points, degree=, closed=, name=, parent=)``・``NurbsCurve.setCvPositions``・
  ``Transform.replaceShapes``・``DagNode.setColor``/``getColor``。
- アトリビュート: ``EnumPlug.set("name")``(名前での設定、``addAttr(defaultValue="name")`` も可)、
  ``Plug.setMin/setMax/setSoftMin/setSoftMax``、``Transform.setLimits(translateX=(min, max), ...)``、
  ``Plug.lock()``・``hide()``・``show()``、``setAttrFlags``/``setFlags`` の ``children=``(コンパウンドアトリビュートの子へも適用)、
  ``Node.addAttr(..., safe=True)``・``connect/connectTo(..., safe=True)``・``setAlias(..., safe=True)``(再実行で既存を返す)。
- その他: ``getChildren(type=)``、複数形(``Nodes``・``Joints`` 等)の一括の書き込み(``setAttrFlags``・``resetAttrs``・``setLocked``・
  ``setColor``・``setVisibility``・``show``・``hide``・``setParent``・``setRadius`` 等)、``Selection.getChannelBoxPlugs()``・
  ``Selection.getItems()``、``MultiPlug.getElement(i)`` で未作成の要素の参照、動的 generic アトリビュートへの定数 ``Matrix``(fast も可)、
  ``Quaternion(EulerRotate)``・``Quaternion(Matrix)``、``EulerRotate(..., unit=)``、``resetAttrs``・``setAttrFlags`` に Plug も指定可。

.. rubric:: 表示とエラー文

- ``Vertex('boxShape.vtx[5]')``・``Vertices('boxShape.vtx[0:2]', ...)``・``CV``・``Selection([...])`` の読める ``repr``(無効なら ``<Vertex invalid>``)。
- 無いメソッドを呼ぶと ``'Joint' has no method or Maya attribute 'orientJoint'; use orient(). Did you mean: ...?`` のように案内する。
- Maya の Script Editor では、mlib の例外の発生場所を利用者のコードの行で表示する(``MLIB_FULL_TRACEBACK=1`` で内部の位置)。
  ``getNode`` の失敗が通知と例外の2回表示されていた問題を直した。
- 名前が一意でないときは一致したパスを3件まで表示する。``space=``・``setTranslate(1, 2, 3)``・ロックされた成分・
  ドリブンキーの既存入力・参照ノードの削除・その版に無いノード型に、直し方を示すエラー文を出す。

.. rubric:: 見送った点

- ``choice.input`` のような Maya 組み込みの generic アトリビュートへの定数マトリクスは ``TypeError`` にした。OpenMaya では書けるが、
  保存したシーンを開くと値が消えるため。マトリクスの出力を接続する。

4.1.0 (2026-10-29)
------------------

マルチアトリビュート全体(``MultiPlug``)で論理番号の存在を ``in`` で調べられるようにし、Plug の表示に型名を出すようにしました。

.. rubric:: 追加

``3 in multi`` は論理番号 3 の要素が存在するかを返します(リスト上の位置ではありません)。要素の Plug
(``multi[3] in multi``)も受け付け、整数・Plug 以外は ``TypeError`` です。値は読み出さず、欠番の要素も作りません。

``len(multi)`` は追加していません。``len`` があると ``maya.cmds`` が ``MultiPlug`` を位置 0〜len-1 の並びとして展開し、
``cmds.getAttr(multi)`` が論理番号と違う要素の値を黙って返すためです。要素数は ``len(multi.getIndices())`` で求めます。

.. rubric:: 変更

``repr`` が実際のラッパーの型名を表示します。``Plug('pma.input1D')`` だったマルチアトリビュート全体は
``MultiPlug('pma.input1D')``、``translate`` は ``Double3Plug('t.translate')``、``translateX`` は ``DoubleLinearPlug('t.translateX')``
のようになり、無効な参照は ``<MultiPlug invalid>`` のように表示します。``str()`` と ``maya.cmds`` への受け渡しは変わりません。
``repr`` の文字列を比べているコードは、新しい表示に合わせてください。

4.0.0 (2026-10-28)
------------------

要素を持つアトリビュートの呼び名を、Maya のコマンド(``addAttr -multi``・``attributeQuery -multi``・
``getAttr -multiIndices``)に合わせて「マルチアトリビュート」に統一しました。名前の変更で、互換の別名は残していません。

.. rubric:: 破壊的変更

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - 旧名
     - 新名
     - 意味
   * - ``mlib.plugs.ArrayPlug``\ (``plugs/arrayPlug.py``)
     - ``mlib.plugs.MultiPlug``\ (``plugs/multiPlug.py``)
     - マルチアトリビュート全体
   * - ``Plug.isArray()``
     - ``Plug.isMulti()``
     - マルチアトリビュート全体か
   * - ``Plug.isElement()``
     - ``Plug.isMultiElement()``
     - マルチアトリビュートの要素か(``input1D[3]`` のように番号で指すもの)
   * - ``Plug.getArray()``
     - ``Plug.getMulti()``
     - 要素から、属するマルチアトリビュートを取得する

``MultiPlug`` のメソッド(``getElement``\ ・``getElements``\ ・``removeElement``\ ・``getIndices``\ ・``getNextAvailable``\ ・
``appendMessage``\ ・``getSourceNodes``)と、``CompoundPlug``\ ・``isCompound``\ ・``isChild`` の名前は変わりません。
英語の例外メッセージも「multi attribute」「multi element」「compound attribute」に揃えました。

.. rubric:: 呼び名の対応

.. list-table::
   :header-rows: 1
   :widths: 25 25 25 25

   * - 説明文
     - mlib
     - Maya のコマンド
     - OpenMaya
   * - マルチアトリビュート
     - ``MultiPlug``\ ・``isMulti()``
     - ``-multi``
     - ``MPlug.isArray``
   * - 要素
     - ``isMultiElement()``\ ・``getMulti()``
     - ``attr[番号]``
     - ``MPlug.isElement``\ ・``array()``
   * - 論理番号
     - ``getIndices()``\ ・``getIndex()``
     - ``getAttr -multiIndices``
     - ``logicalIndex``
   * - コンパウンドアトリビュート
     - ``CompoundPlug``\ ・``isCompound()``
     - ``-attributeType compound``
     - ``MPlug.isCompound``
   * - 子
     - ``getChildren()``\ ・``isChild()``
     - ``-listChildren``
     - ``MPlug.child``\ ・``isChild``

.. rubric:: 移行手順

``ArrayPlug``\ ・``isArray(``\ ・``isElement(``\ ・``getArray(`` を ``grep`` で探し、上表の新名へ置き換えます。OpenMaya の
``MPlug.isArray`` などを直接使っている箇所は変える必要はありません。

3.0.0 (2026-10-28)
------------------

AI なしで理解・保守できる規模にするため、外部(mlrig・HTools・tools・拡張)から使われていない機能と、
ほぼ使われていない fast 経路・複数形クラス・短縮名の別名引数を削除しました。本体は 37,323 行から
27,156 行、テストは 50,147 行から 43,317 行になりました。互換の別名・入口は残していません。

.. rubric:: 削除した機能

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - 削除したもの
     - 代わりの書き方
   * - ``BlendShape``
     - ``mlib.createNode("blendShape")`` 等で取得したノードの Plug を使う、または ``cmds.blendShape``
   * - 計算ノードのラッパー(``AimMatrix``\ ・``ComposeMatrix``\ ・``PickMatrix``\ ・``BlendMatrix``\ ・``PairBlend``\ ・
       ``VectorProduct``\ ・``MultMatrix``\ ・``DecomposeMatrix``\ ・``InverseMatrix``\ ・``AngleBetween``\ ・
       ``DistanceBetween``\ ・``CurveInfo``\ ・``PointOnCurveInfo``\ ・``PointOnSurfaceInfo``\ ・``FourByFourMatrix``)
     - これらの型は動的クラス(``Node`` の派生)で返る。``getPlug("inputMatrix").connect(...)`` のように Plug で接続・設定する
   * - HIK 系(``HIKCharacterNode`` ほか 5 クラス)
     - ``cmds`` と MEL の HumanIK コマンド
   * - ``Transformation``\ 、``Transform.getTransformation`` / ``setTransformation``\ 、``Matrix.asTransformation``
     - ``getMatrix`` / ``setMatrix``\ 、``om2.MTransformationMatrix``
   * - ``Cycle``
     - ``cmds.cycleCheck``
   * - ``DagPose`` の ``merge``\ ・``reset``\ ・``addMembers``\ ・``removeMembers``\ ・``getMembers`` 系・``isAtPose`` 等(残すのは
       ``create``\ ・``fromSkinCluster``\ ・``restore``)、``SkinCluster.resetBindPose``
     - ``cmds.dagPose``
   * - コンポーネントの書込み(``PointComponent(s).setPosition*``\ ・``mirror``\ 、``UV(s).setPosition*``\ ・``setU`` / ``setV``)、
       ``Mesh.mirror``\ ・``NurbsCurve.mirror``\ ・``Transform.mirrorGeometry``
     - ``cmds.xform``\ ・``cmds.polyEditUV``\ 。コンポーネントは読み取り専用の参照になった
   * - 複数形クラス ``Transforms``\ ・``DagNodes``\ 、``Nodes`` / ``Joints`` / ``SkinClusters`` の単数への転送メソッド(約 75 個)、
       ``Nodes.callEach``\ ・``getNames``\ ・``delete``\ 、``Joints.jointOrientToRotate`` / ``freezeRotate``\ 、
       ``SkinClusters.removeInfluences``
     - ``for node in nodes: node.method(...)`` で単数を呼ぶ。一括削除は ``mlib.delete(nodes)``\ 。``Nodes`` は入力検証と
       list としての振る舞い、``Joints`` は ``sortedByDepth`` / ``getSkinClusters`` だけを持つ

.. rubric:: 削除した fast

``fast`` は ``Plug.get`` / ``set``\ ・``createNode``\ ・``delete``\ ・``setMatrix`` 系など中核の操作だけに残しました。次の
fast は、利用がほぼ無く、cmds と同じ結果を保つ補正が保守の負担になるため外しました(引数ごと削除。通常経路は残る)。

- ``mlib.duplicate``\ 、``mlib.select`` / ``Selection.select``\ 、``Namespace.create`` / ``setCurrent`` / ``rename`` / ``move`` / ``remove``
- ``Plug.setMuted`` / ``mute`` / ``unmute``\ 、``Transform.matchTransform``
- influence の除去(``SkinCluster.removeInfluence`` / ``removeUnusedInfluences``\ 、``Joint.removeInfluence``)

.. rubric:: 削除した別名引数

短縮名の別名は、Maya コマンドのフラグをそのまま受ける入口(``cmds/`` の 5 コマンド、``Node.addAttr``\ 、
``Transform.addConstraint``\ 、``Transform.makeIdentity``\ 、``getConnections`` の listConnections フラグ、
``Plug.connect`` / ``disconnect`` の ``f`` / ``l`` / ``na``)だけに残し、mlib 独自メソッドは長名だけにしました。

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 削除した別名
     - 対象(主なもの)
   * - ``ws``
     - ``Transform`` の get/set 系(``getMatrix``\ ・``setTranslate``\ ・``getPivot`` 等)、``scaleGeometry``\ 、``getBoundingBox``\ 、
       ``Mesh`` / ``NurbsCurve`` の照会、コンポーネントの ``getPosition``\ 、``restore`` / ``restoreBindPose`` → ``worldSpace``
   * - ``idx``
     - ``getShape``\ ・``getVertex``\ ・``getCV``\ ・``getElement``\ ・``removeElement``\ ・``AnimCurve`` の番号指定・
       ``getConnections`` → ``index``
   * - ``src`` / ``dst``
     - ``Plug`` の ``connect``\ ・``connectTo``\ ・``disconnect``\ ・``isConnected``\ ・``isConnectedTo``\ ・``disconnectAll``\ ・
       ``getConnections``\ 、``Joint.connectInverseScale``\ 、``Namespace.remove`` → ``source`` / ``destination``\ (Plug は主名も
       ``source`` / ``destination`` に変更。位置引数の呼出しは変わらない)
   * - ``attrs``\ 、``f``\ 、``r``\ 、``scn``
     - ``resetAttrs`` / ``setAttrFlags`` → ``attributes``\ 、``Plug.delete``\ ・``Plugin.unload``\ ・``removeMembers``\ ・
       ``removeInfluence`` 等 → ``force``\ 、``Transform.setParent`` → ``relative``\ 、``getSource`` / ``getDestinations`` →
       ``skipConversionNodes``

旧名でのキーワード指定は ``TypeError`` になります。mlrig の ``ws=`` 指定(約 15 か所)は ``worldSpace=`` へ移行済みです。

.. rubric:: 移行手順

1. 削除したクラス・メソッドを ``grep`` で探し、上表の書き方へ置き換える。
2. ``fast=True`` を付けて呼んでいた上記の操作は、``fast`` を外す(通常経路で Undo に記録される)。
3. ``ws=``\ ・``idx=``\ ・``src=`` 等の短縮名を長名へ置き換える。

2.2.0 (2026-10-27)
------------------

内部実装の表記のブレ(内部名・引数・例外・Undo チャンク名・docstring)を調べて統一し、重なっていた内部処理を
共通ヘルパーへまとめました。規則は ``docs/mlib-api-design.md`` の「内部実装の定型」に記録しています。
公開 API の名前・引数・戻り値は原則変えていませんが、例外の型と文言に次の変更があります。

.. rubric:: 破壊的変更

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - 対象
     - 変更
     - 補足
   * - 例外の型の 4 分類
     - 型違い・別名競合・必須欠落は ``TypeError``\ 、値違いは ``ValueError``\ 、シーンの状態(ロック・接続・参照・
       削除済み・不在)は ``RuntimeError``\ 、fast や実装上の未対応は ``NotImplementedError``
     - 以下はこの分類に合わせて型が変わったもの
   * - ``worldSpace`` / ``ws`` が bool 以外
     - ``ValueError`` → ``TypeError``
     - ``mlib.util._world_space`` を使う全メソッド
   * - ``DagPose.merge`` の ``currentPose`` / ``deleteSources`` が bool 以外
     - ``ValueError`` → ``TypeError``
     - —
   * - ``AimConstraint.setOffset`` / ``setRestRotate`` のロック・参照・入力接続の拒否
     - ``ValueError`` → ``RuntimeError``
     - 状態エラーに分類
   * - ``Namespace``\ ・``Plugin``\ ・``Module``\ ・``PluginPackage`` の名前、``NodeRegistry`` の型名が str 以外
     - ``ValueError`` → ``TypeError``\ (空文字は従来どおり ``ValueError``)
     - —
   * - fast と無関係な非対応(``Shape.scaleGeometry`` のメッシュ・NURBS 以外、``BlendShape.addTargetDeltas`` の
       特殊 origin / deformationOrder、``Mesh`` の並べ替え系の 6 条件)
     - ``NotImplementedError`` → ``ValueError``
     - fast の未対応だけが ``NotImplementedError``
   * - fast と単位アトリビュートの事前換算で数値・文字列でない値
     - ``RuntimeError`` → ``TypeError``
     - 通常経路の非単位型は cmds の ``RuntimeError`` のまま
   * - 例外メッセージ
     - 日本語のメッセージ約 70 件を英語化し、形式を統一(``<arg> must be <型>``\ ・``Specify only one of '<long>' and
       '<short>'``\ ・``Missing required argument: '<arg>'``\ ・``Cannot <action> an invalid <Type>``\ ・
       ``<Target> is locked|connected|referenced: <name>``\ ・``fast <method> does not support <条件>``)
     - 文言を照合しているコードは更新が必要
   * - Undo チャンク名
     - ``mlib<Class><Method>``\ (メソッド)と ``mlib<Func>``\ (``mlibCreateNode`` 等)に統一。ドット形(``mlib.cmds.*``\ ・
       ``mlib.Container.*`` 等)と短縮名(``mlibTransformMatch`` 等)を廃止。計算ノードの共通名 ``mlibCalculationEdit`` は
       ``mlib<Node><Method>`` に、``Plug.set`` は ``mlib<型別クラス>Set``\ (例 ``mlibDoubleLinearPlugSet``)に
     - Undo 履歴の表示名
   * - ``DagNode.getShape(index=0, intermediates=False, *, idx=...)``
     - 主引数名を ``idx`` から ``index`` に(位置引数の意味は不変)
     - —
   * - ``Joint.reparentChildren``
     - 入力を Node / 名前で受け、戻り値を ``self`` に(以前は ``None``)
     - —
   * - ``core.fastWrite.writable`` / ``check_range`` / ``_require_supported_type``\ 、``core.geometryEdit.setPositions``\ 、
       ``core.skinEdit.validate_removal``\ 、``core.registry.get``
     - ``require_writable`` / ``require_range`` / ``require_supported_type``\ 、``set_positions``\ 、``validate_removals``\ 、
       ``wrapper_class`` へ
     - core の内部連携名

.. rubric:: 追加

- ``Node.getConnections`` に ``src`` / ``dst`` の別名(Plug と同じ)。
- 共通ヘルパー: ``decorator._require_bool`` / ``_pick_alias`` / ``_merge_flags`` / ``_edit_context``\ 、``util._finite`` /
  ``_finite_vector`` / ``_checked_tolerance`` / ``_unique_ordered`` / ``_rethrow_init_error``\ 、``core.object._exists`` /
  ``_selection_plug`` / ``_selection_component``\ 、``core.fastWrite._ancestor_plugs`` / ``writable_compound``\ 、
  ``Node._from_name`` / ``_require_valid``\ 。bool 検査約 230 箇所、別名解消約 370 対、無効ノード検査約 35 箇所、
  ロック・参照拒否 12 箇所、プラグ階層の遡上 10 箇所を置き換えました。
- ``Plug.set`` を Template Method 化(派生は ``_set_value`` だけを override)。``Nodes.__init_subclass__`` が複数形クラスの
  ``_bulk_methods`` / ``_bulk_returns`` を ``_bulk_entries`` から合成。

.. rubric:: 修正

- ``mlib.reload()`` が、``from ..maths import Matrix`` のようにパッケージ経由で取り込んだ名前の親パッケージを依存先に
  数えず、読み直しの順序が崩れることがあった。
- ``Transform.setMatrix`` 等がアニメーション付きのチャンネルへ書けなくなっていた(``Plug.set`` の骨格化の途中で混入)。

.. rubric:: 内部名

- 検証は ``_require_<条件>``\ (旧 ``_validate_*`` / ``_check_*``)、変換は ``_resolve_<対象>``\ 、書込みの経路は
  ``_<method>_fast`` / ``_<method>_cmds`` に統一。skinCluster・blendShape の略語(``_jnt_index``\ ・``_xfer_pair``\ ・
  ``_attr``\ ・``_group`` 等)を完全語へ。``cameraFn`` 系の廃止に続き ``_dependency_name``\ 、``Vector._duplicate``\ 、
  ``_as_mvector``\ 、``Joint._unique_ordered`` 等を削除・改名。

.. rubric:: 据え置き(次版の候補)

- joint 側の回転補助(``_rotate_quaternion`` 等)の transform への統合、計算ノードの ``getResult`` の戻り型の統一、
  ``getRotateOrder`` の enum 名表の ``maths.eulerRotate`` への集約、``SkinCluster.mesh_path`` と ``Component.component_type``
  の lowerCamelCase 化、docstring の裸の ``list`` / ``tuple`` / ``dict`` 型表記(約 160 件)と概要・Returns の重複(41 件)。

2.1.0 (2026-10-27)
------------------

2.0.0 で次版へ送った項目を対応しました。読み取りを OpenMaya へ寄せ、書き込み系の ``fast`` を広げ、
公開引数を lowerCamelCase に揃えました。旧引数名・旧メソッドの互換入口は残していません。

.. rubric:: 破壊的変更

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - 旧 API
     - 新 API
     - 補足
   * - snake_case の公開引数(``transfer_to_parent``・``skin_cluster``・``max_influences``・``source_target_pairs``・
       ``weight_index``・``full_weight``・``input_offset``・``value_offset``・``input_scale``・``value_scale``・
       ``input_pivot``・``value_pivot``・``include_tip``・``parent_joint``・``uv_set``・``angle_weighted``・
       ``node_type``・``remove_namespace``・``keyword_arguments``・``with_copy_number``・``ref_vector``・
       ``include_negative``・``include_dag``・``first_only``・``seconds_per_sample``・``driver_value``・
       ``top_level_only``・``from_unit``・``to_unit``・``create_node``・``kill_with_scene``・``compress_undo``・
       ``version_plugin``・``minimum_version``・``minimum_maya``・``install_hint``・``name_or_index``)
     - 同じ意味の lowerCamelCase(``transferToParent``・``skinCluster``・``maxInfluences`` …)
     - 旧名でのキーワード指定は ``TypeError``。位置引数の呼出しは変わりません
   * - ``Camera.cameraFn()``・``Mesh.meshFn()``・``NurbsCurve.curveFn()``・``Reference.referenceFn()``
     - ``mfn()``
     - 形状データの無い mesh / nurbsCurve の ``mfn()`` は ``MFnDagNode``。形状を要する照会は ``RuntimeError``\ (以前は ``ValueError``)
   * - ``SkinCluster.fn``\ (属性)
     - ``SkinCluster.mfn()``\ (呼ぶたびに新しい ``MFnSkinCluster``)
     - —
   * - ``SkinCluster.deforms``・``bind`` の既スキン判定(形状の履歴に含まれるか)
     - 出力 geometry がその形状である skinCluster か(``DagNode.getSkinClusters`` と同じ規則)
     - 上流の別形状を変形する skinCluster は対象外になりました
   * - influence 除去の ``fast=True``\ (合計 0 の頂点を等分)
     - 通常経路(``cmds.skinCluster -removeInfluence``)と同じ距離による再配分
     - bindMethod が 0 以外で合計 0 の頂点が出る場合、負値・非有限値のウェイトは変更前に ``NotImplementedError``\ (負値は以前 ``ValueError``)。liw のロックは fast でも許可
   * - ``Node.resetAttrs()`` の省略時
     - 配列アトリビュートを除外
     - 以前は plusMinusAverage 等で ``TypeError`` になっていました

.. rubric:: 追加

- 計算ノードの ``connect*``\ ・``connectInput``\ ・``connectCurve``\ ・``connectSurface``\ ・``connectTransforms``\ ・
  ``BlendMatrix.connectTarget``/``removeTarget``\ ・``Place2dTexture.connectTexture``\ ・``File.setFilePath``/``setColorSpace``\ ・
  ``AimConstraint.setRestRotate``/``setOffset``\ ・``ScalarGraph.sum``/``multiply``/``condition`` に ``fast``。
- ``SkinClusters.removeInfluences``\ ・``Namespace.create``/``setCurrent``/``rename``/``move``/``remove``\ ・
  ``mlib.select``/``Selection.select``\ ・``Plug.setMuted``\ ・``mlib.duplicate`` に ``fast``。
  cmds と同じ結果にできない指定(名前空間の非 ASCII 名、選択の toggle・hierarchy 等、名前空間内の mute、
  インスタンスや表示レイヤーを含む複製など)は変更前に ``NotImplementedError`` です。
- ``Transform.matchTransform(fast=)``。fast は position と pivots だけで、rotation・scale は ``NotImplementedError``
  (既定が True なので、fast では ``rotation=False, scale=False`` を明示します)。
- OpenMaya で読むようにしたもの: ``Plug.isSettable``\ ・``Node.resetAttrs`` の絞込み・``Node.getHistory``\ ・
  ``Node.getPlugs``\ (フラグ無し・``keyable``\ ・``scalar``)・``IkHandle.getJoints``\ ・``listReferences``\ ・
  ``Plug.getAnimLayers``\ ・``Shape.scaleGeometry``\ (NURBS サーフェスの読取り)・``Namespace.create`` の照会・
  選択とドリブンキーの存在確認。いずれも ``test_cmds_parity.py`` 等で cmds と突き合わせています。
- ``Container`` と ``DagContainer`` の共通処理を ``_ContainerMixin`` へまとめました(公開 API と isinstance は不変)。

.. rubric:: 修正

- ``Reference.getParentReference()`` はファイルを持たない参照ノードで ``None`` を返します(以前は RuntimeError)。

.. rubric:: 据え置き

- ``ArrayPlug.getSourceNodes()`` は論理番号つきで要素ごとの接続元を返し、``getConnections(asNode=True)`` では
  代替できないため維持します。
- ``Plug.setEnumNames`` の fast は、API 2.0 が enum フィールドの削除を公開しないため ``NotImplementedError`` のままです。
- ``SkinCluster.setWeights`` の fast は ``MFnSkinCluster.setWeights`` に置き換えません(正規化と 0 の要素の扱いが
  通常経路と変わるため)。

2.0.0 (2026-10-27)
------------------

cymel に近い使い勝手を目標に、重なっていたメソッドの統合・廃止、未登録ノードタイプの
クラス自動生成、作成入口の一本化を行いました。旧 API の互換入口(別名・引数)は残していません。

.. rubric:: 破壊的変更

.. list-table::
   :header-rows: 1
   :widths: 30 30 10 30

   * - 旧 API
     - 新 API
     - 種類
     - 移行例
   * - ``Node.create(type, ...)``、``Transform.create``・``Joint.create``・``Mesh.create`` などの派生クラスの ``create``
     - :func:`mlib.createNode <mlib.cmds.createNode.createNode>`
     - 廃止
     - ``mlib.createNode("joint", name="j1", parent=grp)``
   * - ``Node(name, create=True)``、``SkinCluster(x, create=False)``
     - constructor は取得専用。作成は ``mlib.createNode``
     - 廃止
     - ``mlib.createNode("transform", name="grp")``
   * - ``createNode(query=, edit=)`` フラグ
     - 無し(作成専用)
     - 廃止
     - —
   * - ``Container.create(members, name=...)``
     - ``Container.create(name="container", members=())``
     - 引数統合
     - ``Container.create("rig", members=nodes)``
   * - 未登録ノードタイプの取得結果(登録済みの祖先クラスへフォールバック)
     - 自動生成クラス(基底は最寄りの登録クラス)。``mlib.nodes.<TypeName>`` で取得できる
     - 意味変更
     - ``type(mlib.getNode("airField1")).__name__ == "AirField"``
   * - ``Node.getType()``\ (登録表の型名)
     - ``getType(inherited=False)``。常に ``cmds.nodeType`` と同じ Maya の型名。``inherited=True`` は祖先を含む list
     - 意味変更
     - ``node.getType(inherited=True)``
   * - ``Plug.getType()``\ (Python クラス)、``Plug.getDataType()``
     - ``Plug.getType()`` が Maya のアトリビュート型名を返す(汎用型は ``None``)。クラスは ``type(plug)``
     - 意味変更 / 廃止
     - ``plug.getType() == "double3"``
   * - ``Node.getPath(full)``、``DagNode.getFullPath()``、``DagNode.getPartialPath()``
     - ``getFullName()`` / ``getName()``
     - 廃止
     - ``node.getFullName()``
   * - ``DagNode.getParentPath()``
     - ``getParent().mpath()``
     - 廃止
     - ``node.getParent().mpath()``
   * - ``DagNode.dagFn()``、``Transform.transformFn()``
     - ``mfn()``\ (最も具体的な OpenMaya function set を毎回新規に返す)
     - 改名
     - ``node.mfn().attributeCount()``
   * - ``Node.isChildOf(other)``
     - ``other.isParentOf(node)``
     - 廃止
     - ``parent.isParentOf(child)``
   * - ``Node.getAttrCount()``
     - ``mfn().attributeCount()``
     - 廃止
     - ``node.mfn().attributeCount()``
   * - ``Node.sameInstance(other)``
     - ``==``
     - 廃止
     - ``a == b``
   * - ``Node.getAssignedObjects()``、``Node.getMaterials()``
     - ``ShadingEngine.getMembers()`` / ``ShadingEngine.getShader()`` を ``getShadingEngines()`` の結果で反復
     - 廃止
     - ``[sg.getShader() for sg in node.getShadingEngines()]``
   * - ``Node.getExtraAttrs(include_children, *, asNames)``
     - ``getPlugs(userDefined=True, includeChildren=...)``。名前は ``getLongName()``
     - 廃止
     - ``[p.getLongName() for p in node.getPlugs(userDefined=True)]``
   * - ``getConnections(..., pcls=)``\ (Node / Plug)
     - 無し
     - 廃止
     - —
   * - ``DagNode.collectSkinClusters()``、``DagNodes.collectSkinClusters()``
     - ``SkinClusters(node.getSkinClusters())``
     - 廃止
     - ``mlib.nodes.SkinClusters(node.getSkinClusters())``
   * - ``Transform.getRoot()`` / ``getSiblings()`` / ``getBoundingBox()``、``Shape.isIntermediateObject()``
     - ``DagNode`` へ移動(Transform・Shape の両方から使える)
     - 移動
     - ``shape.getRoot()``
   * - ``Transform.reset(attributes=None, ...)``\ (戻り self)
     - ``resetAttrs(attributes=None, ...)``\ (戻り ``list[Plug]``。省略時は translate / rotate / scale / shear)
     - 改名 / 戻り値変更
     - ``node.resetAttrs()``
   * - ``Transform.resetPivot(worldSpace=True, *, kind, fast)``
     - ``setPivot((0, 0, 0), worldSpace=True, kind=...)``
     - 廃止
     - ``node.setPivot((0, 0, 0), worldSpace=True, kind="both")``
   * - ``Transform.freeze(...)``
     - ``makeIdentity(apply=True, ...)``
     - 廃止
     - ``node.makeIdentity(apply=True, translate=True)``
   * - ``Transform.getEuler(ws)``
     - ``getRotate(ws, order=0)``\ (同値)
     - 廃止
     - ``node.getRotate(ws=True, order=0)``
   * - ``Transform.getJointOrientQuaternion(ws)``
     - ``getQuaternion(ws, r=False)``
     - 廃止
     - ``joint.getQuaternion(r=False)``
   * - ``Transform.getShearing()`` / ``setShearing()``
     - ``getShear()`` / ``setShear()``
     - 改名
     - ``node.setShear((0.1, 0, 0))``
   * - ``Transform.getOffsetParentMatrix()`` / ``setOffsetParentMatrix()``
     - ``getPlug("offsetParentMatrix").get()`` / ``.set(value, fast=)``
     - 廃止
     - ``node.getPlug("offsetParentMatrix").set(matrix)``
   * - ``Joint.isJoint()``、``Joints.isJoint``
     - ``isinstance(x, mlib.nodes.Joint)`` / ``x.isType("joint")``
     - 廃止
     - ``node.isType("joint")``
   * - ``Plug.getPlugName(short, fullAttrPath)``
     - ``getName()`` / ``getFullName()``
     - 廃止
     - ``plug.getFullName()``
   * - ``Plug.lock``\ (``setLocked`` の別名)
     - ``setLocked()``
     - 廃止
     - ``plug.setLocked(True)``
   * - ``Plug.unlock(below, undoable=True, *, fast)``
     - ``unlock(below=False, *, fast=False)``
     - 引数統合
     - ``plug.unlock(fast=True)``
   * - ``Plug.getNextAvailable(...)``\ (非配列 Plug 上の定義)、``ArrayPlug.getNextAvailableIndex(start)``
     - ``ArrayPlug.getNextAvailable(start=-1, asPlug=False, checkLocked=True, checkChildren=True, *, vacant=False)``。``vacant=True`` が旧 ``getNextAvailableIndex``
     - 移動 / 引数統合
     - ``array.getNextAvailable(vacant=True)``
   * - ``Plug.getEnumFieldName(value)``
     - ``getEnumName(value=None)``\ (省略時は現在値の名)
     - 廃止
     - ``plug.getEnumName(2)``
   * - ``Transforms.reset`` などの複数形クラスの転送メソッド
     - 単数の表に従って削除・改名(``Nodes.mfn``・``hasFn``・``setLocked`` を追加)
     - 廃止 / 改名
     - ``joints.callEach("resetAttrs")``

.. rubric:: isinstance の約束

- 手書きクラスの ``isinstance`` は Maya の抽象祖先を含みません。``SkinCluster`` は ``Node`` の派生で、
  ``isinstance(skin, mlib.nodes.GeometryFilter)`` は False です。Maya の継承関係の判定は
  :meth:`~mlib.nodes.node.Node.isType` か ``getType(inherited=True)`` を使います。
- 自動生成クラスは「最寄りの登録クラスの派生である」ことだけを保証します。登録表の作り直し
  (``mlib.reload()``・``register``)の後は、保持していた生成クラス参照の ``isinstance`` が偽になるので
  ``mlib.nodes.<TypeName>`` を取り直します。
- ``"constraint"`` を :class:`~mlib.nodes.constraint.Constraint` として登録し、
  ``poleVectorConstraint`` の基底を ``PointConstraint`` に揃えました。

.. rubric:: 追加

- :func:`mlib.createNode <mlib.cmds.createNode.createNode>` を作成の唯一の入口にしました。
  ``fast=True`` は OpenMaya で作成し Undo に記録しません。``shared`` を ``fast`` と併用した場合は
  同名・同型のノードだけを再利用します(通常経路との差は docstring を参照)。
- 未登録ノードタイプのクラス自動生成(``mlib.nodes.<TypeName>``、基底は最寄りの登録クラス)。
  プラグインの load / unload と ``mlib.reload()`` でキャッシュを無効化します。
- ``Node.mfn()``・``hasFn(fn)``・``setLocked(state=True, *, fast=False)``・``getType(inherited=False)``。
- ``DagNode.show(fast=)`` / ``hide(fast=)``、``getRoot()`` / ``getSiblings()`` / ``getBoundingBox()`` /
  ``isIntermediateObject()`` を DagNode で提供。``getSiblings()`` は Shape では親直下の他の非中間 Shape を返します。
- ``Node.getPlugs(userDefined=True, includeChildren=True)``。ユーザー定義アトリビュートを追加順の型付き Plug で
  返します(``cmds.listAttr`` のフラグとの併用は ``TypeError``)。
- ``Transform.getRotate(worldSpace=False, *, order=None)``。``order`` を省略するか rotateOrder と同じ
  場合は現在の rotate に最も近い等価解、それ以外は素の分解値を返します。
- ``Transform.setParent(..., r=)``\ (``relative`` の短縮名)。
- ``Plug.getAlias()``・``getArray()``・``getIndex()``・``getEnumNames()``、
  ``getMin/getMax/getSoftMin/getSoftMax/getDefault(*, uiUnits=False)``。
- Plug の演算子 ``>>``\ (``connectTo``。接続先の Plug を返す)・``<<``\ (``connect``。自身を返す)・
  ``//``\ (接続先からの ``disconnect``。接続先を返す)。通常の Undo 経路だけで、配列全体への ``>>`` は
  Maya と同じく ``RuntimeError`` になるので空き要素には ``connectTo(array, nextAvailable=True)`` を使います。

.. rubric:: 移行手順

1. 作成を ``mlib.createNode("<nodeType>", ...)`` に置き換えます。``Node.create`` と ``create=True`` は
   ``AttributeError`` / ``TypeError`` になります。
2. 上表の「廃止」「改名」を ``grep`` で列挙し、新 API へ置き換えます。``Plug.getType()`` の戻り値を
   クラスと比較している箇所は ``type(plug)`` または ``isinstance`` に直します。
3. ``type(node) is mlib.nodes.Node`` のような厳密な型比較は、未登録型が自動生成クラスになるため
   ``isinstance`` か ``isType()`` に直します。
4. ``mlib.reload()`` の後は、保持していた Node / Plug / 生成クラスを取り直します。

.. rubric:: 次版の予定(2.1.0 で対応済み)

- 公開引数の snake_case 名(``input_offset``・``weight_index``・``skin_cluster``・``transfer_to_parent``・
  ``remove_namespace``・``keyword_arguments``・``include_tip``・``with_copy_number``・``max_influences`` など)の
  lowerCamelCase 化。
- ``cameraFn`` / ``meshFn`` / ``curveFn`` / ``referenceFn`` の ``mfn()`` への統合。
- 読み取りの OpenMaya 化の残り(``getHistory``・``getPlugs``・``getAnimLayers``・``listReferences``・
  ``IkHandle.getJoints``・``Plug.isSettable``)。
- 計算ノード系 ``setXxx`` と ``SkinClusters.removeInfluences``・``Transform.matchTransform``・
  ``Namespace``・``select`` の ``fast`` 追加、``setMuted``・``setEnumNames``・``duplicate`` の ``fast``。
- ``DagContainer`` の mixin 化、``ArrayPlug.getSourceNodes()`` の廃止可否。
- 仕様テスト(``test_spec_*``)のファイル名の機能別への改名。

1.0.0
-----

初版。Node / Plug / Component のラッパー、数学型、Undo 対応のデコレーター、cmds 7 コマンドを提供。
