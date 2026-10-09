デフォーマとスキニング
============================================================

cluster・blendShape・skinClusterと、スキン変形を保持した編集を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

ウェイトを変えずにinfluenceを追加する
------------------------------------------

.. code-block:: python

   skin = hlib.node("skinCluster1")
   skin.addInfluences("extra_joint")
   skin.addInfluences(["extra_joint2", hlib.node("extra_joint3")])

Jointをウェイト0で登録します。既存ウェイトの正規化・再配分は行いません。
既存influenceと重複指定は無視し、空リストは何もしません。
Joint以外の対象は追加前に例外にします。操作は1回のUndo/Redoに対応し、
``SkinClusters`` からも同名メソッドを一括実行できます。

influenceを取り除き、親へウェイトを加算する
------------------------------------------------

.. code-block:: python

   skin = hlib.node("skinCluster1")
   joint = hlib.node("extra_joint")
   skin.removeInfluence(joint)
   # 不正ウェイトの修復が必要なら、上の呼出しに代えて指定する
   # skin.removeInfluence(joint, f=True)
   # またはjoint側から、接続する全skinClusterを対象にする
   # joint.removeInfluence()
   # 対象を一つに限定する場合
   # joint.removeInfluence(skin)

同じskinClusterに登録された最も近い祖先influenceへ元ウェイトを加算し、
指定jointのinfluence登録だけを外します。jointノードや子階層は変更しません。
親が直接登録されていなければさらに祖先を探し、移送先がなければMaya標準の
removeInfluenceによる再配分に任せます。最後の一つのinfluenceはエラーにします。
``transfer_to_parent=False`` をSkinCluster側へ渡すと標準除去のみ行います。
``Joint.removeInfluence()`` は未スキニングなら何もしません。

``force=True`` または短縮名 ``f=True`` は、不正ウェイトを除去してから
既存の祖先移送・登録解除を行います。``Joint.removeInfluence`` と
``SkinClusters.removeInfluences`` でも同じ指定を使えます。
ロックを解除したり、接続やスキニングレイヤーを迂回したりする指定ではありません。
削除可否の事前検証は読取だけで行い、修復と登録解除を一回のUndoにまとめます。
``force`` と ``f`` の同時指定やbool以外の値は、変更前に ``TypeError`` です。
単数の ``SkinCluster.removeInfluence`` は従来どおりNone、
``Joint.removeInfluence`` と ``SkinClusters.removeInfluences`` は自身を返します。
祖先へウェイトを加算する処理は先頭meshが対象です。
NURBSなど未対応のgeometryで祖先移送が必要な場合、``force=True`` は修復前に
``ValueError`` で停止し、ウェイトを変更しません。

不正ウェイトの要素だけを除去する
------------------------------------

.. code-block:: python

   skin = hlib.node("skinCluster1")
   skin.removeInvalidWeights()  # SkinCluster自身。通常のUndoに対応
   # Undo不要の直接更新を選ぶ場合
   # skin.removeInvalidWeights(fast=True)
   skins = hlib.nodes.SkinClusters([skin])
   skins.removeInvalidWeights()  # SkinClusters自身

``removeInvalidWeights(*, fast=False)`` は、生の ``weightList`` にある既存要素から
負値・NaN・正負の無限大・未登録influence論理番号の要素を削除します。
存在しない要素は作成しません。登録済みinfluenceの有効な0や1を超える値、
合計が1でない頂点は不正扱いせず保持します。
正規化、合計0の補填、influence登録の解除は行いません。
削除した登録済みinfluenceの要素は既定値0になり、不正要素がなければ何もしません。
戻り値は単数・複数とも自身です。
単独の不正要素除去はNURBSの生の ``weightList`` にも使えます。

スキニングレイヤー、influenceの ``lockInfluenceWeights``、``weightList`` と
既存要素のロック・入力接続、削除対象要素の出力接続を変更前に検証し、
編集できなければ例外で停止します。ロック解除や接続の切断は行いません。
既定の ``fast=False`` は ``cmds.removeMultiInstance`` で一回のUndo/Redoに対応し、
``fast=True`` は ``MDGModifier`` による直接更新でUndoに記録しません。
``fast`` はboolのキーワード専用引数です。実行途中の失敗で完了済み変更を
自動ロールバックする機能はありません。

未使用influenceの登録だけを解除する
----------------------------------------

.. code-block:: python

   unused = skin.unusedInfluences()       # 照会だけ。list[Node]
   removed = skin.removeUnusedInfluences()   # 登録解除したlist[Node]
   # 不正ウェイトを修復してから判定する場合は上の呼出しに代えて指定
   # removed = skin.removeUnusedInfluences(f=True)

未使用の判定はMayaの ``weightedInfluence`` により全geometryを対象にします。
微小な非ゼロ値も使用中として扱い、閾値で切り捨てません。
返却リストはinfluence順で、jointノード自体は削除しません。
``SkinClusters.removeUnusedInfluences`` は保持順の ``list[list[Node]]`` を返します。

``removeUnusedInfluences(*, force=False)`` は、``force=True`` または ``f=True`` で
不正ウェイトを除去してから使用状況を調べます。修復後に全influenceが未使用となる場合は、
修復前に ``ValueError`` で停止し、登録が空になる解除を防ぎます。
通常の呼出しも全influenceの解除は拒否します。修復と登録解除は一回のUndoで戻せます。
このforceも正規化・補填・ロック解除・レイヤーの迂回を行いません。
force/fの重複やbool以外は変更前に ``TypeError``、途中失敗は自動ロールバックしません。

ウェイトの正規化と最大influence数
-----------------------------------

.. code-block:: python

   skin.normalizeWeights()            # 各頂点の合計を1にする
   skin.normalizeWeights(decimals=3)  # 小数3桁へ丸め、端数を配分して合計1にする
   skin.setMaxInfluences(4)          # 設定のみ。既存ウェイトは変更しない
   skin.setMaxInfluences(4, prune=True)  # 大きい4個を残し、残りを0にして正規化
   print(skin.maxInfluences())

正規化とpruneは先頭meshの全頂点が対象です。小数桁数は0〜15を指定できます。
例えば同じ重みが3つなら、小数2桁では0.34、0.33、0.33とし、同率時は登録順を
優先します。浮動小数点の保存値には機械精度の誤差があり得ます。
合計0・負値・非有限値、ロック・入力接続・スキニングレイヤーは編集前に拒否します。
``normalizeWeights`` は ``normalizeWeights`` 設定を変えません。
``setMaxInfluences`` は既定で ``maintainMaxInfluences`` も有効にします。
``maintain=False`` で無効にできます。設定だけでは既存の非ゼロ数は制限されません。
これらの変更は一回のUndoで戻せます。実行途中の例外は通知し、自動ロールバックはしません。

選択した頂点のウェイト配分を調整する
-----------------------------------------

``redistributeWeights`` は番号列のほか、先頭geometryのmeshに属する
Vertex・Vertices・Vertexと整数の混在列を受け取ります。

.. code-block:: python

   skin = hlib.node("skinCluster1")
   skin.redistributeWeights(hlib.ls(sl=True, type="vertex"), method="cubic")
   skin.redistributeWeights(hlib.node(skin.mesh).vertices([0, 1]), method="linear")

``method`` はeasingの曲線名です。配分を合計1として読み、曲線を適用してから再正規化します。
別meshのVertexは全対象を検証してから拒否します。選択を変更せず、空入力は何もしません。
戻り値は従来どおりNone。通常のUndoで戻せますが、実行途中のゼロ合計やMayaエラーで
先に完了した頂点の更新は自動では戻しません。

cluster と locator
--------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   mesh = hlib.node("pCube1")
   cluster_name, handle_name = cmds.cluster(mesh.fullName() + ".vtx[0:2]")
   cluster = Node(cluster_name)

   print(cluster.weightedNode())   # cluster1Handle（ハンドル transform）
   print(cluster.geometry())        # [Mesh(...)]（変形対象の shape）

   loc_transform = cmds.spaceLocator(name="myLocator")[0]
   loc_shape_name = cmds.listRelatives(loc_transform, shapes=True)[0]
   locator = Node(loc_shape_name)

   print(locator.position())         # Translate(0.0, 0.0, 0.0)
   locator.setPosition((1.0, 2.0, 3.0))

``cluster`` ノードは自動的に ``Cluster`` ラッパーへ解決されます。``weightedNode``
はクラスタのハンドル transform（デフォーマ本体とは別ノード）、``geometry`` は
変形対象の shape を返します。``locator`` シェイプは ``Locator`` ラッパーへ解決され、
``position``/``setPosition`` は ``localPosition`` アトリビュートを ``Translate`` として
扱います。

blendShape の作成
------------------------

``createBlendShape(base, targets=None, **kwargs)`` はベースへ接続したBlendShapeを返します。
ベースは明示し、選択には依存しません。通常のUndoに対応します。

.. code-block:: python

   bs = hlib.createBlendShape("faceMesh", name="faceBlendShape")
   bs.addTarget("smileMesh")

   # 初期ターゲットは単体またはリスト。Nodeオブジェクトも指定できる。
   bs = hlib.createBlendShape("otherFace", targets=["smileMesh", "blinkMesh"])
   bs.targetPlug(0).set(1.0)

``targets=None`` または空列はターゲットなしです。``name/n``・``origin/o``・
``frontOfChain/foc`` 等はMaya標準フラグとして渡せます。照会・編集は各メソッドを使います。

blendShape のターゲット操作
------------------------------

.. code-block:: python

   from hlib.nodes import Node

   base = hlib.node("pCube1")
   target = hlib.node("pCube2")   # base と同じトポロジーの別メッシュ

   bs = Node(cmds.blendShape(target.fullName(), base.fullName(), name="myBlendShape")[0])
   print(bs.targetAliases())            # ['pCube2']（既定ではターゲット名がエイリアスになる）
   print(bs.weights())            # [0.0]
   bs.weightPlugs()[0].set(1.0)

   new_target = hlib.node("pCube3")
   weightPlug = bs.addTarget(new_target)   # 空いている weight インデックスへ追加
   weightPlug.set(0.5)
   print(bs.targetAliases())            # ['pCube2', 'pCube3']

``targetAliases()`` / ``weightPlugs()`` / ``weights()`` は ``aliases()`` の順序に従います。
weight配列の論理インデックスで並べ替えません。weight以外のアトリビュートに
エイリアスを付けた場合、その名前・Plug・値も含みます。
``addTarget`` は ``base`` を省略すると既存の base geometry の先頭を使い、
``weight_index`` を省略すると ``plug("weight").nextAvailableIndex()`` で空きインデックス
を自動的に選びます。追加したターゲットには既定でその名前がエイリアスとして
設定されるため、戻り値のプラグの ``fullName`` は ``weight[N]`` ではなく
ターゲット名を含む表記になります（``longName()`` では実際のアトリビュート名を取得できます）。

ターゲット番号・エイリアスを受け取る編集・照会には、同じBlendShapeのweight要素Plugも
渡せます。addTarget・duplicateTarget等の返却を次の操作へ使えます。

.. code-block:: python

   weight = bs.addTarget(new_target)
   weight.set(0.5)
   bs.resetTargetVertices(weight, hlib.ls(sl=True, type="vertex"))
   bs.reduceTargetDeltas(weight, 0.001)

別BlendShapeのPlug、weight以外、配列親、空weight要素、削除済み参照は拒否します。
エイリアス変更後も同じweight要素を参照できます。

ターゲット編集モード
--------------------------

``targetEdit`` はMaya標準のsculptTargetで編集モードを切り替えます。
開始時は番号またはエイリアスを指定し、終了時はターゲットを省略できます。
通常のUndoに対応し、戻り値は自身です。fastフラグはありません。

.. code-block:: python

   bs.targetEdit("smile", True)
   bs.targetEdit("smile", True, full_weight=0.5)  # 既存in-between
   bs.targetEdit("smile", False)
   bs.targetEdit(state=False)  # 対象を指定せず終了

``state`` はbool限定です。開始時のターゲットと項目は存在を検証します。
開始時は自身のweight要素Plugも指定できます。
終了時はtargetとfull_weightを使用しません。複数ベースではノード全体に適用します。

blendShape の編集・保存
-----------------------

既存の ``targetAliases/weightPlugs/weights`` の仕様は変えていません。
実際のターゲットだけを列挙する場合は ``targetIndices()``、番号またはweightの
エイリアスから操作する場合は ``targetPlug()`` を使います。空のweight要素や
weight以外の別名は新しい一覧には含みません。番号は疎でも保持されます。

.. code-block:: python

   import maya.cmds as cmds
   import hlib

   bs = hlib.node("faceBlendShape")
   indices = bs.targetIndices()
   bs.targetPlug("smile").set(0.5)
   bs.replaceTarget("smile", "smileNew")  # 番号・別名・現在値・weight接続を維持

   # 現在の形状をベイクし、in-betweenと頂点ウェイトを複製。新しいweight値は0。
   copied = bs.duplicateTarget("smile", weight_index=5, alias="smileRight")
   bs.flipTarget("smileRight", axis="X")  # 左右を交換

   # 片側を反対側へ写す。directionはMaya標準値で0=負方向、1=正方向。
   bs.mirrorTarget("smileRight", axis="X", direction=1)
   bs.removeTarget("smileRight")  # 全ベースのターゲットとそのin-betweenを削除

追加した形状編集APIはポリゴンメッシュ用です。置換するメッシュは頂点数だけでなく
面の頂点接続順も一致する必要があります。ミラーはMaya標準のオブジェクト空間の
対称対応を使用するため、対称なベースメッシュを前提とします。
接続中の入力があるターゲットへのミラーは拒否します。複製でベイクしてから操作してください。
``removeTarget`` はMaya標準のShape Editor削除処理を呼び、関連する表示情報も削除します。
入力メッシュは削除しませんが、weightの接続元がcombinationShapeの場合は
Maya標準の削除処理によりそのノードも削除されます。

in-between
~~~~~~~~~~

.. code-block:: python

   bs.addInBetween("smile", "smileHalf", weight=0.5)
   weights = bs.inBetweenWeights("smile")    # [0.5]
   bs.replaceTarget("smile", "smileHalfNew", full_weight=0.5)
   bs.removeInBetween("smile", weight=0.5)

``addInBetween(relative=True)`` はMayaの相対in-betweenとして追加します。
指定ウェイトは0と1以外、-5以上の0.001刻みです。既存ウェイトへの追加は拒否します。
``inBetweenWeights`` は1.0以外の項目を返します。
``base`` を受け取るメソッドは省略時に最小のベース論理番号を使います。
``removeInBetween`` はShape Editorと同様、全ベースの同じウェイト項目を削除します。
``removeTarget/duplicateTarget`` も全ベースが対象です。

頂点ウェイトとデルタ
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   weights = bs.targetWeights("smile")      # 頂点番号順の全値。既定値1。
   bs.setTargetWeights("smile", {0: 0.25, 1: 0.75})  # 部分更新
   bs.setTargetWeights("smile", weights)       # 全頂点更新

   deltas = bs.targetDeltas("smile")        # dict[int, hlib.Vector]
   bs.setTargetDeltas("smile", deltas, disconnect=True)
   bs.setTargetDeltas("smile", {0: (0.0, 2.0, 0.0)})

デルタは通常ターゲットではオブジェクト空間cmです。
``targetDeltas`` はMayaの ``inputPointsTarget`` を読み、接続中の形状も現在値を取得します。
``setTargetDeltas`` は同項目の絶対デルタ全体を置換し、省略頂点はゼロにします。
相対補助デルタはクリアし、他のin-betweenのデルタは更新しません。
接続中の形状を変更する場合は ``disconnect=True`` が必要です。
``full_weight`` で中間項目も指定できます。
不正な頂点番号・非有限数・頂点数不一致は書き込み前に拒否します。

デルタ単体の保存と対象頂点
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``dumpTargetDeltas(target, path, base=None, full_weight=1.0)`` と
``loadTargetDeltas(target, path, base=None, full_weight=1.0, disconnect=False, *, fast=False)`` で
辞書キーの変換をメソッド内にまとめて保存・復元できます。

.. code-block:: python

   bs.dumpTargetDeltas("smile", "C:/tmp/smile_delta.hlib.json")
   restored = hlib.node("restoredBlendShape")  # 同じ頂点順のベースと既存smileターゲット
   restored.loadTargetDeltas("smile", "C:/tmp/smile_delta.hlib.json", disconnect=True)
   restored.targetPlug("smile").set(1.0)

単体IOはhlib.json形式で、文字列の頂点番号キーとVector値を保存します。
dumpは絶対パスのPath、loadはBlendShape自身を返します。
全データを検証してからsetTargetDeltasへ委譲し、通常は一回のUndoにまとまります。
loadのfast=TrueはUndoなしです。接続中の入力を切断する場合はdisconnect=Trueを明示します。
既存のdumpTargets/loadTargetsの形式と、標準jsonでの次の保存方法は変更しません。

``targetDeltas`` の辞書だけをJSONへ書けば、名前やウェイトを含まない
「頂点番号とxyz変位」だけのファイルになります。JSONの辞書キーは文字列に
なるので、読み込み時に整数へ戻します。

.. code-block:: python

   import json
   import hlib

   bs = hlib.node("faceBlendShape")
   deltas = bs.targetDeltas("smile")
   with open("smile_delta.json", "w", encoding="utf-8") as stream:
       json.dump({str(i): list(delta) for i, delta in deltas.items()}, stream, indent=2)

   with open("smile_delta.json", encoding="utf-8") as stream:
       deltas = {int(i): xyz for i, xyz in json.load(stream).items()}

   # 復元先の既存ターゲットを置換。接続中のターゲット入力は明示的に切断。
   restored = hlib.node("restoredBlendShape")
   restored.setTargetDeltas("smile", deltas, disconnect=True)
   restored.targetPlug("smile").set(1.0)

まだ復元先のターゲットがない場合は、変形前のベースと同じ形状を一時ターゲットとして
登録してからデルタを書き込みます。

``addTargetDeltas(deltas, base=None, weight_index=None, alias=None)`` はこの一時メッシュの
準備と後始末をまとめ、新しい通常1.0のターゲットのweight Plugを返します。

.. code-block:: python

   restored = hlib.createBlendShape("newFace")
   weight = restored.addTargetDeltas({0: (0.0, 2.0, 0.0)}, alias="smile")
   weight.set(1.0)

   # hlib.json単体ファイルから未作成のターゲットへ復元する場合。
   weight = restored.addTargetDeltas({}, alias="blink")
   restored.loadTargetDeltas(weight, "C:/tmp/blink_delta.hlib.json")
   weight.set(1.0)

別名・未使用番号・全デルタを登録前に検証し、現在の表示形状ではなくBlendShapeへ入る
変形前geometryを中立基準として使います。weightの初期値は0です。一時メッシュは残さず、
登録全体は一回のUndo/Redoに対応し、例外時はUndoトランザクションで巻き戻します。
Undo有効時に使用します。通常local/world originのポリゴン用で、post-deformationと
user-defined originは未対応です。fastフラグは提供しません。

標準jsonファイルを扱うときは、上で読み込んだ整数キーのdeltasをaddTargetDeltasへ渡すか、
次のMaya標準コマンドの手順を使います。

.. code-block:: python

   import maya.cmds as cmds

   base = "newFace"  # 保存元と頂点順・トポロジー・変形前の座標が同じメッシュ
   neutral = cmds.duplicate(base, returnRootsOnly=True)[0]
   restored = hlib.node(cmds.blendShape(neutral, base, name="restoredBlendShape")[0])
   cmds.delete(neutral)
   restored.targetPlug(0).setAlias("smile")
   restored.setTargetDeltas(0, deltas)
   restored.targetPlug(0).set(1.0)

デルタ単体のJSONにはトポロジー情報や頂点マスクは入りません。
同じ形状を再現するには、対応する頂点順と変形前の座標、envelope・頂点ウェイトなどの
条件も揃える必要があります。通常のオブジェクト空間ターゲットでは変位の単位はcmです。
``setTargetDeltas`` は既存項目のデルタ全体を置換します。Undo不要なら ``fast=True`` を指定できます。
in-betweenを扱う場合は取得・設定の両方に同じ ``full_weight`` を指定してください。

.. code-block:: python

   vertices = bs.targetVertices("smile")  # ベースメッシュ上のVertices
   indices = vertices.indices              # 昇順のtuple[int, ...]
   cmds.select(vertices.fullNames(), replace=True)

   # 変位長が0.0001cmを超える頂点だけ。full_weightでin-betweenも選べる。
   vertices = bs.targetVertices("smile", tolerance=0.0001)
   half_vertices = bs.targetVertices("smile", full_weight=0.5)

対象頂点は ``targetDeltas`` の絶対デルタで判定し、明示的に格納されたゼロ変位は
除外します。現在のweightが0でも、頂点マスクが0でも、デルタがあれば対象です。
``tolerance`` は非負の有限数で、その値と等しい変位も除外します。
複数ベースでは ``base`` を指定でき、対象がない場合は空のVerticesを返します。

指定頂点だけデルタから除外するには ``resetTargetVertices`` を使用します。
頂点番号・番号のリスト・ベースメッシュの ``Vertex`` / ``Vertices`` を渡せます。
未接続時は残りの絶対デルタと相対補助デルタ、頂点ウェイト、別の項目を保持します。

.. code-block:: python

   bs.resetTargetVertices("smile", [10, 20, 30])  # 通常はUndo対応
   bs.resetTargetVertices("smile", 10, full_weight=0.5)  # in-between
   bs.resetTargetVertices("smile", vertices, fast=True)  # OpenMaya、Undoなし

   # ベースメッシュで選択した頂点を直接渡す。
   bs.resetTargetVertices("smile", hlib.ls(sl=True, type="vertex"))

ターゲットメッシュが接続中なら、そのメッシュの指定頂点を中立位置へ戻し、接続を維持します。
現在の絶対デルタを差し引くので、変形後のベース表示位置や現在のweightには依存しません。
同じターゲット形状を共有する他の項目にも編集が反映されます。
明示的な ``disconnect=True`` は、従来どおり切断して保存デルタだけを編集します。
接続中の編集は通常ポリゴンのlocal/world originに対応します。post-deformation・
ユーザー定義origin・メッシュ以外の接続元は未対応で、変更前に例外とします。
``fast=True`` で入力履歴付きターゲット形状を編集することも未対応です。
接続中のデルタ配列はMayaが再計算するため、配列の疎な格納状態はMayaに従います。
座標変換による微小誤差が残る場合は、頂点照会の ``tolerance`` を指定してください。
空入力やデルタのない頂点だけの指定は何も変更せず、入力接続も保持します。

デルタの長さでまとめて除外するには ``reduceTargetDeltas`` を使用します。
格納済みの絶対デルタのXYZベクトル長が ``tolerance`` 以下（境界値を含む）の頂点を除外します。
通常ターゲットの単位はcmで、既定0はゼロデルタだけを除外します。
現在のweight・envelope・頂点マスクは判定に使用しません。
未接続時は該当頂点の相対補助デルタも除外し、残りのデータを保持します。

.. code-block:: python

   bs.reduceTargetDeltas("smile")  # ゼロデルタのみ、Undo対応
   bs.reduceTargetDeltas("smile", 0.001)  # 変位長0.001cm以下
   bs.reduceTargetDeltas("smile", 0.001, full_weight=0.5, fast=True)

接続中は ``resetTargetVertices`` と同じくターゲット形状を自動編集して接続を維持します。
除外対象がない場合は接続もデータも変更しません。

一式のJSON保存・復元
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   bs.dumpTargets("C:/tmp/faceTargets.json")
   # 同じトポロジーのベースに空のblendShapeを作成して復元。
   restored = hlib.node(cmds.blendShape("newFace", name="restoredFace")[0])
   restored.loadTargets("C:/tmp/faceTargets.json")

保存対象は全ベースのトポロジー、各ターゲットの絶対・相対デルタ、in-betweenの名前・
種類・補間曲線、頂点ウェイト、ベース頂点マスク、エイリアス、weight現在値、envelope、origin、
負ウェイトの許可設定です。接続中のデータは現在値にベイクします。
ファイルは検証後に一時ファイルから置き換えます。

復元先にはターゲットもweight要素もないことが必要です。ベースは論理番号で対応させ、
頂点数と面の頂点接続順を全件検証してから変更します。名前が違うベースへも復元できます。
MayaのUndoが有効であることが必要で、読み込み失敗時はUndoトランザクションで巻き戻します。
全体を1回でUndo/Redoできます。Maya標準の挙動により、Undo後に内容のない内部配列が
残ることがありますが、ターゲット一覧には含みません。

JSON保存と複製は通常のポリゴンターゲット用で、post-deformationの接線／変換空間や
正規化グループは拒否します。JSONはuser-defined originも拒否します。
外部ドライバ・アニメーション接続・Shape Editorのフォルダ配置・デフォーマ順序は保存しません。
シーン全体のリグ保存形式ではありません。

OpenMaya照会とfast更新
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ターゲット・頂点ウェイト・デルタ・保存用データの照会はOpenMaya API 2.0で行います。
未初期化データは共通の型付きデータ読取処理で判定し、評価エラーを空値として扱いません。

``setTargetWeights``、``setTargetDeltas``、``resetTargetVertices``、``replaceTarget``、``duplicateTarget``、
``reduceTargetDeltas``、``loadTargets`` はキーワード専用の ``fast=False`` を受け付けます。
既定値ではcmds/MELによるUndo対応の更新、``fast=True`` ではMPlug・MFnデータ・
MDGModifierによる直接更新を行います。高速経路ではcmds/MELを呼び出さず、
Undoの有効／無効設定や既存のUndo履歴も変更しません。

.. code-block:: python

   bs.setTargetWeights("smile", {0: 0.5})  # Undo対応
   bs.setTargetWeights("smile", {0: 0.5}, fast=True)  # Undoなし
   bs.setTargetDeltas("smile", deltas, disconnect=True, fast=True)
   bs.replaceTarget("smile", "smileNew", fast=True)
   bs.duplicateTarget("smile", alias="smileCopy", fast=True)
   restored.loadTargets("C:/tmp/faceTargets.json", fast=True)

入力の検証、頂点番号、単位、戻り値は両経路で共通です。``fast`` にbool以外を
渡した場合はTypeErrorです。``loadTargets(fast=True)`` はUndoが無効でも使用できますが、
失敗時に更新済みのデータを自動ロールバックしません。

``addTarget/addInBetween/removeTarget/removeInBetween/mirrorTarget/flipTarget`` は
OpenMaya API 2.0に同等の標準操作がないため、Mayaの標準コマンド／Shape Editorの
MEL処理を維持し、fast引数を提供しません。独自のMayaプラグインやUndo設定の切替は使いません。

skinCluster ウェイトのバックアップ・復元
------------------------------------------

.. code-block:: python

   from hlib.nodes.skinCluster import SkinCluster

   skin = SkinCluster("hlibExampleMeshSkinCluster")
   skin.dumpWeights("C:/tmp/hlibExampleWeights.json")

   # ... 別シーンで読み込み直す、または同じシーンで何か変更した後に復元する場合 ...
   skin.loadWeights("C:/tmp/hlibExampleWeights.json")

``dumpWeights``/``loadWeights`` は ``influences()`` と同じ並びの全 influence の
頂点ウェイトを単純な JSON 形式でファイルへ書き出し・読み込みます。
``loadWeights`` は、書き出し時の頂点数が現在の mesh と一致し、記録された
influence がすべて現在の skinCluster に存在することを要求します。
一致しない場合はウェイトを変更せず ``ValueError`` を送出します
（influence 名が異なる、頂点数が変わった状態への読み込みは
このメソッドの対象外です。同じ頂点数での接続順序変更は検出しません）。

スキン変形を保ったままjointの姿勢を編集する
--------------------------------------------------

.. code-block:: python

   from hlib.decorator import preservedSkinShape
   from hlib.nodes.joint import Joint

   joint = Joint("hlibExampleJoint")
   with preservedSkinShape([joint]):
       # 現在のjoint姿勢をスキニング基準へ反映する。
       joint.plug("jointOrientZ").set(45.0)

``preservedSkinShape`` は Maya標準の ``skinCluster -moveJointsMode`` /
``-recacheBindMatrices`` を使い、ブロック内での joint 姿勢変更を
「新しいバインド姿勢」として扱います。関節の向きを付け直す、
リグを組み替えるといった作業で、既存のスキニングを壊したくない場合に使います。
ブロック全体(モード切り替え・編集・bind行列の再計算)は一回の Undo にまとまります。

任意の階層変更・influence削除や全フレームの変形保持を保証する機能ではありません。
モード変更・再キャッシュ・復元のRuntimeErrorは実装上抑制されるため、
処理後の形状とモードは呼び出し側でも確認してください。
頂点・CVの座標編集はjointのバインド基準変更とは別の処理です。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
