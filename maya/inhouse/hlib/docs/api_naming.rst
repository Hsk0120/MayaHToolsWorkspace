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
* 独自メソッド: snake_case。例: ``get_position``、``set_weights``。
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
     - 単数形・複数形ともに get_position()。
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

``SkinClusters.remove_influences(joints)`` / ``remove_influences(joints)`` は
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
* Mesh: ``vertex_count``、``polygon_count``、``edge_count``、``uv_count``。
* NurbsCurve: ``cv_count``、``span_count``、``degree``、``form``。
* Component / Components: ``full_name`` / ``full_names``。

.. code-block:: python

   import hlib

   node = hlib.createNode("transform")
   print(node.name(), node.full_name(), node.is_locked())
   plug = node.plug("translateX")
   print(plug.name(), plug.attribute_name(), plug.is_locked())
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
   * - hlib.general.channelBox
     - hlib.general.channelBox
   * - hlib.general.timeSlider
     - hlib.general.timeSlider
   * - hlib.general.drivenKey
     - hlib.general.drivenKey
   * - hlib.maths.eulerRotation
     - hlib.maths.eulerRotation
   * - hlib.maths.translate
     - hlib.maths.translation

``hlib.getChannelBox()`` / ``hlib.getTimeSlider()`` / ``hlib.getDrivenKey()`` のコマンド名は変わりません。
JSONに保存済みの ``math:Translate`` はTranslation、``math:Rotate`` はXYZ順の
EulerRotationとして読み込めます。成分値は換算せず引き継ぎます。
EulerRotationの回転順序はJSONでは従来どおり名前で保存し、読み込み後は
``order_name`` で名前、``order`` でom2の番号を取得できます。

メソッド整理後の入口
------------------------------

* ノードの行列取得は ``get_matrix(ws=False)``。旧 ``decompose()`` の引数省略は
  ワールド空間だったため、移行時は ``get_matrix(ws=True)`` とします。
* DAGパスは ``path(full=False)`` / ``path(full=True)``。DGにも対応する
  ``name()`` / ``full_name()`` は別の用途として維持します。
* 属性取得は ``plug()`` に統一しました。
* ``MatrixPlug.get()`` / ``set(value, fast=False)`` は対象属性だけを読み書きします。
  所有ノードの変換には ``Transform.get_matrix()`` / ``set_matrix()`` を使います。
  ``MatrixPlug`` の ``ws`` 引数と ``set_value`` は廃止しました。
* 表示は ``Transform.set_visibility(state, fast=False)``、ミュートは
  ``Plug.set_muted(state)`` で切り替えます。
* 選択の反映は ``Selection.select(mode="replace", missing="skip")``。
  ``mode`` は ``replace`` / ``add`` / ``remove`` です。
* ``ObjectSet`` / ``Container`` / ``DagPose`` のメンバー追加は ``add_members``、
  除外を持つクラスは ``remove_members`` です。
* 頂点等の個数は ``vertex_count`` / ``edge_count`` / ``polygon_count`` /
  ``uv_count`` / ``cv_count`` / ``span_count`` に統一しました。
* IKハンドルのジョイント取得は ``joints()`` / ``end_joint()``。
  Shapeの親取得は ``parent_node()``、Namespaceの切替は ``set_current()`` です。
* 複数コンポーネントの座標取得も ``get_position()``。
  同一座標への設定 ``set_position()`` と要素別設定 ``set_positions()`` は区別します。
* ウェイト移送は ``SkinCluster.transfer_weights([(source, target), ...])``。
  インフルエンスの解除は ``SkinClusters.remove_influences()`` です。
  ``SkinCluster.bind`` の最大数指定は ``max_influences`` に統一しました。
* ``PluginPackage`` の保持値 ``name`` / ``plugins`` / ``module`` /
  ``minimum_version`` / ``minimum_maya`` はプロパティです。

これらの旧入口は残していません。ノードの入力・出力取得、回転表現の取得、
ジョイント回転のフリーズは、それぞれの意味が明確な既存メソッドを維持しています。


属性と状態設定の追加整理
------------------------

* ``Double3Plug.set`` はTransformへ委譲せず、対象チャンネルだけを書き込みます。
  旧コードで姿勢の変更を意図していた場合はTransformの ``set_rotate`` 等へ移行します。
* 全Plugの ``get`` から ``ws`` を削除しました。属性の値に空間指定はありません。
* ``set_locked`` / ``set_keyable`` / ``set_channel_box`` は、それぞれ
  ``set_flags(locked=...)`` / ``set_flags(keyable=...)`` / ``set_flags(channel_box=...)``
  へ統一しました。同時指定もでき、全フラグを検証してから更新します。
* ``Joint.orientation()`` は廃止し ``get_joint_orient()`` を使います。
* ``Joint.remove_influence(..., transfer_to_parent=False)`` で祖先への移送を無効化できます。
  Jointを残してMaya標準の再配分で登録を外します。既定Trueの動作は変わりません。
* Plugin/Moduleの ``version_tuple()`` は廃止しました。
  ``version = plugin.version()`` の結果がNoneでなければ ``version.parts`` を使います。
* ``Constraint.set_weight`` は指定ターゲットを全件検証してから更新します。
  Mayaで更新中に起きたエラーの自動ロールバックは行いません。

コンポーネントの ``get_x`` / ``set_x`` 等は公開名を維持し、内部の軸操作を共通化しました。


部分更新と保持値の整理
----------------------

* ``AnimCurve.values()`` は ``key_values()``、``tangent()`` は ``get_tangent()``、
  ``infinity()`` は ``get_infinity()`` へ改名しました。旧名は公開しません。
* ``set_infinity(*, pre=None, post=None)`` は指定した側だけ変更します。
  両方をリセットする場合は ``pre="constant", post="constant"`` を明示します。
  位置引数は使わず、両側の値を検証してから更新します。
* ``Transform.pivot()`` は ``get_pivot()`` へ改名しました。
  ``get_pivot(ws=False, kind="rotate")`` と
  ``set_pivot(value, ws=False, kind="rotate", preserve=True)`` は
  回転ピボットが既定です。取得・設定とも ``kind="scale"`` が使え、
  設定時は ``kind="both"`` も使えます。
  以前の設定動作を指定するには ``kind="both", preserve=False`` を渡します。
  オブジェクト空間の取得を設定と同じxformの座標解釈に揃えたため、
  スケールを持つノードで旧取得値と異なる場合があります。
  Jointへの設定は黙って無視せず ``TypeError`` にします。
* 保持値は括弧なしで参照します。対象は ``Scene.path`` / ``Scene.name``、
  ``Plugin.name`` / ``Module.name``（複数形の ``Plugins.name`` は名前のリスト）、``Selection.items``、
  ``Viewport.name`` / ``Viewport.panel``、``Outliner.name`` です。
  ``Selection.items`` は従来どおりコピーなので、返却リストを変更しても元は変わりません。
  Mayaに照会する ``Plugin.path()`` / ``Module.path()``、
  ``ChannelBox.name()`` / ``TimeSlider.name()`` はメソッドのままです。
* ``SkinCluster.transfer_weights`` は全組の形とinfluence所属を検証してから、
  指定順で移送します。同じinfluence同士の組は何もしません。
  正規化はMayaの標準処理とskinCluster設定に従い、
  実行途中のMayaエラーは自動ロールバックしません。
* ``transfer_to_parent`` はJoint・SkinCluster・SkinClustersのいずれでもboolのみを受け付けます。

単数クラスと対応する複数クラスは同じファイルにまとめる方針です。
``Joint`` / ``Joints``、``Vertex`` / ``Vertices`` などの既存配置は維持します。

表示色APIの変更
------------------------------

``Node.outliner_color()`` は ``get_outliner_color()``、
``Node.override_color()`` は ``get_override_color()`` に変更しました。
戻り値は ``hlib.general.Color`` です。RGBは ``.rgb``、色番号は ``.index``、
有効形式は ``.mode`` で取得します。詳細は :doc:`node_colors` を参照してください。
``BlendColors.color()`` は ``color_plug()`` に変更し、
数値の取得には ``get_color(index)`` を追加しました。

ノードコレクションの継承と色の戻り値
----------------------------------------

``Nodes`` / ``Transforms`` を追加し、``Joints`` は ``Transforms``、
``SkinClusters`` は ``Nodes`` の派生に変更しました。
``Joints`` の構築時に非jointを黙って除外せず ``TypeError`` にします。
重複判定は同一ノード・同一DAGパスに統一し、異なるインスタンスパスを保持します。

複数形の ``get_override_color()`` / ``get_outliner_color()`` は
``list[Color]`` から ``Colors`` に変わりました。
複数形の色setterの戻り値は各結果のリストからコレクション自身へ変わりました。
他の通常一括メソッドの戻り値や ``hlib.ls()`` の返却規則は維持しています。
使用例は :doc:`guide_nodes` と :doc:`node_colors` を参照してください。


取得値と参照の命名統一
----------------------

値の取得と設定は ``get_*`` / ``set_*``、接続用Plugの取得は ``*_plug()``
に統一しました。旧メソッド名の互換別名はありません。

* TimeSlider: ``get_current_time()``、``get_playback_range()``、
  ``get_animation_range()``、``get_selected_range()``。
* Units: ``get_linear()``、``get_angle()``、``get_time()``。
* Viewport / Outliner: ``get_settings()``。
* Workspace: ``get_rule()``、ルール名一覧は ``rule_names()``。
* SkinCluster: ``get_max_influences()``。
* Joint: ``get_joint_orient()``、``get_inverse_scale()``。
* Camera: ``get_focal_length()``。Mesh: ``get_points()``、``get_normals()``。
  NurbsCurve: ``get_cv_positions()``。
* Constraint / BlendShape / BlendWeighted: ``get_weights()``。
  既存のリスト・辞書などの戻り値形式は維持します。
* BlendColors: ``blender_plug()`` はPlug、``get_blender()`` は係数の値。
* AnimCurve / BlendColors / BlendWeighted / MultMatrix / DistanceBetween:
  出力Plugは ``output_plug()``。
* Shape / Transform: Maya APIの関数セット取得は ``dag_fn()``。
* Plug: 属性名の文字列は ``attribute_name()``。
* Namespace / UiElement: 保持する名前は ``name`` プロパティ。
  Mayaへ照会する ``Node.name()`` やUIを解決する ``TimeSlider.name()`` はメソッドです。


参照対象と入力契約の整理
------------------------

以下は旧名を残さない変更です。保存済みウェイトJSONの形式は維持します。

.. list-table:: メソッドの移行
   :header-rows: 1
   :widths: 45 55

   * - 旧API
     - 新API
   * - ``BlendShape.targets()``
     - ``target_aliases()`` （文字列の一覧）
   * - ``ArrayPlug.next_available()``
     - ``next_available_index()`` （未存在の論理番号）
   * - ``AnimCurve.driver()`` / ``DrivenKey.driver()``
     - ``driver_plug()``
   * - ``DrivenKey.driven()``
     - ``driven_plug()``
   * - ``Reference.edit_nodes()`` / ``edit_attrs()``
     - ``edit_node_names()`` / ``edit_attribute_names()``
   * - ``Reference.namespace()`` （参照内容の照会）
     - ``associated_namespace()``
   * - ``Reference.is_root()`` （参照階層の判定）
     - ``is_top_level()``
   * - ``PluginPackage.ensure_loaded()``
     - ``try_load()`` （状態文字列を返す）
   * - ``Node.add_attr()`` / ``has_attr()``
     - ``add_attribute()`` / ``has_attribute()``
   * - ``Node.reset_attrs()`` / ``set_attr_flags()``
     - ``reset_attributes()`` / ``set_attribute_flags()``
   * - ``Plug.delete_attr()``
     - ``delete_attribute()``
   * - ``Node.move_attribute()``
     - ``move_attribute_order()`` （Channel Boxの並び順変更）
   * - ``Transform.set_visible()``
     - ``set_visibility()`` （自身のvisibility属性だけを変更）
   * - ``Container.create_node(kind=...)``
     - ``create_node(type=...)``

``Reference.namespace()`` と ``set_namespace()`` は、継承元Nodeと同じく
referenceノード自身の名前空間を扱います。参照内容の名前空間を取得する場合は
``associated_namespace()`` を使います。Referenceは非DAGノードなので、
継承した ``is_root()`` はRuntimeErrorとなります。

``SkinCluster.influences()`` は文字列ではなく ``list[Node]`` を返します。
名前が必要な場合は ``[node.name() for node in skin.influences()]`` を使います。
``unused_influences()`` と同じ要素型になり、Joint以外のinfluenceも保持します。
``dump_weights()`` / ``load_weights()`` のJSON内の名前は引き続き文字列です。

入力・ウェイトの個別取得
~~~~~~~~~~~~~~~~~~~~~~~~

``MultMatrix.get_input(index)`` / ``BlendWeighted.get_input(index)`` は
既存入力の評価値を返します。``input_plug(index)`` は同じ入力のPlugです。
未存在要素の照会はIndexErrorで、要素を作成しません。
``BlendWeighted.get_weight(index)`` は既存inputに対応する倍率を返し、
weight未設定時は要素を作らず1を返します。
``Constraint.get_weight(target)`` は指定ターゲットの値を返します。

``DecomposeMatrix.get_input()`` / ``input_plug()`` は単一行列入力を扱い、
``get_rotate_order()`` はMayaの回転順序番号0〜5を返します。
``Transform.get_visibility()`` は自身の属性値を返します。
親・表示レイヤーを含む最終的な可視性判定ではありません。

成分別編集とメンバー入力
~~~~~~~~~~~~~~~~~~~~~~~~

頂点・CVの ``get_x/get_y/get_z`` と ``set_x/set_y/set_z`` は ``ws`` を受け取り、
軸setterは ``fast`` にも対応して自身を返します。複数形ではスカラーを全要素へ、
数値列を保持順の各要素へ設定します。UVの ``set_u/set_v`` も ``fast`` と自身返却に対応しますが、
UVへ空間指定 ``ws`` は追加しません。通常更新はUndo可能、``fast=True`` はUndo不要の明示指定です。

``Container`` / ``DagPose`` のメンバー追加と、DagPoseの除外は可変長入力とリスト入力に対応します。
例えば ``pose.add_members(a, b)`` と ``pose.add_members([a, b])`` は同じです。
DagPoseは従来どおり空入力を拒否します。Containerのメンバー除外APIは追加していません。
