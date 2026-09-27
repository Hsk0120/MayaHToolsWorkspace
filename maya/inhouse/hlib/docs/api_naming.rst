APIの命名と移行
==============================

今回の整理は既存APIを置き換える変更です。旧Python名の互換別名は残していません。
利用側のスクリプトも更新してください。モジュール移動を含むため、更新後はMayaを
再起動するか ``hlib.reload()`` を実行し、保持していたラッパーは取り直してください。

命名規則
------------------------------

* パッケージ: 既存の小文字名を維持。``hlib_bifrost`` 等の拡張名も変更しない。
* 一般Pythonモジュール: lowerCamelCase。例: ``eulerRotation.py``、``scriptJob.py``。
  hlibとすべての ``hlib_*`` 拡張パッケージで共通。
  内部用の先頭 ``_``、``__init__.py`` 等の特殊名、テスト探索用 ``test_*.py`` は維持する。
* ``cmds`` の関数とファイル: Mayaに合わせたcamelCase。独自コマンドも同じ規則。
* ``nodes`` のファイル: Maya nodeTypeと同じ表記。例: ``skinCluster.py``。
* クラス: PascalCase。例: ``SkinCluster``、``ChannelBox``。
* 独自メソッド: snake_case。例: ``get_positions``、``set_weights``。
* Mayaの現在の状態・名前・メタ情報を取得する操作: メソッド。
* 保持している参照・番号・数学値・JSONデータ: プロパティまたはフィールド。

長短フラグ・属性名の扱いは :doc:`flag_aliases` を参照してください。

主な改名
------------------------------

.. list-table:: 旧APIから新APIへの対応
   :header-rows: 1
   :widths: 45 55

   * - 旧API
     - 新API
   * - AnimCurve.inputs()
     - key_inputs()。inputs(type=...)は継承元の接続検索。
   * - BlendWeighted.inputs()
     - input_plugs()。inputs(type=...)は継承元の接続検索。
   * - Joint.parent() / children()
     - parent_joint_name() / child_joint_names()。戻り値は従来どおり名前。
   * - Transform.compose(matrix)
     - set_matrix(matrix)。Matrix.compose()は引き続き行列の生成。
   * - Transform.release_srt()
     - unlock_and_disconnect_transform_channels()。shearも含む。
   * - Componentのposition() / Componentsのpositions()
     - get_position() / get_positions()。
   * - component.x = value（y/z/u/vも同様）
     - component.set_x(value)。取得はget_x()。
   * - maths.Translate
     - maths.Translation。
   * - maths.Rotate
     - maths.EulerRotation。ラジアンと回転順序を保持。度はfrom_degrees()。
   * - EulerRotation.asDegrees()
     - as_degrees()。
   * - EulerRotation.order(名前の文字列)
     - order_name。order はom2と同じ番号(int、MayaのrotateOrder属性と同じ並び)になった。
   * - Transform.get_rotate()(XYZ順序の値)
     - get_rotate()はcmds.xformと同じくノードのrotateOrderの値になった。XYZ順序はget_euler()。
       set_rotate()の3成分もノードのrotateOrderの値として扱う。
   * - json.CurveSnapshot
     - json.NurbsCurveSnapshot。

複数形の ``get_position()`` は単体と同名で呼べる入口として残し、
保持順の座標列を返します。``set_position(value)`` は同じ座標を全要素へ設定、
``set_positions(values)`` は要素ごとの座標を設定します。

数学型の意味の変更
------------------------------

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
  ``m.transform_point(v)``。``m @ v`` は TypeError。
* ``q1 * q2`` は om2 の順序(q1 を先に適用。以前の Hamilton 積 ``q1 ⊗ q2`` とは逆)。
  ``to_swing_twist`` の結果は ``twist * swing`` で元の回転になる。
* EulerRotation は Vector の派生ではなく(``dot`` などは無い)、``order`` は om2 の番号(int)。
  名前は ``order_name``。``euler.order == "xyz"`` のような名前との比較は例外にならず常に False に
  なるため、``euler.order_name == "xyz"`` (または ``euler.order == om2.MEulerRotation.kXYZ``)に
  書き換える。``Matrix(rotate=EulerRotation)`` はその回転順序を反映する。
* 行列の分解は ``om2.MTransformationMatrix`` の規約(行列式が負なら Z スケールが負。以前は X)。
  Euler 角は om2 の解(中間軸が 90 度を超える側になることがある)。
* ``Transform.get_rotate`` / ``set_rotate`` の3成分はノードの rotateOrder の値(XYZ 順序は
  ``get_euler``)。``set_*`` はスケールの符号と Euler の解を現在のチャンネル値に近いものへ揃える。
* ``Transform.set_rotate(value, unit="deg")`` は value が EulerRotation / Quaternion だと ValueError
  (度として扱えるのは3成分の値だけ)。以前は EulerRotation の成分を度として読み、回転順序を無視して
  XYZ として扱っていた。EulerRotation / Quaternion はラジアンのまま ``unit="rad"`` (既定)で渡すと
  回転順序も反映される。度からは ``EulerRotation.from_degrees(x, y, z, order)`` で作る。
* joint の ``set_matrix`` と、それを使う ``set_translate`` / ``set_rotate`` / ``set_scale`` /
  ``set_shear`` などは、jointOrient と rotateAxis を rotateOrder にかかわらず XYZ 順序の回転として
  扱う(Maya の joint の評価と同じ。不具合の修正)。以前は rotateOrder の順序で解釈していたため、
  rotateOrder が xyz 以外で、jointOrient または rotateAxis の2軸以上が 0 でない joint では、
  書き込んだ rotate による行列が要求した行列と一致しなかった。
* segmentScaleCompensate が有効な joint の ``set_matrix`` などは、joint の行列
  S·RA·R·JO·IS·T の IS(inverseScale の逆数の対角行列)を、3x3 部分へ inverseScale の対角行列を
  右から掛けて打ち消し、平行移動はそのまま使う(不具合の修正)。以前は ``1 / inverseScale`` の
  スケール行列を平行移動を含む行列全体へ右から掛けていたため、inverseScale が 1 でない(親の
  スケールが 1 でない)場合に scale と translate が誤った値になっていた。
* ``Vector()`` はゼロベクトル、``Vector(x, y)`` は z=0 (om2 と同じ)。文字列の成分
  (``Vector("1", "2", "3")``)は ValueError。添字の範囲外は負の値も IndexError。
* ``hlib.maths`` の import に Maya(mayapy または Maya 本体)が必要。以前の hlib で作った
  pickle は読み込めない(JSON の ``math:*`` 記録は読み込める)。

SkinClustersの責務
------------------------------

``SkinClusters`` は保持するスキンクラスターの集合操作だけを担当します。
``gather`` / ``apply`` / ``finalize`` と、作業用の公開キャッシュは廃止しました。
jointのウェイト移送・子の再親付け・ノード削除は ``Joint.delete()`` /
``Joints.delete()`` から内部処理を呼びます。

``SkinClusters.remove_joints(joints)`` / ``remove_influences(joints)`` は
保持するスキンクラスターからinfluence登録だけを解除し、jointノードを残します。
remove_jointsは以前の同名APIと異なり、ノード削除を行いません。
祖先influenceがあれば加算し、なければMaya標準の再配分に任せます。
``transfer_to_parent=False`` は祖先への移送を行わず標準解除だけを実行します。
全influenceの解除は編集前にValueErrorとなります。

プロパティからメソッドへの移行
----------------------------------------

次の照会は名前を維持し、呼び出しに ``()`` を付けます。

* Node: ``full_name``、``uuid``、``type_id``、``plugin_name``、``is_locked``、``is_referenced``。
* Plug: ``name``、``full_name``、``attribute``、``parent``、各 ``is_*``、
  ``has_min`` / ``has_max`` / ``has_soft_min`` / ``has_soft_max``、
  ``min`` / ``max`` / ``soft_min`` / ``soft_max`` / ``default``。
* Shape: ``is_intermediate_object``。
* Camera: ``focal_length``。
* Joint: ``joint_orient``、``orientation``、``inverse_scale``。Joints: ``names``。
* Mesh: ``num_vertices``、``num_polygons``、``num_edges``、``num_uvs``。
* NurbsCurve: ``num_cvs``、``num_spans``、``degree``、``form``。
* Component / Components: ``full_name`` / ``full_names``。

.. code-block:: python

   import hlib

   node = hlib.createNode("transform")
   print(node.name(), node.full_name(), node.is_locked())
   plug = node.plug("translateX")
   print(plug.name(), plug.attribute(), plug.is_locked())
   print(plug.node)  # 保持している所有Node。プロパティのまま。

``Component.shape`` / ``index``、``Components.shape`` / ``indices``、
``Plug.node`` は保持した参照・番号なのでプロパティを維持します。
``Vector.x`` などの数学値と、``NodeRef.uuid`` などJSONの保存済みデータも維持します。

モジュールの移動
------------------------------

.. list-table:: importパスの変更
   :header-rows: 1

   * - 旧モジュール
     - 新モジュール
   * - hlib.editors.channelBox
     - hlib.editors.channelBox
   * - hlib.editors.timeSlider
     - hlib.editors.timeSlider
   * - hlib.animation.drivenKey
     - hlib.animation.drivenKey
   * - hlib.maths.eulerRotation
     - hlib.maths.eulerRotation
   * - hlib.maths.translate
     - hlib.maths.translation

``hlib.channelBox()`` / ``hlib.timeSlider()`` / ``hlib.drivenKey()`` のコマンド名は変わりません。
JSONに保存済みの ``math:Translate`` はTranslation、``math:Rotate`` はXYZ順の
EulerRotationとして読み込めます。成分値は換算せず引き継ぎます。
EulerRotationの回転順序はJSONでは従来どおり名前で保存し、読み込み後は
``order_name`` で名前、``order`` でom2の番号を取得できます。
