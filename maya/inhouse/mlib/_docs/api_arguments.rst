引数仕様
====================

単数Nodeのコンストラクタ
--------------------------------

単数の具象Nodeクラスに、キーワード専用の ``create=False`` を追加しました。
既定Falseは既存ノードの取得で、名前・Node・Plug・Component・Maya API参照の
既存の入力解決を維持します。Trueはクラスに対応するMaya nodeTypeを作成し、
最初の引数をノード名として使います。

.. code-block:: python

   from mlib.nodes import Joint, Transform, MultiplyDivide, Node

   joint = Joint("jointName", create=True)
   transform = Transform("transformName", create=True)
   multiply = MultiplyDivide("multiplyName", create=True)
   same_joint = Joint(joint.getFullName(), create=False)
   generic = Node.create("network", name="settingsNode")

``create`` はboolのみを受け付け、位置引数では指定できません。
``create=True`` は空でない文字列の名前だけを受け付けます。
未知のキーワード引数は生成前に拒否します。Mayaの ``parent`` / ``skipSelect`` 等の
作成フラグが必要な場合は、既存の ``Node.create(type, **kwargs)`` / ``mlib.createNode`` を使います。
名前の連番化、空シェイプと必要な親Transformの生成、選択状態はMaya標準の作成に従い、
通常のUndoに対応します。プラグインの扱いは既存の ``createNode`` と同じです。

``Node``・``DagNode``・``Shape``・``Constraint`` 等の作成型が確定しない基底クラス、
抽象Maya型に対応する ``AnimCurve``、geometryが必要な ``SkinCluster`` は
``create=True`` を受け付けません。SkinClusterは ``mlib.bindSkin(geometry, influences)`` /
``SkinCluster.bind(mesh, influences)`` でバインドします。
``mlib.getNode()`` / ``mlib.cmds.getNode()`` 等の取得関数とget付きの本体には、
``create`` を追加していません。詳しくは :doc:`guide_nodes` を参照してください。

lsのコンポーネント取得
----------------------------------------


``mlib.ls(sl=True, type="vertex")`` は選択頂点を ``list[Vertex]`` で返します。
``type`` / ``typ`` に指定できるコンポーネント名は ``vertex``・``edge``・``face``・
``uv``・``controlVertex`` です。単一の正式名称を指定し、別種類からの変換は行いません。
型未指定ではNode・Plug・Componentの混合リストです。範囲はflatten指定によらず単体へ展開し、
複数シェイプも同じリストで返します。対象がなければ空リストです。
既存のノード型指定・joint/skinCluster専用コレクションは維持します。
``component=`` は追加していません。

BlendShapeの追加編集API
-----------------------

``mlib.createBlendShape(base, targets=None, **kwargs)`` は新規BlendShapeを返します。
単一のベースを先頭に明示し、targetsは単体または列、None/空列なら空ターゲットで作成します。
作成フラグの長短名と通常Undoに対応し、照会・編集・fastは受け付けません。

従来の ``addTarget(target, base=None, weight_index=None, full_weight=1.0)`` と
``targetAliases/weightPlugs/weights/geometry`` は引数・戻り値とも維持します。
以下の ``target`` は既存ターゲットの整数番号、weightのエイリアス、または同じ
BlendShapeに属する登録済みweight要素のPlugです。別ノードのPlug・配列親・
weight以外・実ターゲットのない要素は受け付けません。

.. list-table:: 追加した引数と戻り値
   :header-rows: 1
   :widths: 75 25

   * - 呼び出し
     - 戻り値
   * - ``getTargetIndices(base=None)``
     - 昇順の番号リスト
   * - ``getTargetPlug(target)``
     - weightのPlug
   * - ``removeTarget(target)``
     - 自身
   * - ``replaceTarget(target, geometry, base=None, full_weight=1.0, *, fast=False)``
     - 既存weightのPlug
   * - ``duplicateTarget(target, weight_index=None, alias=None, *, fast=False)``
     - 新規weightのPlug
   * - ``mirrorTarget(target, axis="X", direction=1, base=None)``
     - 自身
   * - ``flipTarget(target, axis="X", base=None)``
     - 自身
   * - ``addInBetween(target, geometry, weight, base=None, relative=False)``
     - 親weightのPlug
   * - ``removeInBetween(target, weight)``
     - 自身
   * - ``targetEdit(target=None, state=True, full_weight=1.0)``
     - 自身。Trueで開始、Falseで終了
   * - ``dumpTargetDeltas(target, path, base=None, full_weight=1.0)``
     - 保存したPath。シーン変更なし
   * - ``loadTargetDeltas(target, path, base=None, full_weight=1.0, disconnect=False, *, fast=False)``
     - 自身。既存項目のデルタ全体を置換
   * - ``addTargetDeltas(deltas, base=None, weight_index=None, alias=None)``
     - 新規通常ターゲットのweight Plug
   * - ``getInBetweenWeights(target, base=None)``
     - ウェイトのリスト
   * - ``getTargetWeights(target, base=None)``
     - 全頂点ウェイトのリスト
   * - ``setTargetWeights(target, weights, base=None, *, fast=False)``
     - 自身
   * - ``getTargetDeltas(target, base=None, full_weight=1.0)``
     - 頂点番号とVectorの辞書
   * - ``getTargetVertices(target, base=None, full_weight=1.0, *, tolerance=0.0)``
     - 非ゼロデルタのベース頂点群(Vertices)
   * - ``setTargetDeltas(target, deltas, base=None, full_weight=1.0, disconnect=False, *, fast=False)``
     - 自身
   * - ``resetTargetVertices(target, vertices, base=None, full_weight=1.0, disconnect=False, *, fast=False)``
     - 自身
   * - ``reduceTargetDeltas(target, tolerance=0.0, base=None, full_weight=1.0, disconnect=False, *, fast=False)``
     - 自身
   * - ``dumpTargets(path)`` / ``loadTargets(path, *, fast=False)``
     - 自身

複数ベースの範囲、頂点ウェイトとデルタの更新方式、保存形式の制限は
:doc:`guide_deformers` の「blendShapeの編集・保存」を参照してください。
``resetTargetVertices`` / ``reduceTargetDeltas`` は既定で接続中のターゲット形状を
自動編集し接続を保持します。明示的な ``disconnect=True`` だけが切断してベイクします。
``setTargetDeltas`` の接続ガードは従来どおりです。
``fast`` はキーワード専用のboolです。既定FalseはUndo対応のコマンド更新、
TrueはUndoなしのOpenMaya更新です。入力と戻り値・単位は同じです。
``loadTargets(fast=True)`` は失敗時の自動ロールバックも行いません。

接続と切断
----------

``connect`` は接続先から呼びます。接続元からは ``connectTo`` を使います。
``force/f``、``lock/l``、``nextAvailable/na`` の長短名はORで評価します。

方向を選ぶ接続APIでは ``src/source`` が自身への入力、
``dst/destination`` が自身からの出力です。下表のAPIではどちらも既定で有効です。
同じ方向の名前と別名を同時に渡すと、同値でも ``TypeError`` になります。

.. list-table:: Plugの接続方向
   :header-rows: 1
   :widths: 45 55

   * - 呼び出し
     - 戻り値と方向指定
   * - ``getConnections(src=True, dst=True)``
     - 通常は相手Plugのリスト。``src/dst`` は既存の ``source/destination`` の別名
   * - ``connected(*, src=True, dst=True)``
     - 指定方向に接続があればTrue
   * - ``connectedTo(other, *, src=True, dst=True)``
     - 指定方向でotherと直結していればTrue
   * - ``disconnectAll(*, src=True, dst=True)``
     - 指定方向を全て切断し、自身を返す

``connected``・``connectedTo``・``disconnectAll`` の方向指定は
boolのキーワード専用引数です。bool以外は ``TypeError`` になります。
両Falseでは判定はFalse、通常の接続取得は空リスト、``disconnectAll`` は何もせず自身を返します。
``getConnections`` の従来の位置引数・``s/d`` は維持し、入力は ``s and source``、
出力は ``d and destination`` で評価します。``s=False, src=True`` でも入力は含めません。
子・配列要素の列挙は ``getConnections`` の ``checkChildren/checkElements`` で指定します。
``connected`` はMPlugの従来の接続状態判定を維持し、子・配列要素を列挙する検索は行いません。
``connectedTo`` と ``disconnectAll`` は対象Plugの直結だけを扱います。

.. code-block:: python

   dst.connect(src, f=True)
   src.connectTo(dst, f=True)  # 同じ接続方向
   dst.disconnect()           # 入力だけを切断し、入力元Plugを返す
   dst.disconnectInput()      # 未接続でもエラーにせず、自身を返す
   dst.disconnectAll()        # 入力と全出力を明示的に切断し、自身を返す
   plug.getConnections(src=False, dst=True)  # 出力先Plugのリスト
   plug.connected(src=True, dst=False)     # 入力の有無
   plug.connectedTo(other, src=False, dst=True)  # 自身からotherへの接続の有無
   plug.disconnectAll(src=False, dst=True)   # 出力のみ切断し、自身を返す
   element = array.connect(src, na=True)
   array.disconnect(src, na=True)

``disconnect(src=None, force=False, f=False, nextAvailable=False, na=False, *, fast=False)``
は入力接続だけを解除します。``src``（別名 ``source``）は入力元のPlug・MPlug・
アトリビュート名、またはNoneです。boolによる方向指定と ``dst/destination`` は受け付けません。
別名と元の名前の重複指定は編集前に ``TypeError`` になります。
既定の ``disconnect()`` は現在の入力を解除し、その入力元Plugを返します。
入力がない場合と、指定した相手との接続がない場合は ``RuntimeError`` です。
入力元を明示した ``nextAvailable/na`` は配列内の直接接続を検索し、
解除した接続先要素のリストを返します。
``force/f`` は接続先のロックを一時解除し、切断後に復元します。

方向を選ぶ解除は ``disconnectAll(*, src=True, dst=True)``、未接続でも
何もしない入力解除は ``disconnectInput()`` を使います。どちらも自身を返します。
子・配列要素の独立接続を展開せず、unitConversionノードも保持します。
通常の複数切断は1回のUndo/Redoにまとめ、``fast=True`` はUndoなしのOM2更新です。
``disconnectAll`` はforce指定を受け付けません。
``getSource/getDestinations`` と ``isSource/isDestination/disconnectInput/getSourceNodes`` に
方向引数はありません。``connect(src)`` と ``connectTo(dst)`` も接続相手の指定を維持します。

``force=True`` は一時的にロックを解除して接続します。
mlib拡張の ``unlock=False`` を併用するとロック解除を禁止できます。

位置・回転・行列
----------------

空間は ``ws=True`` を基本表記とし、``worldSpace=True`` も使えます。
長短名の同時指定は拒否します。

``translate`` / ``setTranslate`` の ``at`` は
0=親原点、1=translate、2=回転ピボット、3=スケールピボット、4以上=行列原点です。
既定値は2です。以前のmlibの行列原点指定は ``at=4`` へ移行してください。
``setTranslate`` はtranslateだけを書き込み、ピボット自体は動かしません。

.. code-block:: python

   position = node.getTranslate(ws=True)
   origin = node.getTranslate(ws=True, at=4)
   channels = node.setTranslate((10, 2, 3), ws=True, get=True)
   node.setTranslate((10, 2, 3), ws=True, safe=True)
   parent_inverse = node.getMatrix(ws=True, p=True, inv=True)

``quaternion`` / ``setQuaternion`` は ``ra`` (rotateAxis)、``r`` (rotate)、
``jo`` (jointOrient)で合成対象を選びます。既定は ``ra=False, r=True, jo=True`` です。
ワールド指定などで未対応の組合せはValueErrorになります。

``scale`` / ``setScale``、``shearing`` / ``setShearing`` は
ローカル指定でscale/shearチャンネルそのものを扱い、jointのinverseScaleを含めません。
ワールド指定はOpenMayaの分解規約を使います。負スケールの符号は行列から一意に
決まらないため、ワールドの指定値と取得値の符号が一致しない場合があります。
getを省いた ``scale/shear`` の取得入口は廃止しました。
設定には ``setScale/setShear`` を使用します。

``get=True`` は書き込まず設定すべき値を返します。
位置・回転・スケール・シアーは数値リスト、``setMatrix`` は
``translate/rotate/scale/shear`` をキーとする辞書を返します。
後者の辞書にはmlibの値型を格納します。
コレクションの ``get=True`` も各対象の計算結果のリストを返します。

単位とsafe
----------

Plugの ``get/set`` は内部単位(cm/rad/秒)、``get/set(uiUnits=True)`` は現在のUI単位です。
``safe=True`` は書込み失敗を抑制し、複合値では書ける子だけを書き込みます。
Plugのsafe指定は失敗数を返します。Transformのsafe指定は自身を返します。
``fast=True`` はmlib固有のUndoなし直接更新であり、safeとは別の指定です。

.. code-block:: python

   node.getPlug("ry").set(90, uiUnits=True)  # UIがdegの場合90度
   failed = node.getPlug("translate").set((1, 2, 3), safe=True)
   node.setRotate((0, 90, 0), ws=True, unit="deg")

``setRotate`` の第2位置引数は空間になりました。``unit`` は名前付きで指定します。
回転double3の ``set`` も第2位置引数はsafe、unitは名前付きです。
通常のsetterが自身を返すmlibの規則と、om2派生の数学型は維持します。
引数・戻り値の対応範囲は、このページに記載した仕様に従います。

アトリビュート参照・値・状態の取得
------------------------------------

参照は ``mlib.getPlug(target)`` または ``node.getPlug(name)`` で取得します。
既存Plugはそのまま返し、参照取得のために値を評価しません。
``mlib.getAttr`` / ``mlib.cmds.getAttr`` のラッパーは公開しません。
値は ``plug.get()`` で内部単位(cm/rad/秒)、``plug.get(uiUnits=True)`` でUI単位として読みます。
Mayaの型名・ロック・設定可否は ``getDataType()``・``isLocked()``・``isSettable()`` 等の専用メソッドを使います。
``getDataType()`` は定義型を返し、generic/kAnyはNoneです。現在値の型名が必要な場合は
``maya.cmds.getAttr(plug.getFullName(), type=True)`` で明示的に評価します。
``time`` 指定などMaya固有の照会は ``maya.cmds.getAttr(plug.getFullName(), time=...)`` を
直接呼び出します。この戻り値の形と単位はMaya標準のままです。

アトリビュートの追加
--------------------

正式名を ``addAttr`` に変更しました。旧 ``addAttribute`` は残していません。
typeを省略するとdoubleです。``at:/dt:`` 接頭辞やMayaの ``at/dt`` も使えます。
``childNames/childShortNames/childSuffixes/subType`` で子を自動生成できます。
mlibでは既定で追加したPlugを返します。``getPlug=False`` を明示した場合のみNoneを返します。

.. code-block:: python

   label = node.addAttr("label", "string", dv="control")
   offset = node.addAttr("offset", "double3", subType="doubleLinear")
   node.addAttr("weight", min=0, max=1, dv=1, k=True)
   node.rename("control", ignoreShape=True)

``rename`` の旧 ``ignore_shape`` 引数も ``ignoreShape`` へ移行しました。

ここでの ``addAttr`` はNodeのメソッドです。``mlib.addAttr(node, ...)`` は
Mayaコマンド用の入口で、従来どおり常にPlugを返し、getPlug引数は受け取りません。

ノード削除のsafe
----------------

``Node.delete(*, safe=False, fast=False)`` と ``Joint.delete``、``Nodes.delete``、``Joints.delete`` の
safeはboolのキーワード専用引数です。既定FalseはMaya標準削除です。
Trueは自身とDAG子孫のDG接続を確認し、接続があればその対象を削除しません。
戻り値は削除・スキップともNone。safeの短縮名とforceフラグはありません。
JointもNodeの標準削除を継承し、ウェイト移送や子の保持は行いません。
判定対象は :doc:`api_methods` を参照してください。

skinClusterの修復とinfluence解除
----------------------------------

.. list-table:: 引数と戻り値
   :header-rows: 1
   :widths: 75 25

   * - 呼び出し
     - 戻り値
   * - ``SkinCluster.removeInfluence(joint, transfer_to_parent=True, *, force=False)``
     - None
   * - ``Joint.removeInfluence(skin_cluster=None, *, transfer_to_parent=True, force=False)``
     - Joint自身
   * - ``SkinClusters.removeInfluences(joints, transfer_to_parent=True, *, force=False)``
     - SkinClusters自身
   * - ``SkinCluster.removeUnusedInfluences(*, force=False)``
     - 登録解除した ``list[Node]``
   * - ``SkinClusters.removeUnusedInfluences(*, force=False)``
     - 保持順の ``list[list[Node]]``
   * - ``SkinCluster.removeInvalidWeights(*, fast=False)``
     - SkinCluster自身
   * - ``SkinClusters.removeInvalidWeights(*, fast=False)``
     - SkinClusters自身

``force`` はboolのキーワード専用引数で、短縮名 ``f`` も使えます。
両名の同時指定は変更前に ``TypeError`` です。既定Falseは従来動作を維持します。
Trueは不正ウェイトを除去してからinfluenceの登録を外す指定で、
ロック解除・レイヤーの迂回・正規化ではありません。
事前検証は読取だけで、修復と登録解除は一回のUndoにまとまります。
``removeUnusedInfluences(force=True)`` で修復後に全influenceが未使用となる場合は、
修復前に ``ValueError`` になります。jointノードは削除しません。
祖先へのウェイト加算は先頭meshが対象です。NURBSなどで祖先移送が必要な場合、
``force=True`` は修復前に ``ValueError`` で停止します。

``removeInvalidWeights`` は既存の生の ``weightList`` 要素から、負値・NaN・正負の無限大・
未登録influence論理番号の要素だけを削除します。有効な0・1を超える値・合計が1でない頂点は
保持し、正規化・合計0の補填・influenceの削除は行いません。
単独の不正要素除去はNURBSの生の ``weightList`` にも使えます。
``fast`` はboolのキーワード専用引数で、既定FalseはUndo対応、TrueはUndoなしです。
ロック・入力接続・レイヤー、削除対象の出力接続は変更前に拒否します。
詳しい判定・使用例は :doc:`guide_deformers` を参照してください。

保存ポーズの統合
----------------

``DagPose.merge(sources, *, currentPose=False, deleteSources=True)`` は自身を返します。
sourcesは単体/複数の名前またはNodeで、名前とNodeの混在は不可です。
両フラグはboolのキーワード専用引数で、短縮名とfastはありません。
currentPoseは統合先を含む全対象の現在姿勢保存、deleteSourcesは元ポーズの削除です。
既定では保存済み姿勢を保持し、競合した場合は変更前に拒否します。
接続変更・Undo・対応範囲は :doc:`dag_pose` を参照してください。
