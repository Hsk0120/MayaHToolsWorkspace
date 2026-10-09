ノードとTransform
============================================================

ノードの状態・階層・ピボット・表示と変換を扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

ノードの継承
------------

``Node`` はDGノード全般、``DagNode`` はDAG階層を持つノードの共通基底です。
``Transform`` と ``Shape`` はどちらも ``DagNode`` を継承します。
ShapeがTransformの子に置かれることと、クラスの継承関係は別です。

.. code-block:: text

   Node
   └─ DagNode
      ├─ Transform
      │  └─ Joint
      └─ Shape
         ├─ Mesh
         └─ NurbsCurve

``mpath()``・``dagFn()``・``parentPath()``・``parent()`` は
``DagNode`` に共通実装があります。Shapeの ``parent()`` は
親がTransformの場合だけ返します。
``hlib.node()`` は引き続きノード型に対応する具象クラスを返します。
保持していたインスタンスのパスが無効になった場合、別インスタンスへ切り替えません。

クラスからノードを作成する
--------------------------

単数の具象Nodeクラスは、コンストラクタに ``create=True`` を指定して作成できます。
クラスに対応するMaya nodeTypeを使い、最初の引数をノード名として渡します。
``create=False`` が既定で、省略した場合は従来どおり既存ノードを取得します。

.. code-block:: python

   from hlib.nodes import Joint, Transform, MultiplyDivide, Mesh, Node

   joint = Joint("jointName", create=True)
   transform = Transform("controlName", create=True)
   multiply = MultiplyDivide("multiplyName", create=True)
   existing_joint = Joint(joint.fullName())  # create=Falseで同じノードを取得

   empty_mesh = Mesh("emptyMeshShape", create=True)
   print(empty_mesh.type())                 # mesh。まだ形状データはありません。

   # 汎用Nodeで作成する場合はMaya nodeTypeを明示します。
   settings = Node.create("network", name="settingsNode")

同名ノードがある場合はMayaの命名規則で連番化され、返すラッパーは実際に作成したノードを指します。
Shapeの具象クラスで作る場合は空シェイプになり、必要な親TransformもMayaが生成します。
形状データを持たない空シェイプでは、``meshFn()`` や ``numVertices()`` 等の
形状データを必要とする照会は利用できません。ポリゴンの形状も作る場合は
``hlib.createPolygon()`` を使ってください。
選択状態の扱いは ``maya.cmds.createNode`` と同じです。通常のUndoで作成を戻せます。
作成に必要なプラグインの扱いも既存の ``createNode`` と同じ規則に従います。

``create`` はboolのキーワード専用引数です。``create=True`` の名前には
空でない文字列を指定します。未知のキーワード引数はノードを生成する前に拒否します。
``parent`` や ``skipSelect`` 等のMaya作成フラグを指定する場合は、
``Node.create("transform", name="control", parent=parent)`` または ``hlib.createNode`` を使います。

``Node``・``DagNode``・``Shape``・``Constraint`` のように作成型が確定しない基底クラスや、
Mayaの抽象型に対応する ``AnimCurve`` は ``create=True`` で作成できません。
``SkinCluster`` はgeometryとのバインドが必要なので、
``hlib.bindSkin(geometry, influences)`` または ``SkinCluster.bind(mesh, influences)`` を使います。
取得関数の ``hlib.node()`` / ``hlib.cmds.node()`` とget付きの取得関数には、
``create`` 引数を追加していません。

Transform のピボット
---------------------

.. code-block:: python

   transform = hlib.node("pCube1")
   print(transform.pivot())              # 既定は (0, 0, 0)
   transform.setPivot((1.0, 2.0, 3.0), kind="both")  # 回転・スケールピボットをまとめて設定
   print(transform.pivot(ws=True))       # ワールド空間での現在位置

``pivot`` / ``setPivot`` は ``kind="rotate"`` が既定です。
``kind="scale"`` でスケールピボットだけを扱えます。設定時の ``kind="both"`` は
両方を同じ位置へ変更します。値・戻り値は Maya API の内部距離単位（cm）です。
``ws=True`` はワールド空間、既定Falseは ``cmds.xform`` のオブジェクト空間です。

設定時は ``preserve=True`` が既定で、変換行列を維持します。
補償を行わずピボットを動かす場合は ``preserve=False`` を指定します。
Jointは独立したピボットの変更をサポートしないため、``setPivot`` は更新前に
``TypeError`` を送出します。

バウンディングボックス
-----------------------

.. code-block:: python

   mesh_transform = hlib.node("pCube1")
   print(mesh_transform.boundingBox())          # 自身の変換は含むが親の変換は含まない
   print(mesh_transform.boundingBox(ws=True))    # 親の変換も含めたワールド空間

``boundingBox`` は ``MFnDagNode.boundingBox`` をそのまま使うため、
``ws=False``（既定）でも自身の translate/rotate/scale は反映されます。
``cmds.xform(node, query=True, boundingBox=True)`` と同じ考え方で、
親から継承した変換だけを含まない座標系です。``ws=True`` で親のワールド行列も
適用した真のワールド空間の境界ボックスになります。戻り値は
``om2.MBoundingBox`` で、``.min``/``.max`` から座標を取得できます。

ノードの状態照会と階層クエリ
----------------------------

.. code-block:: python

   grandparent = hlib.createNode("transform", name="grandparent")
   parent = hlib.createNode("transform", name="parent")
   child = hlib.createNode("transform", name="child")
   parent.setParent(grandparent)
   child.setParent(parent)

   print(child.locked())                        # False
   print(child.fromReferencedFile())                     # False（参照シーンなら True）
   print(child.isType("transform"))               # True
   print(child.isType("dagNode"))                 # True（継承チェーンも判定）
   print(grandparent.ancestorOf(child))         # True
   print(child.root() is grandparent or child.root().fullName() == grandparent.fullName())

   plug = child.plug("translateX")
   print(plug.keyable())                          # True
   print(plug.parent().fullName())                    # child.translate

``isType`` は ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
mesh シェイプは ``isType("shape")`` でも True になります。``root()`` は DAG 階層の
最上位祖先を返し、自身がワールド直下ならそのまま自身を返します。
``Shape`` には同様に ``intermediateObject`` があります。

ノードの名前と取得
------------------

``str(node)`` と ``node.name()`` は maya.cmds で一意に解決できる最短名、
``node.fullName()`` は完全な DAG パスを返します。どちらも呼び出すたびに求め直すため、
名前変更・親子付け替えの後も同じ Node を ``cmds.select(node)`` のように
maya.cmds へそのまま渡せます。削除済みのノードは空文字列です。

``hlib.node(value)`` (``Node(value)`` と同じ)は、名前・MObject・MDagPath のほか、
既存の Node、Plug・MPlug(所有ノード)、Vertex・Vertices などのコンポーネント
(所有シェイプ)も受け付け、実際のノード型に対応するラッパーを返します。
``"dup.tx"`` のように同じ短い名前のノードがあって複数の対象に一致する名前は、
最初の一致を返さず ``RuntimeError`` になります(``"bulk*"`` のように複数のノードに一致する
パターンも同じです。パターンは ``hlib.ls`` を使ってください)。``deleteAttr`` でアトリビュートが
削除された Plug・MPlug は、所有ノードが残っていても ``ValueError`` です
(``RuntimeError`` としても捕捉できます)。インスタンス化されたノードは
指定したインスタンスのパスを保持し、そのインスタンスだけが削除された場合は
パスを使う操作はRuntimeErrorになります。別インスタンスへは切り替えません。

.. code-block:: python

   joint = hlib.createNode("joint", name="nameExampleJoint")
   print(hlib.node(joint.plug("tx")))        # nameExampleJoint（Joint）
   print(hlib.node(joint.name() + ".tx"))    # アトリビュート名の文字列も所有ノードになる
   copy = hlib.node(joint)                   # 同じノードを指す新しいラッパー

詳しくは :doc:`cmds_interop` を参照してください。

ノード型の分類とDAG階層クエリ
------------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="classifyExample")
   print(node.typeId())                 # int（セッション内でのみ有効な内部ID）
   print(node.classification())        # ["drawdb/geometry/transform"]

   root = hlib.createNode("transform", name="root")
   branch = hlib.createNode("transform", name="branch")
   leaf = hlib.createNode("transform", name="leaf")
   branch.setParent(root)
   leaf.setParent(branch)

   print(root.children())   # [Transform('branch')]（Shape子は含まない）
   print(root.leaves())             # [Transform('leaf')]（子を持たない末端）
   print(branch.siblings())         # 親が同じ他の Transform（自身は含まない）

``typeId`` はプラグインの版数や環境によって値が変わりうるため永続化には
向きません。同一セッション内での高速な型比較にのみ使ってください。
``siblings()`` は親が無い（ワールド直下の）場合、他のワールド直下 Transform
（``persp`` / ``top`` などの既定カメラを含む）を対象にします。
``node.pluginName()`` はプラグイン由来のノード型でプラグイン名を返し、
Maya 組み込みのノード型では空文字列になります。

直接の親子関係とアトリビュート削除
--------------------------------------

.. code-block:: python

   grandparent = hlib.createNode("transform", name="grandparent2")
   parent = hlib.createNode("transform", name="parent2")
   child = hlib.createNode("transform", name="child2")
   parent.setParent(grandparent)
   child.setParent(parent)

   print(grandparent.parentOf(parent))   # True（直接の親子のみ）
   print(grandparent.parentOf(child))    # False（孫は対象外）
   print(grandparent.ancestorOf(child))  # True（子孫はすべて対象）
   print(parent.childOf(grandparent))    # True
   print(child.attrCount())            # int（全アトリビュート数）

   import maya.cmds as cmds
   cmds.addAttr(child.name(), longName="temp", attributeType="double")
   child.plug("temp").delete()          # 動的アトリビュートを削除

   cmds.addAttr(child.name(), longName="lockedTemp", attributeType="double")
   locked_plug = child.plug("lockedTemp")
   locked_plug.setFlags(locked=True)
   # locked_plug.delete()             # ロック中は RuntimeError
   locked_plug.delete(force=True)     # 一時的に解除してから削除

``parentOf``/``childOf`` は直接の親子関係のみを判定します。
祖先・子孫すべてを対象にする場合は ``ancestorOf`` を使ってください。
``delete`` は addAttr で追加した動的アトリビュートにのみ使用でき、
``translateX`` のような静的アトリビュートを削除しようとすると Maya が拒否します。
ロックされているアトリビュートは既定では削除できず ``RuntimeError`` になりますが、
``force=True`` を指定すると一時的にロックを解除してから削除します。
接続があるアトリビュートは force に関わらず Maya が自動的に切断してから削除します。
削除したアトリビュートの Plug は無効になり(``plug.valid()`` が ``False``、``str(plug)`` は空文字列)、
``get()``/``set()`` は ``RuntimeError`` です。同じ名前で追加し直したアトリビュートは ``node.plug()`` で
取得し直してください。

表示・SRT解放・軸判定・オフセットグループ
------------------------------------------

.. code-block:: python

   transform = hlib.createNode("transform", name="rigControl")

   transform.setVisibility(False)
   print(transform.plug("visibility").get())   # False
   transform.setVisibility(True)

   transform.setTranslate((1.0, 2.0, 3.0))
   transform.makeIdentity(apply=True, translate=True)
   print(transform.translate())             # Translate(0.0, 0.0, 0.0)

   driver = hlib.createNode("transform", name="rigDriver")
   driver.plug("translateX").connectTo(transform.plug("translateX"))
   transform.plug("translate").setFlags(locked=True)
   transform.unlockAndDisconnectTransformChannels()
   print(transform.plug("translate").locked())      # False
   print(transform.plug("translateX").sourceWithConversion())       # None（接続も解除される）

   from hlib.maths import Vector
   print(transform.closestAxisToVector(Vector(0, -1, 0)))   # "-y"

   zero, offset = transform.createOffsetGroups("rigControl_zero", "rigControl_offset")
   print(transform.parent().name())   # rigControl_offset
   print(offset.parent().name())      # rigControl_zero

``show``/``hide`` は ``visibility`` の単純なオン・オフです。``makeIdentity`` は
``cmds.makeIdentity`` のラッパーで、キーワード引数をそのまま渡します。
``unlockAndDisconnectTransformChannels`` は translate/rotate/scale/shear とその X/Y/Z 子をまとめて
アンロック・接続解除します。``closestAxisToVector`` は自身のワールド行列
（回転・スケールのみ、平行移動は無視）で各ローカル軸を変換し、指定した
ワールド方向ベクトルに最も近いものを ``"x"``/``"-y"`` のような文字列で返します
（``include_negative=False`` で負方向を除外可能）。``createOffsetGroups`` は
自身の現在のワールド行列に一致するグループを外側から内側の順で作成し、
自身を最も内側のグループへ付け替えます（ワールド位置は変化しません）。
引数を省略すると ``"<自身の名前>_offset"`` という1個のグループになります。

コンストレイントを削除する
--------------------------

``Transform.deleteConstraints()`` は自身を拘束しているコンストレイントと、
その入力経路にあるpairBlendを削除します。Jointでも使用できます。

.. code-block:: python

   import hlib

   driven = hlib.node("rigControl")
   deleted_names = driven.deleteConstraints()
   print(deleted_names)  # 削除前のノード名。該当がなければ []

入力接続をpairBlend・unitConversionに限って上流へ辿ります。
拘束元ノード、アニメーションカーブ、コンストレイントに繋がらないpairBlendは残します。
unitConversion自体は削除対象に含めません。
削除ノードの出力が他のノードにも使われている場合や、削除対象が参照・ロックされている場合は
変更前にエラーにします。全体は一回のUndoで戻せます。

現在姿勢の維持やベイク、pairBlendに接続されていたアニメーションの再接続は行いません。
削除後に姿勢が変わる場合があります。

複数ノードへの操作は :doc:`bulk_collections`、行列の計算は :doc:`matrices` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

ノードの削除
------------

``node.delete()`` はそのノードクラスの削除処理を実行します。
基底NodeはMaya標準の規則でDAGの子階層も削除します。
``hlib.delete(nodes)`` は各入力を具象ノードへ解決し、入力順に ``node.delete()`` を
呼び出します。先行処理で削除済みとなった対象や重複はスキップします。
全体を1回のUndoで戻せます。

``Joint.delete()`` はウェイト移送・子階層保持を伴う専用操作です。
``hlib.delete(joint_name)`` でもこの専用操作が呼ばれます。
独自ノードクラスも ``delete()`` の上書きで削除挙動を変更できます。

複数のノードを扱う
------------------------------

``Nodes → DagNodes → Transforms → Joints`` の順に継承します。
単数形も ``Node → DagNode → Transform`` に沿い、ConstraintはTransformを継承します。
ConstraintもTransformsへ格納でき、DAG階層・表示操作を共有します。

Jointの親スケール補正は ``segmentScaleCompensate()`` で照会し、
``setSegmentScaleCompensate(True)`` / ``setSegmentScaleCompensate(False)``
で切り替えます。Jointsでも同じメソッドで一括操作でき、照会は保持順のboolリストを返します。
通常の一括変更は1回のUndoで戻せます。``fast=True`` はUndo対象外です。
inverseScaleの接続やバインド情報は変更しないため、切り替えによって見た目が変わる場合があります。
``SkinClusters`` は ``Nodes`` を継承します。各クラスは単数形と同じファイルにあります。

.. code-block:: python

   from hlib.nodes import Nodes, Transforms, Joints

   targets = Transforms(hlib.ls(type="transform"))
   targets.setTranslate((1, 2, 3))     # 全対象に同じ値
   values = targets.translate()   # 保持順の値リスト
   targets.callEach("setTranslate", [((i, 0, 0),) for i in range(len(targets))])

   joints = Joints(hlib.ls(type="joint"))
   print(isinstance(joints, Transforms))  # True
   print(isinstance(joints, Nodes))       # True
   subset = joints[:2]                   # Joints
   references = joints.copy()            # 同じシーン対象を参照する別の容器

コンストラクタは単一の名前や参照、またはそれらの列を受け付けます。
名前・API参照の解決は :doc:`cmds_interop` の共通規則に従います。
``Transforms`` はJointなど派生ラッパーも保持します。
``Joints`` に通常のTransformを渡す等、型が合わない場合は ``TypeError`` です。
対象を黙って除外しません。構築後に削除された参照も保持するため、
``valid()`` で要素ごとの有効性を確認できます。

同じノード・同じDAGパスの重複を除き、最初の入力順を維持します。
同じノードでも異なるインスタンスパスは保持するため、パス別のワールド行列を取得できます。
改名・親変更への追従は単体Nodeの規則に従います。
``copy()`` やスライスはノードを複製せず、同じ参照を共有します。

通常の一括メソッドは単体の戻り値のリストを返し、引数の事前確認後に順に実行します。
通常モードの編集は一回のUndoにまとめます。実行途中で失敗した場合は停止し、
完了済みの変更は自動では戻しません。引数の確認は全対象の書込み可能性の保証とは異なります。
色設定は全対象のアトリビュートを事前検証します。詳細は :doc:`node_colors` を参照してください。
``Joints.delete()``・フリーズ・``SkinClusters.removeInfluences()`` 等の専用処理は維持しています。

``hlib.ls()`` の戻り値は従来どおりです。joint/skinClusterの型指定は専用コレクション、
それ以外はリストです。必要に応じて ``Nodes(...)`` / ``Transforms(...)`` で包んでください。
アトリビュートを含む検索結果はそのままNodesへ渡すと所有ノードへ解決されます。
Plug自体の一覧として保持したい場合は検索結果のリストを使用してください。


Transformのリセットとピボット
--------------------------------------

.. code-block:: python

   node.reset()                       # 移動0・回転0・スケール1・シアー0
   node.reset(["tx", "rotate", "sz"])  # 指定したアトリビュートだけ
   node.reset("customValue")           # 独自の数値アトリビュートの既定値
   node.resetPivot()                  # 姿勢を維持して両ピボットをワールド原点へ
   node.resetPivot(ws=False)          # オブジェクト空間の原点へ
   node.resetPivot(kind="rotate")     # 回転ピボットのみ

``reset()`` はアトリビュートの定義上の既定値へ戻します。フリーズではないため姿勢は変わります。
ロック解除・接続切断は行いません。Jointでも使えますが、jointOrientは既定の対象に含みません。
``resetPivot()`` はピボット補償値を調整して行列を保ちます。Jointは独立したピボットを
サポートしないためエラーになります。Transformsからの一括呼出にも対応します。
通常はUndoで戻せます。``reset(fast=True)`` はUndoなしです。


Jointのスケール接続と表示半径
----------------------------------------

.. code-block:: python

   joint.connectInverseScale()                 # 親のscale → 自身のinverseScale
   joint.connectInverseScale(parent, force=True) # 指定Transformから接続を置換
   joint.disconnectInverseScale()              # inverseScaleへの入力だけ切断
   joints.connectInverseScale()                # 各Joint自身の親へ一括接続
   joints.disconnectInverseScale()
   joint.setRadius(2.0)                         # 個別の表示半径
   print(joint.radius())
   joints.setRadius(0.5)                        # 一括変更

親がないJointでは引数なしの接続は何もしません。同じ接続が既にある場合も変更しません。
既存入力の置換には ``force=True`` が必要です。これはPlug.connectと同じく、接続先が
ロックされている場合の一時解除・再ロックも含みます。
切断は複合アトリビュートと各軸の入力に対応し、出力接続は維持します。
segmentScaleCompensateの切り替えや切断後の値のリセット、姿勢補償は行いません。
接続の変更によって姿勢が変わる場合があります。

radiusはジョイント個別の表示半径です。骨の長さやscale、Maya全体のjointDisplayScaleは
変更しません。通常はUndo対応で、``setRadius(..., fast=True)`` だけはUndoなしです。


Maya標準のフリーズ
------------------------------

.. code-block:: python

   node.freeze()                         # makeIdentity(apply=True)と同じ
   node.freeze(t=False, r=True, s=True)   # 回転とスケールだけ
   transforms.freeze()                   # 一括操作・一回のUndo

``freeze()`` はMaya標準の ``makeIdentity`` をapply=Trueで呼びます。
成分や法線オプションはMayaの長名・短名で指定できます。apply=Falseは拒否します。
子階層への作用、Jointの移動保持、ロック・接続・スキニング済み形状の制約もMayaに従います。
姿勢移送を行うJoint.freezeRotateとは異なります。

スキンバインドとジョイントのミラー複製
------------------------------------------------------

.. code-block:: python

   import hlib

   skin = hlib.bindSkin(mesh, joints, toSelectedBones=True,
                                 maximumInfluences=4, normalizeWeights=1)
   skins = hlib.bindSkin([mesh_a, mesh_b], joints, tsb=True, mi=4)
   mirrored = hlib.mirrorJoint(root_joint, mirrorYZ=True, mirrorBehavior=True,
                              searchReplace=("left_", "right_"))

``bindSkin`` は形状ごとに標準skinClusterコマンドを実行します。
1形状ならSkinCluster、複数なら入力順のSkinClustersを返します。
作成オプションは実行中MayaのskinClusterの長名・短名を使用でき、省略値もMayaに従います。
バインド対象とインフルエンスは明示指定し、各入力列で名前とNodeは混在させません。
bindMethod=3のジオデシックボクセルバインドは、標準コマンドと同様に別途geomBindが必要です。

``mirrorJoint`` は指定Joint以下をミラー複製し、新規Jointだけを返します。
1個ならJoint、階層など複数ならJointsです。フラグと既定値はMayaに従います。
両コマンドともUndo対応です。複数形状のバインドが途中で失敗した場合は例外になり、
完了済みの変更は自動では戻しません。


アウトライナーの表示設定
------------------------------------

.. code-block:: python

   node.setOutlinerVisibility(False)  # 非表示
   node.setOutlinerVisibility(True)   # 表示
   visible = node.outlinerVisibility()
   joints.setOutlinerVisibility(False)  # DagNodes/Transforms/Jointsでも一括操作可能

通常のビューポート表示は別のメソッドで操作します。

.. code-block:: python

   node.setVisibility(False)
   node.setVisibility(True)
   visible = node.visibility()

表示・Outliner色・Drawing OverridesはDagNode・DagNodesで扱います。
Transform・Joint・Shape・Constraintでも使用でき、汎用Node・Nodesでは公開しません。取得値は自身の設定であり、
親の非表示や表示レイヤーを含む最終表示状態ではありません。

hiddenInOutlinerを操作します。ビューポートのvisibilityは変更しません。
取得値はノードの表示設定であり、フィルターや親の折り畳み、Outlinerの非表示ノード表示設定を
含む画面上の可視性ではありません。通常はUndo可能で、fast=TrueはUndo対象外です。


エクストラアトリビュート
------------------------------------

.. code-block:: python

   weight = node.addAttr("weight", attributeType="double", defaultValue=1,
                               minValue=0, maxValue=1, keyable=True)
   mode = node.addAttr("mode", at="enum", enumName="off:on", keyable=True)
   text = node.addAttr("memo", dataType="string")
   text.set("コントローラ")
   vector = node.addAttr("offset", attributeType="double3")
   vector.set((1, 2, 3))
   extras = node.extraAttrs()  # トップレベルのPlug一覧
   all_extras = node.extraAttrs(include_children=True)
   same_plug = node.plug("weight")       # 個別に取得

既存のaddAttrで追加できます。Mayaの長名・短名フラグを受け付け、重複指定は拒否します。
数値のdefaultValueはMayaの定義上の既定値です。文字列にもdefaultValueで初期値を指定できます。
既定で追加したPlugを返します。``getPlug=False`` を明示した場合のみNoneを返します。
attributeTypeがdouble2/double3/float2/float3の場合、X/Y/Zの子も自動で追加します。
compoundも ``childNames`` と ``subType`` で共通型の子を自動作成できます。

列挙結果は非表示・非keyableのユーザー定義アトリビュートも含みます。
Mayaの標準アトリビュートは含みません。multiはArrayPlug、複合型はCompoundPlugまたは専用型です。
列挙はOpenMayaの定義情報から追加順に取得し、空配列や疎な配列の要素を作成しません。
``extraAttrNames()`` と既定の ``extraAttrs()`` は複合配列もトップレベルのみ返します。
``include_children=True`` で複合配列の子が含まれる場合は、番号なしのPlugを作れないため
RuntimeErrorになります。子の操作には ``node.plug("items")[7]["amount"]`` のように番号を指定します。
追加・通常の値変更はUndo対応です。

.. list-table:: 主な型と返却Plug
   :header-rows: 1

   * - Mayaの型
     - Plugクラス
   * - double / float
     - DoublePlug / FloatPlug
   * - long / short
     - LongPlug / ShortPlug
   * - bool / enum / string
     - BoolPlug / EnumPlug / StringPlug
   * - doubleAngle / doubleLinear / time
     - DoubleAnglePlug / DoubleLinearPlug / TimePlug
   * - double3 / matrix
     - Double3Plug / MatrixPlug
   * - message
     - MessagePlug（値ではなく接続を扱う）

EnumPlugはget/setで整数、enumName/enumValueでラベルと値を扱えます。
専用型のないMayaデータ型は従来どおりPlugの対応範囲で使用できます。
型の自動選択は標準アトリビュートにも適用されます。例えばfloatの配列要素もFloatPlugになります。

マテリアル・シェーダーとテクスチャ
------------------------------------------------------------

ノードクラスのファイルはすべてnodes直下に配置しています。
Lambert、Reflect、Blinn、Phong、PhongE、StandardSurface、SurfaceShader、
ShadingEngine、File、Place2dTexture、Place3dTextureを型付きで取得できます。
継承はMayaのノード型に合わせ、例えばBlinnとPhongはReflect、ReflectはLambertを継承します。
StandardSurfaceはLambertの派生ではなく、SurfaceShaderはNodeから直接派生します。
LambertとStandardSurfaceの中間型PaintableShadingDependNodeは、起動中のMayaの継承情報に
存在する場合に使用します。Maya 2022ではShadingDependNodeを直接継承します。

.. code-block:: python

   import hlib

   material = hlib.createShader("lambert", name="bodyMaterial")
   material.plug("color").set((0.2, 0.4, 0.8))
   group = hlib.createShadingGroup(material, name="bodySG")
   body = hlib.node("body")  # 既存のTransform
   group.assign(body)
   mesh = body.shape()
   group.assign(mesh.faces([0, 1, 2]))  # フェース単位にも割り当て可能
   materials = mesh.materials()
   face_material = mesh.face(0).material()
   targets = group.members()  # NodeまたはFaceのリスト

createShader/createShadingGroupのnameはnでも指定できます。
シェーダーの作成とシェーディンググループの作成は分けて扱います。
assignは既存の割り当てを置き換え、選択状態には依存しません。
MeshのshadingEngines/faceShadingEnginesはDAGインスタンスごとの割り当てを取得します。
faceShadingEnginesはフェース順のリストで、未割り当てはNoneです。
TransformのshadingEnginesは直下の非中間シェイプを対象とします。
シェーダー側のshadingEnginesとassignedObjectsから割り当て先をたどることもできます。

.. code-block:: python

   texture = hlib.createNode("file", name="bodyTexture")
   texture.setFilePath("C:/textures/body.<UDIM>.exr")
   placement = hlib.createNode("place2dTexture")
   placement.connectTexture(texture)
   texture.plug("outColor").connectTo(material.plug("color"))
   current_placement = texture.placement()
   current_space = texture.colorSpace()

connectTextureはUV・フィルター・繰り返しなどの標準接続をまとめて行います。
既存の異なる接続を置き換える場合はforce=Trueを明示します。
FileのsetColorSpaceは現在の色管理設定で有効な色空間を指定します。
ファイルパスはそのまま保持し、UDIMの展開やファイルコピーは行いません。

ShadingEngineのshader/setShaderはkindにsurface、volume、displacementを指定できます。
任意の出力はPlugで渡すかoutputで出力名を指定します。
マテリアル固有の値はplugで扱い、表示色用のColorクラスへは変換しません。
作成・割り当て・接続・値変更は通常のUndoに対応します。

一括APIの戻り値
------------------------------------

通常の更新（setTranslate・freeze・setVisibilityなど）はコレクション自身を返します。
照会は保持順の結果リスト、addAttr等の生成結果が必要な操作も結果リストです。
callEachも同じ戻り値規則に従います。空のコレクションでもこの規則は変わりません。
色の照会はlist[Color]、Joints.skinClustersはSkinClustersという専用の集約結果を返します。
明示実装のdeleteはNoneを返し、削除済み参照の連鎖操作には使用しません。

開発者は複数形クラスへ通常のdefとして公開メソッドを定義し、共通処理へ委譲します。
単数クラスへのメソッド追加だけでは一括APIは増えません。継承するメソッドと、
要素別入力が必要な操作の制限は派生コレクションでも維持します。
失敗時は後続処理を止めますが、自動ロールバックはしません。
