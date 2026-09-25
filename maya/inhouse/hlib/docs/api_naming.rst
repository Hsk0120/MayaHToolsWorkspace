APIの命名と移行
==============================

今回の整理は既存APIを置き換える変更です。旧Python名の互換別名は残していません。
利用側のスクリプトも更新してください。モジュール移動を含むため、更新後はMayaを
再起動するか ``hlib.reload()`` を実行し、保持していたラッパーは取り直してください。

命名規則
------------------------------

* パッケージと一般モジュール: 小文字のsnake_case。
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
   * - json.CurveSnapshot
     - json.NurbsCurveSnapshot。

複数形の ``get_position()`` は単体と同名で呼べる入口として残し、
保持順の座標列を返します。``set_position(value)`` は同じ座標を全要素へ設定、
``set_positions(values)`` は要素ごとの座標を設定します。

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
     - hlib.editors.channel_box
   * - hlib.editors.timeSlider
     - hlib.editors.time_slider
   * - hlib.animation.drivenKey
     - hlib.animation.driven_key
   * - hlib.maths.eulerRotation
     - hlib.maths.euler_rotation
   * - hlib.maths.translate
     - hlib.maths.translation

``hlib.channelBox()`` / ``hlib.timeSlider()`` / ``hlib.drivenKey()`` のコマンド名は変わりません。
JSONに保存済みの ``math:Translate`` はTranslation、``math:Rotate`` はXYZ順の
EulerRotationとして読み込めます。成分値は換算せず引き継ぎます。
