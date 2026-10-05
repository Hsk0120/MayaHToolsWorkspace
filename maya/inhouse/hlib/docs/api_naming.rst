APIの命名と移行
==============================

今回の整理は既存APIを置き換える変更です。旧Python名の互換別名は残していません。
利用側のスクリプトも更新してください。モジュール移動を含むため、更新後はMayaを
再起動するか ``hlib.reload()`` を実行し、保持していたラッパーは取り直してください。

コマンドとオブジェクトの境界
----------------------------------------------------------------------

コマンド層はmaya.cmds、オブジェクト・数学層はOpenMayaの名前・概念を基準にします。
オブジェクトの距離はcm、角度はrad、時間は秒で、UI単位を変えても変わりません。
通常更新はcmdsでUndoに対応し、対応APIの ``fast=True`` は同じ値をom2で直接更新します。

.. list-table:: 今回の主な移行
   :header-rows: 1

   * - 旧名・旧指定
     - 新名・新指定
   * - full_name() / is_valid() / add_attribute()
     - fullName() / isValid() / addAttr()
   * - vertex_count() / cv_count() / get_cv_positions()
     - numVertices() / numCVs() / cvPositions()
   * - get_translate() / set_translate() / set_rotate()
     - getTranslation() / setTranslation() / setRotation()
   * - get_position() / set_positions()
     - getPosition() / setPositions()
   * - space=MSpace.kWorld / space=MSpace.kObject
     - ws=True / ws=False
   * - long_name / attribute_type / data_type
     - longName / attributeType / dataType
   * - from_degrees() / as_degrees() / is_equivalent()
     - fromDegrees() / asDegrees() / isEquivalent()

その他のnodes/plugs/components/math/sceneの公開メソッドもlowerCamelCaseへ統一しています。
``getTranslation`` 等の姿勢操作はhlibの複合操作です。MFnTransformの同一名・同一動作の
薄いラッパーではありません。アトリビュート値には ``plug("translate").get()`` を使います。

.. code-block:: python

   import math
   import hlib

   node = hlib.createNode("transform")
   node.plug("rotateX").set(math.pi / 2)  # rad。通常はUndo可能
   node.plug("translateX").set(100, fast=True)  # cm。Undoなし
   node.setTranslation((100, 0, 0), ws=True)
   value = node.plug("rotateX").get()
   node.plug("rotateX").set(value)  # UI単位によらず同じ角度
   print(hlib.getAttr(node.plug("rotateX")))  # コマンドのUI単位

配列型は空でも1要素でもlistを維持します。未初期化データのみNoneです。
CV番号はAPIと同じで、周期末尾の重複CVをcmdsに渡す場合は先頭の対応番号へ変換します。
JSONスナップショットは単位情報付きの保存形式を使い、適用時に境界変換します。

命名規則
----------------------------------------------------------------------

公開関数・メソッド・プロパティは、UI・環境・JSON・utils・decoratorsを含め
lowerCamelCaseへ統一します。例えば ``get_settings`` は ``getSettings``、
``undo_chunk`` は ``undoChunk``、``to_data`` は ``toData``、
``minimum_version`` プロパティは ``minimumVersion`` です。
旧名の別名は残しません。コンストラクター引数の ``minimum_version`` は維持します。

Maya標準名、om2継承メソッド、Python特殊メソッド、標準APIと通知APIの
``get_logger`` / ``raise_with_notify`` は例外です。引数・内部関数・ローカル変数は
snake_caseを使用できます。保存キー・保存フィールドは変更しません。
この表記整理によって単位、戻り値、Undo、編集範囲の仕様は変更していません。

* パッケージ: 既存の小文字名を維持。``hlib_bifrost`` 等の拡張名も変更しない。
* 一般Pythonモジュール: lowerCamelCase。例: ``eulerRotation.py``、``scriptJob.py``。
  hlibとすべての ``hlib_*`` 拡張パッケージで共通。
  内部用の先頭 ``_``、``__init__.py`` 等の特殊名、テスト探索用 ``test_*.py`` は維持する。
* ``cmds`` の関数とファイル: Mayaに合わせたcamelCase。独自コマンドも同じ規則。
* ``nodes`` のファイル: Maya nodeTypeと同じ表記。例: ``skinCluster.py``。
* クラス: PascalCase。例: ``SkinCluster``、``ChannelBox``。
* オブジェクト層の公開メソッド: lowerCamelCase。例: ``getPosition``、``setWeights``。
* Mayaの現在の状態・名前・メタ情報を取得する操作: メソッド。
* 保持している参照・番号・数学値・JSONデータ: プロパティまたはフィールド。

長短フラグ・アトリビュート名の扱いは :doc:`flag_aliases` を参照してください。

主な改名
----------------------------------------------------------------------

.. list-table:: 旧APIから新APIへの対応
   :header-rows: 1
   :widths: 45 55

   * - 旧API
     - 新API
   * - AnimCurve.inputs()
     - keyInputs()。inputs(type=...)は継承元の接続検索。
   * - BlendWeighted.inputs()
     - inputPlugs()。inputs(type=...)は継承元の接続検索。
   * - Joint.parent() / children()
     - parentJointName() / childJointNames()。戻り値は従来どおり名前。
   * - Transform.compose(matrix)
     - setMatrix(matrix)。Matrix.compose()は引き続き行列の生成。
   * - Transform.release_srt()
     - unlockAndDisconnectTransformChannels()。shearも含む。
   * - Componentのposition() / Componentsのpositions()
     - 単数形・複数形ともに getPosition()。
   * - component.x = value（y/z/u/vも同様）
     - component.setX(value)。取得はgetX()。
   * - maths.Translate
     - maths.Translation。
   * - maths.Rotate
     - maths.EulerRotation。ラジアンと回転順序を保持。度はfromDegrees()。
   * - EulerRotation.as_degrees()
     - asDegrees()。
   * - EulerRotation.order(名前の文字列)
     - orderName。order はom2と同じ番号(int、MayaのrotateOrderアトリビュートと同じ並び)になった。
   * - Transform.getRotation()(XYZ順序の値)
     - getRotation()はcmds.xformと同じくノードのrotateOrderの値になった。XYZ順序はgetEuler()。
       setRotation()の3成分もノードのrotateOrderの値として扱う。
   * - json.CurveSnapshot
     - json.NurbsCurveSnapshot。

複数形の ``getPosition()`` は単体と同名で呼べる入口として残し、
保持順の座標列を返します。``setPosition(value)`` は同じ座標を全要素へ設定、
``setPositions(values)`` は要素ごとの座標を設定します。

数学型の意味の変更
----------------------------------------------------------------------

``hlib.maths`` の Vector 系・Quaternion・EulerRotation・Matrix は OpenMaya API 2.0 の型を
継承し、意味を om2 に合わせました(詳細は :doc:`guide_maths` と :doc:`matrices`)。
以前の hlib(dataclass 版)から挙動が変わる主な点は次のとおりです。

* 値は可変で、ハッシュ不可(``dict`` のキーや ``set`` の要素にできない)。``+=`` などは
  同じオブジェクトを書き換える。``==`` は同じ om2 の系統なら型が違っても成分で比較する
  (``Translation(1, 2, 3) == Scale(1, 2, 3)`` は True、EulerRotation は順序も比較する)。
* 弱参照(``weakref.ref(value)``)は TypeError になった(om2 の型と同じく弱参照に対応しない)。
* ``Matrix`` の反復(``for x in m``・``list(m)``)は、反復を始めた時点の値の複製から読む。以前は反復中の変更も読み取っていた。
  値を弱参照で持つキャッシュなどは、値を複製して保持するか通常の参照に変える。
* 演算結果の型は、系統の違う om2 の値が左辺の一部の組み合わせ(``om2.MVector * Matrix`` など)を
  除いて hlib の型(規則と例外は :ref:`maths-result-types`)。素の om2 の値を含むリストの
  ``in`` / ``index`` / ``count`` は、Python のバージョンによって TypeError になることがある
  (:ref:`maths-comparison`)。
* ``Vector * Vector`` は内積(float)、``^`` は外積。``v * m`` は平行移動を含まない方向の変換、
  ``m * v`` は om2 と同じ列ベクトルとしての積で、以前の ``m * v`` (位置の変換)は
  ``m.transformPoint(v)``。``m @ v`` は TypeError。
* ``q1 * q2`` は om2 の順序(q1 を先に適用。以前の Hamilton 積 ``q1 ⊗ q2`` とは逆)。
  ``toSwingTwist`` の結果は ``twist * swing`` で元の回転になる。
* EulerRotation は Vector の派生ではなく(``dot`` などは無い)、``order`` は om2 の番号(int)。
  名前は ``orderName``。``euler.order == "xyz"`` のような名前との比較は例外にならず常に False に
  なるため、``euler.orderName == "xyz"`` (または ``euler.order == om2.MEulerRotation.kXYZ``)に
  書き換える。``Matrix(rotate=EulerRotation)`` はその回転順序を反映する。
* 行列の分解は ``om2.MTransformationMatrix`` の規約(行列式が負なら Z スケールが負。以前は X)。
  Euler 角は om2 の解(中間軸が 90 度を超える側になることがある)。
* ``Transform.getRotation`` / ``setRotation`` の3成分はノードの rotateOrder の値(XYZ 順序は
  ``getEuler``)。``set_*`` はスケールの符号と Euler の解を現在のチャンネル値に近いものへ揃える。
* ``Transform.setRotation(value, unit="deg")`` は value が EulerRotation / Quaternion だと ValueError
  (度として扱えるのは3成分の値だけ)。以前は EulerRotation の成分を度として読み、回転順序を無視して
  XYZ として扱っていた。EulerRotation / Quaternion はラジアンのまま ``unit="rad"`` (既定)で渡すと
  回転順序も反映される。度からは ``EulerRotation.fromDegrees(x, y, z, order)`` で作る。
* joint の ``setMatrix`` と、それを使う ``setTranslation`` / ``setRotation`` / ``setScaling`` /
  ``setShearing`` などは、jointOrient と rotateAxis を rotateOrder にかかわらず XYZ 順序の回転として
  扱う(Maya の joint の評価と同じ。不具合の修正)。以前は rotateOrder の順序で解釈していたため、
  rotateOrder が xyz 以外で、jointOrient または rotateAxis の2軸以上が 0 でない joint では、
  書き込んだ rotate による行列が要求した行列と一致しなかった。
* segmentScaleCompensate が有効な joint の ``setMatrix`` などは、joint の行列
  S·RA·R·JO·IS·T の IS(inverseScale の逆数の対角行列)を、3x3 部分へ inverseScale の対角行列を
  右から掛けて打ち消し、平行移動はそのまま使う(不具合の修正)。以前は ``1 / inverseScale`` の
  スケール行列を平行移動を含む行列全体へ右から掛けていたため、inverseScale が 1 でない(親の
  スケールが 1 でない)場合に scale と translate が誤った値になっていた。
* ``Vector()`` はゼロベクトル、``Vector(x, y)`` は z=0 (om2 と同じ)。文字列の成分
  (``Vector("1", "2", "3")``)は ValueError。添字の範囲外は負の値も IndexError。
* ``hlib.maths`` の import に Maya(mayapy または Maya 本体)が必要。以前の hlib で作った
  pickle は読み込めない(JSON の ``math:*`` 記録は読み込める)。

SkinClustersの責務
----------------------------------------------------------------------

``SkinClusters`` は保持するスキンクラスターの集合操作だけを担当します。
``gather`` / ``apply`` / ``finalize`` と、作業用の公開キャッシュは廃止しました。
jointのウェイト移送・子の再親付け・ノード削除は ``Joint.delete()`` /
``Joints.delete()`` から内部処理を呼びます。

``SkinClusters.removeInfluences(joints)`` / ``removeInfluences(joints)`` は
保持するスキンクラスターからinfluence登録だけを解除し、jointノードを残します。
remove_jointsは以前の同名APIと異なり、ノード削除を行いません。
祖先influenceがあれば加算し、なければMaya標準の再配分に任せます。
``transfer_to_parent=False`` は祖先への移送を行わず標準解除だけを実行します。
全influenceの解除は編集前にValueErrorとなります。

プロパティからメソッドへの移行
----------------------------------------------------------------------

次の照会は名前を維持し、呼び出しに ``()`` を付けます。

* Node: ``fullName``、``uuid``、``typeId``、``pluginName``、``isLocked``、``isFromReferencedFile``。
* Plug: ``name``、``fullName``、``attribute``、``parent``、各 ``is_*``、
  ``hasMin`` / ``hasMax`` / ``hasSoftMin`` / ``hasSoftMax``、
  ``min`` / ``max`` / ``softMin`` / ``softMax`` / ``default``。
* Shape: ``isIntermediateObject``。
* Camera: ``focal_length``。
* Joint: ``joint_orient``、``orientation``、``inverse_scale``。Joints: ``names``。
* Mesh: ``numVertices``、``numPolygons``、``numEdges``、``numUVs``。
* NurbsCurve: ``numCVs``、``numSpans``、``degree``、``form``。
* Component / Components: ``fullName`` / ``fullNames``。

.. code-block:: python

   import hlib

   node = hlib.createNode("transform")
   print(node.name(), node.fullName(), node.isLocked())
   plug = node.plug("translateX")
   print(plug.name(), plug.longName(), plug.isLocked())
   print(plug.node())  # 所有Nodeを返すメソッド。

``Component.shape`` / ``index``、``Components.shape`` / ``indices`` はプロパティを維持します。
``Plug.node()`` は所有ノードを取得するメソッドです。
``Vector.x`` などの数学値と、``NodeRef.uuid`` などJSONの保存済みデータも維持します。

モジュールの移動
----------------------------------------------------------------------

.. list-table:: importパスの変更
   :header-rows: 1

   * - 旧モジュール
     - 新モジュール
   * - hlib.ui.channelBox
     - hlib.ui.channelBox
   * - hlib.ui.timeSlider
     - hlib.ui.timeSlider
   * - hlib.scene.drivenKey
     - hlib.scene.drivenKey
   * - hlib.maths.eulerRotation
     - hlib.maths.eulerRotation
   * - hlib.maths.translate
     - hlib.maths.translation

``hlib.getChannelBox()`` / ``hlib.getTimeSlider()`` / ``hlib.getDrivenKey()`` のコマンド名は変わりません。
旧JSON型タグ ``math:Translate``・``math:Rotate`` は受け付けず、ValueErrorになります。
現在の型タグは ``math:Translation``・``math:EulerRotation`` です。
EulerRotationの回転順序はJSONでは従来どおり名前で保存し、読み込み後は
``orderName`` で名前、``order`` でom2の番号を取得できます。

メソッド整理後の入口
----------------------------------------------------------------------

* ノードの行列取得は ``getMatrix(ws=False)``。旧 ``decompose()`` の引数省略は
  ワールド空間だったため、移行時は ``getMatrix(ws=True)`` とします。
* DAGパスは ``path(full=False)`` / ``path(full=True)``。DGにも対応する
  ``name()`` / ``fullName()`` は別の用途として維持します。
* アトリビュート取得は ``plug()`` に統一しました。
* ``MatrixPlug.get()`` / ``set(value, fast=False)`` は対象アトリビュートだけを読み書きします。
  所有ノードの変換には ``Transform.getMatrix()`` / ``setMatrix()`` を使います。
  ``MatrixPlug`` の ``ws`` 引数と ``set_value`` は廃止しました。
* 表示は ``Transform.setVisibility(state, fast=False)``、ミュートは
  ``Plug.setMuted(state)`` で切り替えます。
* 選択の反映は ``Selection.select(mode="replace", missing="skip")``。
  ``mode`` は ``replace`` / ``add`` / ``remove`` です。
* ``ObjectSet`` / ``Container`` / ``DagPose`` のメンバー追加は ``addMembers``、
  除外を持つクラスは ``removeMembers`` です。
* 頂点等の個数は ``numVertices`` / ``numEdges`` / ``numPolygons`` /
  ``numUVs`` / ``numCVs`` / ``numSpans`` に統一しました。
* IKハンドルのジョイント取得は ``joints()`` / ``endJoint()``。
  Shapeの親取得は ``parent()``、Namespaceの切替は ``setCurrent()`` です。
* 複数コンポーネントの座標取得も ``getPosition()``。
  同一座標への設定 ``setPosition()`` と要素別設定 ``setPositions()`` は区別します。
* ウェイト移送は ``SkinCluster.transferWeights([(source, target), ...])``。
  インフルエンスの解除は ``SkinClusters.removeInfluences()`` です。
  ``SkinCluster.bind`` の最大数指定は ``max_influences`` に統一しました。
* ``PluginPackage`` の保持値 ``name`` / ``plugins`` / ``module`` /
  ``minimumVersion`` / ``minimumMaya`` はプロパティです。

これらの旧入口は残していません。ノードの入力・出力取得、回転表現の取得、
ジョイント回転のフリーズは、それぞれの意味が明確な既存メソッドを維持しています。


アトリビュートと状態設定の追加整理
----------------------------------------------------------------------

* ``Double3Plug.set`` はTransformへ委譲せず、対象チャンネルだけを書き込みます。
  旧コードで姿勢の変更を意図していた場合はTransformの ``setRotation`` 等へ移行します。
* 全Plugの ``get`` から ``ws`` を削除しました。アトリビュートの値に空間指定はありません。
* ``setLocked`` / ``set_keyable`` / ``set_channel_box`` は、それぞれ
  ``setFlags(locked=...)`` / ``setFlags(keyable=...)`` / ``setFlags(channelBox=...)``
  へ統一しました。同時指定もでき、全フラグを検証してから更新します。
* ``Joint.orientation()`` は廃止し ``getJointOrient()`` を使います。
* ``Joint.removeInfluence(..., transfer_to_parent=False)`` で祖先への移送を無効化できます。
  Jointを残してMaya標準の再配分で登録を外します。既定Trueの動作は変わりません。
* Plugin/Moduleの ``version_tuple()`` は廃止しました。
  ``version = plugin.version()`` の結果がNoneでなければ ``version.parts`` を使います。
* ``Constraint.setWeight`` は指定ターゲットを全件検証してから更新します。
  Mayaで更新中に起きたエラーの自動ロールバックは行いません。

コンポーネントの ``getX`` / ``setX`` 等は公開名を維持し、内部の軸操作を共通化しました。


部分更新と保持値の整理
----------------------------------------------------------------------

* ``AnimCurve.values()`` は ``keyValues()``、``tangent()`` は ``getTangent()``、
  ``infinity()`` は ``getInfinity()`` へ改名しました。旧名は公開しません。
* ``setInfinity(*, pre=None, post=None)`` は指定した側だけ変更します。
  両方をリセットする場合は ``pre="constant", post="constant"`` を明示します。
  位置引数は使わず、両側の値を検証してから更新します。
* ``Transform.pivot()`` は ``getPivot()`` へ改名しました。
  ``getPivot(ws=False, kind="rotate")`` と
  ``setPivot(value, ws=False, kind="rotate", preserve=True)`` は
  回転ピボットが既定です。取得・設定とも ``kind="scale"`` が使え、
  設定時は ``kind="both"`` も使えます。
  以前の設定動作を指定するには ``kind="both", preserve=False`` を渡します。
  オブジェクト空間の取得を設定と同じxformの座標解釈に揃えたため、
  スケールを持つノードで旧取得値と異なる場合があります。
  Jointへの設定は黙って無視せず ``TypeError`` にします。
* 保持値は括弧なしで参照します。対象は ``Scene.path`` / ``Scene.name``、
  ``Plugin.name`` / ``Module.name``、``Selection.items``、
  ``Viewport.name`` / ``Viewport.panel``、``Outliner.name`` です。
  ``Selection.items`` は従来どおりコピーなので、返却リストを変更しても元は変わりません。
  Mayaに照会する ``Plugin.path()`` / ``Module.path()``、
  ``ChannelBox.name()`` / ``TimeSlider.name()`` はメソッドのままです。
* ``SkinCluster.transferWeights`` は全組の形とinfluence所属を検証してから、
  指定順で移送します。同じinfluence同士の組は何もしません。
  正規化はMayaの標準処理とskinCluster設定に従い、
  実行途中のMayaエラーは自動ロールバックしません。
* ``transfer_to_parent`` はJoint・SkinCluster・SkinClustersのいずれでもboolのみを受け付けます。

単数クラスと対応する複数クラスは同じファイルにまとめる方針です。
``Joint`` / ``Joints``、``Vertex`` / ``Vertices`` などの既存配置は維持します。

表示色APIの変更
----------------------------------------------------------------------

``Node.outliner_color()`` は ``getOutlinerColor()``、
``Node.override_color()`` は ``getOverrideColor()`` に変更しました。
戻り値は ``hlib.ui.Color`` です。RGBは ``.rgb``、色番号は ``.index``、
有効形式は ``.mode`` で取得します。詳細は :doc:`node_colors` を参照してください。
``BlendColors.color()`` は ``colorPlug()`` に変更し、
数値の取得には ``getColor(index)`` を追加しました。

ノードコレクションの継承と色の戻り値
----------------------------------------------------------------------

``Nodes → DagNodes → Transforms`` の継承で、``Joints`` は ``Transforms``、
``SkinClusters`` は ``Nodes`` の派生に変更しました。
``Joints`` の構築時に非jointを黙って除外せず ``TypeError`` にします。
重複判定は同一ノード・同一DAGパスに統一し、異なるインスタンスパスを保持します。

複数形の ``getOverrideColor()`` / ``getOutlinerColor()`` は
``list[Color]`` を返します。
複数形の色setterの戻り値は各結果のリストからコレクション自身へ変わりました。
通常の一括更新もコレクション自身を返します。照会・生成結果が必要な操作は結果リストです。
``hlib.ls()`` の返却規則は維持しています。
使用例は :doc:`guide_nodes` と :doc:`node_colors` を参照してください。


取得値と参照の命名統一
----------------------------------------------------------------------

値の取得と設定は ``get_*`` / ``set_*``、接続用Plugの取得は ``*_plug()``
に統一しました。旧メソッド名の互換別名はありません。

* TimeSlider: ``getCurrentTime()``、``getPlaybackRange()``、
  ``getAnimationRange()``、``getSelectedRange()``。
* Preferences: ``getLinearUnit()``、``getAngleUnit()``、``getTimeUnit()``。
* Viewport / Outliner: ``getSettings()``。
* Workspace: ``getRule()``、ルール名一覧は ``ruleNames()``。
* SkinCluster: ``getMaxInfluences()``。
* Joint: ``getJointOrient()``、``getInverseScale()``。
* Camera: ``getFocalLength()``。Mesh: ``getPoints()``、``getNormals()``。
  NurbsCurve: ``cvPositions()``。
* Constraint / BlendShape / BlendWeighted: ``getWeights()``。
  既存のリスト・辞書などの戻り値形式は維持します。
* BlendColors: ``blenderPlug()`` はPlug、``getBlender()`` は係数の値。
* AnimCurve / BlendColors / BlendWeighted / MultMatrix / DistanceBetween:
  出力Plugは ``outputPlug()``。
* Shape / Transform: Maya APIの関数セット取得は ``dagFn()``。
* Plug: アトリビュート名の文字列は ``longName()``。
* Namespace / UiElement: 保持する名前は ``name`` プロパティ。
  Mayaへ照会する ``Node.name()`` やUIを解決する ``TimeSlider.name()`` はメソッドです。


参照対象と入力契約の整理
----------------------------------------------------------------------

以下は旧名を残さない変更です。保存済みウェイトJSONの形式は維持します。

.. list-table:: メソッドの移行
   :header-rows: 1
   :widths: 45 55

   * - 旧API
     - 新API
   * - ``BlendShape.targets()``
     - ``targetAliases()`` （文字列の一覧）
   * - ``ArrayPlug.next_available()``
     - ``nextAvailableIndex()`` （未存在の論理番号）
   * - ``AnimCurve.driver()`` / ``DrivenKey.driver()``
     - ``driverPlug()``
   * - ``DrivenKey.driven()``
     - ``drivenPlug()``
   * - ``Reference.edit_nodes()`` / ``edit_attrs()``
     - ``editNodeNames()`` / ``editAttributeNames()``
   * - ``Reference.namespace()`` （参照内容の照会）
     - ``associatedNamespace()``
   * - ``Reference.isRoot()`` （参照階層の判定）
     - ``isTopLevel()``
   * - ``PluginPackage.ensureLoaded()``
     - ``tryLoad()`` （状態文字列を返す）
   * - ``Node.add_attr()`` / ``has_attr()``
     - ``addAttr()`` / ``hasAttr()``
   * - ``Node.reset_attrs()`` / ``set_attr_flags()``
     - ``resetAttributes()`` / ``setAttributeFlags()``
   * - ``Plug.delete_attr()``
     - ``delete()``
   * - ``Node.move_attribute()``
     - ``moveAttributeOrder()`` （Channel Boxの並び順変更）
   * - ``Transform.set_visible()``
     - ``setVisibility()`` （自身のvisibilityアトリビュートだけを変更）
   * - ``Container.createNode(kind=...)``
     - ``createNode(type=...)``

``Reference.namespace()`` と ``setNamespace()`` は、継承元Nodeと同じく
referenceノード自身の名前空間を扱います。参照内容の名前空間を取得する場合は
``associatedNamespace()`` を使います。Referenceは非DAGノードなので、
継承した ``isRoot()`` はRuntimeErrorとなります。

``SkinCluster.influences()`` は文字列ではなく ``list[Node]`` を返します。
名前が必要な場合は ``[node.name() for node in skin.influences()]`` を使います。
``unusedInfluences()`` と同じ要素型になり、Joint以外のinfluenceも保持します。
``dumpWeights()`` / ``loadWeights()`` のJSON内の名前は引き続き文字列です。

入力・ウェイトの個別取得
~~~~~~~~~~~~~~~~~~~~~~~~

``MultMatrix.getInput(index)`` / ``BlendWeighted.getInput(index)`` は
既存入力の評価値を返します。``inputPlug(index)`` は同じ入力のPlugです。
未存在要素の照会はIndexErrorで、要素を作成しません。
``BlendWeighted.getWeight(index)`` は既存inputに対応する倍率を返し、
weight未設定時は要素を作らず1を返します。
``Constraint.getWeight(target)`` は指定ターゲットの値を返します。

``Plug.connectTo(target, force=True, unlock=False)`` は既存入力を置換しますが、
接続先のロックは解除しません。Maya標準 ``connectAttr(force=True)`` から
挙動を保って移行するときに使います。既定の ``unlock=True`` は従来どおり
force時に一時アンロックし、接続後に元のロックを戻します。

``hlib.scene.Cycle.find(targets=None, include_dag=True, seconds=10.0, first_only=False)``
は循環候補を ``list[Cycle]`` で返します。Noneはシーン全体で、空の対象リストは拒否します。
``cycle.plugs`` は検出順の ``tuple[Plug, ...]`` です。名前変更には追従しますが、
接続変更後は再検索が必要です。手動で ``Cycle(plugs)`` を作る場合は循環の成立を検証しません。
``getConnections()`` は現在の実接続を ``(sourcePlug, destinationPlug)`` で返し、
経路外への接続も含みます。``getParents()`` は現在のDAG親子関係を
``(parent, childNode)`` で返します。削除済み対象などの照会失敗は例外になります。
時間制限で未完了の場合や検出対象外の依存があり、結果0件は無循環の保証ではありません。
検索時間の計測・結果の文字列保存・レポート整形・画面表示はHToolsが担当します。

``Container.removeMembers(*nodes, force=False)`` は所属だけを解除します。
ネスト時は親containerへ所属が移り、``force=True`` は全containerから外します。
``removeContainer()`` はメンバーを先に外してから箱を除去します。
通常の ``delete()`` と異なり、未接続の演算ノードも残します。
ただし箱自身のアトリビュートや出力接続は残らず、迂回接続も行いません。

``publishName(name)`` は未Bindの公開名を作り、``bindAttribute(name, plug)`` が
所属ノードの内部アトリビュートと対応付けます。``publishAndBind(name, plug)`` は一括操作です。
``publishedAttributes()`` は公開名をキー、内部Plug（未BindならNone）を値とする辞書を返します。
``unbindAttribute(name)`` は公開名を残し、``unpublishName(name)`` は未Bind名を削除します。
これらはUndo可能です。ロックを自動解除せず、外部ノードを自動で所属させません。
ノードの親子アンカー公開はこのAPIの対象外です。

``hlib.nodes.DagContainer.create(name="dagContainer")`` はDAGコンテナを作ります。
``Transform`` と ``Container`` の派生型で、移動・回転、所属管理、公開操作を利用できます。
既存のdagContainerも ``Node`` で包むと自動的にこの型になります。
DAGの子はMaya標準の所属管理に従います。``removeMembers`` / ``removeContainer``
で階層を解除すると子のローカル値が維持されるため、ワールド姿勢は変化する場合があります。
Undoでは元の階層へ戻ります。

``ScalarGraph(container)`` は従来どおりcontainer内に演算を作ります。
``ScalarGraph(create_node=factory)`` は ``factory(node_type, name=...) -> Node`` を使います。
どちらか一方を指定します。生成関数側が生成物の記録と管理を担当し、
ScalarGraphは計算と接続を担当します。既存の生成物を読み取るだけではノードを作成しません。

``AimConstraint.rotationConnections()`` は回転出力の直接接続を
``(sourcePlug, destinationPlug)`` のリストで返します。複合接続は親だけを返し、
演算ノード宛ても含めます。下流探索や拘束対象の選別は行いません。
``settingPlugs()`` はRest Rotate、Offset、Aim/Up/World Up VectorのXYZ、
World Up Type、enableRestPosition、useOldOffsetCalculationを返します。
接続中の設定も含み、行列入力とウェイトは含みません。ウェイトは ``weightPlugs()`` で取得します。
``getRestRotation()`` / ``getOffset()`` はラジアンのXYZタプル、
対応する ``setRestRotation(value)`` / ``setOffset(value)`` は有限のラジアン3値を受け取ります。
setterは参照・ロック・入力接続を解除せず拒否し、Undo可能です。
Rest Rotateの設定は対象へ直接回転を設定せず、Offsetの設定はMaintain Offsetを再計算しません。
``getOutputRotation()`` は ``constraintRotateOrder`` を持つ ``EulerRotation`` を返します。
継承した ``getRotation()`` が扱う自身のTransform回転とは異なります。

``DecomposeMatrix.getInput()`` / ``inputPlug()`` は単一行列入力を扱い、
``getRotateOrder()`` はMayaの回転順序番号0〜5を返します。
``Transform.getVisibility()`` は自身のアトリビュート値を返します。
親・表示レイヤーを含む最終的な可視性判定ではありません。

成分別編集とメンバー入力
~~~~~~~~~~~~~~~~~~~~~~~~

頂点・CVの ``getX/getY/getZ`` と ``setX/setY/setZ`` は ``ws=False`` / ``ws=True`` を受け取り、
軸setterは ``fast`` にも対応して自身を返します。複数形ではスカラーを全要素へ、
数値列を保持順の各要素へ設定します。UVの ``setU/setV`` も ``fast`` と自身返却に対応しますが、
UVへ空間指定 ``ws`` / ``worldSpace`` は追加しません。通常更新はUndo可能、``fast=True`` はUndo不要の明示指定です。

``Container`` / ``DagPose`` のメンバー追加と、DagPoseの除外は可変長入力とリスト入力に対応します。
例えば ``pose.addMembers(a, b)`` と ``pose.addMembers([a, b])`` は同じです。
DagPoseは従来どおり空入力を拒否します。Containerのメンバー除外APIは追加していません。

参照・型・入力の固定規則
----------------------------------------------------------------------

``Node`` とその派生クラスは、生存中の同じMayaノードを比較します。
DAGノードでは保持するインスタンスのパスも区別します。
``sameNode(other)`` は別インスタンスも同じノードとして扱い、
``sameInstance(other)`` は同じDAGインスタンスだけをTrueにします。

ノードのハッシュは生成時のMayaハンドルから保持する固定値です。
別インスタンスが異なる比較結果でも、同じハッシュになることがあります。
Plugは所有ノードのハッシュと生成時のアトリビュートパス（配列番号を含む）を使用し、
等価比較では生存中のMPlugと生成時のアトリビュートパスを確認します。
改名・削除によって保持中のハッシュを変更しません。ハッシュ値は永続IDではなく、
JSON等へ保存して次のMayaセッションの検索に使用しないでください。

Undoキューに残る削除済み対象は生存している場合があり、同じ対象として比較できます。
完全に破棄された参照同士は等価ではありません。
動的アトリビュートの改名後に新しく取得したPlugは、保持中のPlugと生成時のアトリビュートパスが異なるため
等価にはなりません。必要な場合はアトリビュートの改名後に参照を取得し直してください。
Componentはシェイプのインスタンス・成分種類・番号で比較します。
トポロジー変更による番号の意味の変化は追跡しません。UVは現在のUVセットを扱います。
可変の数学型とColorは引き続きハッシュ不可です。

``getNode`` / ``Node`` は実際の型を自動判定します。
``Joint`` 等の具体クラスは、そのクラスまたは派生クラスに適合しなければTypeErrorです。
保持したDAGインスタンスだけが削除された場合、名前やパスを使う操作はRuntimeErrorとなり、
別インスタンスへ暗黙に切り替えません。``isValid()`` はノード自身の有効性を判定します。

ノードの対象列は「名前だけ」または「Nodeだけ」で指定します。
同じ対象列に両方を混ぜると、編集前にTypeErrorになります。
Nodeの派生型同士は同じ入力形式ですが、操作が許可する型は別途検査されます。
Plug・Component・API参照の既存受付は維持し、その受付範囲を拡張する変更ではありません。

.. code-block:: python

    skin.addInfluences(["joint1", "joint2"])
    skin.addInfluences([hlib.getNode("joint1"), hlib.getNode("joint2")])
    # 名前とNodeを同じ対象列に混ぜない

``ls()`` の戻り値規則は維持します。joint/skinCluster指定は専用コレクション、
その他はリストです。copy/sliceは参照のコピーで、シーンのノード複製ではありません。
一括操作の実行中に失敗した場合は停止し、完了済み操作を自動では戻しません。
``undoChunk`` と ``undoTransaction`` の保証範囲はそれぞれの仕様に従います。
``reload()`` 後は保持しているラッパーを取得し直してください。
旧クラスのインスタンスを新しい型へ自動移行したり、新旧間の比較を保証したりしません。

入力解決と型選択
----------------------------------------------------------------------

.. list-table:: 入口ごとの受付対象
   :header-rows: 1

   * - 入口
     - 受付対象
     - 結果
   * - ``hlib.getNode(value)`` / ``Node(value)``
     - 名前、Node、Plug、単体Component、MObject、MDagPath、MPlug
     - ノード型に対応するNode派生。Plug/Componentは所有ノード
   * - ``hlib.getPlug(value)``
     - アトリビュート名、Plug、MPlug
     - アトリビュート型に対応するPlug。既存Plugはそのまま
   * - ``node.plug(name)``
     - そのノードのアトリビュート名・アトリビュートパス
     - アトリビュート型に対応するPlug
   * - ``Nodes(values)`` と派生コレクション
     - 共通入力解決で扱える対象列
     - 要素型を検証したコレクション
   * - ``Object._input_names`` を利用するコマンドの対象引数
     - 名前・Node・Plug・Component・Components・API参照とその列
     - Mayaへ渡す名前。各コマンド固有の対象制約は別途適用

同じ対象列では名前文字列とNodeを混ぜません。独立した引数や数値まで同じ型に
揃える規則ではありません。コレクションの型制約や空列の扱いは各APIに従います。
``Object._input_names`` 等は内部APIで、利用側の通常の入口は ``hlib.getNode`` / ``hlib.getPlug`` です。

``Joint(name)`` 等のNode具象クラスは、異なる種類のノードを拒否します。
Plug派生の直接コンストラクターは、拡張実装で指定クラスを割り当てる低水準の入口として
維持しています。Nodeの具象型検証とは同一ではありません。
通常は ``hlib.getPlug`` または ``node.plug`` に型選択を任せてください。
既存Plugを ``getPlug`` に渡しただけでは有効性を再検証しません。
削除後の参照は ``isValid()`` で確認し、値操作時の検証とは区別します。

通常編集とfastの境界
----------------------------------------------------------------------

``fast`` を公開する操作はboolだけを受け付けます。通常編集は既存のUndo単位を維持し、
``fast=True`` は対応するOpenMaya更新を使います。内側の対応処理へモードを伝え、
正常終了・例外のどちらでも元のモードに戻します。fastを持たないAPIへ任意に渡すことはできません。

.. list-table:: 主な制限
   :header-rows: 1

   * - 対象
     - fastの制限
   * - Plug・Transform・Jointなどのアトリビュート更新
     - 対応するアトリビュート型とフラグのみ。未対応型・フラグはNotImplementedError
   * - Vertex/CV・UV・形状ミラー
     - 入力履歴付き形状は未対応。CV更新では周期カーブも未対応
   * - 一括操作
     - 引数形式の事前検証と全シーン条件の事前検証は別。保証は各メソッドに従う
   * - ファイル・UI・プラグイン管理
     - シーンUndoやfastによる復旧の保証対象ではない

fastの完了済み更新はUndoや ``undoTransaction`` では戻せません。
``undoChunk`` はUndoをまとめるだけで、例外時に自動で巻き戻しません。
``undoTransaction`` は巻き戻しを試みますが、その成功を保証しません。
後始末が失敗した場合は警告し、本処理が投げた例外を優先します。
復旧用ガードの作成またはチャンク終了に失敗した場合は、無関係なUndo履歴を
戻すことを避けるため、自動巻き戻しを実行しません。

解除・保存・登録の失敗
----------------------------------------------------------------------

``ScriptJobs.stop()`` は所有する全監視の解除を試みます。失敗したものは保持し、
最後にRuntimeErrorを出します。再実行では残った監視だけを解除します。
JSON保存に失敗し、一時ファイルの削除も失敗した場合は、保存の例外を再送出し、
削除の失敗を警告します。

自動公開では同じ公開クラス名の重複も拒否し、両方の定義元を示します。
拡張の登録途中に例外が起きた場合は、型登録表と公開名を登録前へ戻します。
拡張のimport自身が起こした外部SDK等の副作用までは巻き戻しません。

fastを指定できるメソッド
----------------------------------------------------------------------

以下はクラスに明示定義された入口です。派生クラスは継承した入口も利用できます。

.. list-table::
   :header-rows: 1

   * - クラス
     - メソッド
   * - ``ArrayPlug``
     - ``set``
   * - ``BlendColors``
     - ``setColor``, ``setBlender``
   * - ``BlendWeighted``
     - ``setInput``, ``setWeight``
   * - ``CompoundPlug``
     - ``set``
   * - ``Constraint``
     - ``setWeight``
   * - ``DecomposeMatrix``
     - ``setInput``, ``setRotateOrder``
   * - ``DistanceBetween``
     - ``setPoints``
   * - ``Double3Plug``
     - ``set``
   * - ``Joint``
     - ``jointOrientToRotate``, ``freezeRotation``
   * - ``Joints``
     - ``jointOrientToRotate``, ``freezeRotation``
   * - ``Locator``
     - ``setPosition``
   * - ``MatrixPlug``
     - ``set``
   * - ``Mesh``
     - ``mirror``
   * - ``MultMatrix``
     - ``setInput``
   * - ``Node``
     - ``setOutlinerColor``, ``setOverrideColor``, ``setAttributeFlags``
   * - ``Nodes``
     - ``setOverrideColor``, ``setOutlinerColor``, ``setOverrideColors``, ``setOutlinerColors``
   * - ``NurbsCurve``
     - ``mirror``
   * - ``Plug``
     - ``setFlags``, ``set``, ``reset``
   * - ``PointComponent``
     - ``setPosition``, ``setX``, ``setY``, ``setZ``
   * - ``PointComponents``
     - ``setPosition``, ``setPositions``, ``setX``, ``setY``, ``setZ``, ``mirror``
   * - ``SkinCluster``
     - ``setWeights``, ``loadWeights``, ``normalizeWeights``, ``setMaxInfluences``
   * - ``Transform``
     - ``mirror``, ``setMatrix``, ``setTranslation``, ``setRotation``, ``setScaling``, ``setShearing``, ``setVisibility``
   * - ``UV``
     - ``setPosition``, ``setU``, ``setV``
   * - ``UVs``
     - ``setPosition``, ``setPositions``, ``setU``, ``setV``

旧互換入口の廃止
----------------

* Matrixの回転指定・読み書きは ``rotate`` に統一。``rotation`` 引数・プロパティは廃止。
* Matrix.decompose()のオイラー回転キーは ``euler``。重複する ``rotation`` キーは廃止。
* ``Matrix._wrap_copy`` は廃止。内部実装は ``_wrap`` を使います。
* ``Matrix.to_mmatrix()`` は廃止。OpenMayaへはそのまま渡せます。基底型の複製が必要なら ``om2.MMatrix(matrix)`` を使います。
* ``SkinCluster.redistributeWeights()`` の曲線名は ``sine``。旧 ``sinusoidal`` はValueErrorになります。

大型ツールから共通化した操作
----------------------------------------

``hlib.utils.orientedBounds.computeOrientedBounds(points)`` は点群の共分散と
局所探索からOBBを推定します。戻り値は ``center`` (Vector)、``axes``
(3本のVector)、``size`` (3成分tuple) の辞書です。入力と同じ空間・単位を使い、
3点未満や非有限座標を拒否します。最小サイズは1e-6で、厳密な最小体積は保証しません。
同モジュールの ``sampleExtremePoints(points, direction_count=64)`` は
方向サンプルの極値点を抽出します。厳密な凸包ではありません。

``Mesh.getVertexAdjacency(ws=False)`` は頂点ID順に
``list[list[tuple[int, float]]]`` を返します。各ペアは隣接頂点IDとcm単位の
エッジ長です。ワールド指定は保持するDAGインスタンスを使用し、シーンを変更しません。
エッジID順を保ち、孤立頂点は空リスト、重複エッジは別々に返します。

空間指定の短縮フラグ
------------------------------

hlibの姿勢・形状・コンポーネントの空間指定は ``ws=True`` （ワールド）または
``ws=False`` （ローカル）です。長名 ``worldSpace`` も同じ意味で使用できます。
両方指定すると値が同じでもTypeErrorになります。bool以外はValueError
（形状情報ノードの接続APIではTypeError）、
旧 ``space=`` はTypeErrorです。距離cm・角度radという値の単位は変更しません。
通常の取得・設定はローカルが既定ですが、``resetPivot`` / ``restoreBindPose`` と
形状情報ノードの ``connectCurve`` / ``connectSurface`` は従来どおりワールドが既定です。
数学型の継承先を含むOpenMaya標準APIでは、引き続きMSpace定数を使用します。
