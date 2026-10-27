変更履歴
========

mlib の版ごとの変更点です。版番号は ``mlib.__version__``・``maya/modules/mlib.mod``・
この文書の見出しに同じ値を置き、``__tests__/unit/test_static_version.py`` が三者の一致を検査します。

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
