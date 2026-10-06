引数仕様
====================

lsのコンポーネント取得
----------------------------------------


``hlib.ls(sl=True, type="vertex")`` は選択頂点を ``list[Vertex]`` で返します。
``type`` / ``typ`` に指定できるコンポーネント名は ``vertex``・``edge``・``face``・
``uv``・``controlVertex`` です。単一の正式名称を指定し、別種類からの変換は行いません。
型未指定ではNode・Plug・Componentの混合リストです。範囲はflatten指定によらず単体へ展開し、
複数シェイプも同じリストで返します。対象がなければ空リストです。
既存のノード型指定・joint/skinCluster専用コレクションは維持します。
``component=`` は追加していません。

BlendShapeの追加編集API
-----------------------

``hlib.createBlendShape(base, targets=None, **kwargs)`` は新規BlendShapeを返します。
単一のベースを先頭に明示し、targetsは単体または列、None/空列なら空ターゲットで作成します。
作成フラグの長短名と通常Undoに対応し、照会・編集・fastは受け付けません。

従来の ``addTarget(target, base=None, weight_index=None, full_weight=1.0)`` と
``getTargetAliases/getWeightPlugs/getWeights/getGeometry`` は引数・戻り値とも維持します。
以下の ``target`` は既存ターゲットの整数番号またはweightのエイリアスです。

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

.. code-block:: python

   dst.connect(src, f=True)
   src.connectTo(dst, f=True)  # 同じ接続方向
   dst.disconnect()           # 入力だけを切断し、入力元Plugを返す
   dst.disconnectInput()      # 未接続でもエラーにせず、自身を返す
   dst.disconnectAll()        # 入力と全出力を明示的に切断
   element = array.connect(src, na=True)
   array.disconnect(src, na=True)

``force=True`` は一時的にロックを解除して接続します。
hlib拡張の ``unlock=False`` を併用するとロック解除を禁止できます。

位置・回転・行列
----------------

空間は ``ws=True`` を基本表記とし、``worldSpace=True`` も使えます。
長短名の同時指定は拒否します。

``getTranslation`` / ``setTranslation`` の ``at`` は
0=親原点、1=translate、2=回転ピボット、3=スケールピボット、4以上=行列原点です。
既定値は2です。以前のhlibの行列原点指定は ``at=4`` へ移行してください。
``setTranslation`` はtranslateだけを書き込み、ピボット自体は動かしません。

.. code-block:: python

   position = node.getTranslation(ws=True)
   origin = node.getTranslation(ws=True, at=4)
   channels = node.setTranslation((10, 2, 3), ws=True, get=True)
   node.setTranslation((10, 2, 3), ws=True, safe=True)
   parent_inverse = node.getMatrix(ws=True, p=True, inv=True)

``getQuaternion`` / ``setQuaternion`` は ``ra`` (rotateAxis)、``r`` (rotate)、
``jo`` (jointOrient)で合成対象を選びます。既定は ``ra=False, r=True, jo=True`` です。
ワールド指定などで未対応の組合せはValueErrorになります。

``getScaling`` / ``setScaling``、``getShearing`` / ``setShearing`` は
ローカル指定でscale/shearチャンネルそのものを扱い、jointのinverseScaleを含めません。
ワールド指定はOpenMayaの分解規約を使います。負スケールの符号は行列から一意に
決まらないため、ワールドの指定値と取得値の符号が一致しない場合があります。
以前の ``getScale/setScale/getShear/setShear`` は廃止しました。

``get=True`` は書き込まず設定すべき値を返します。
位置・回転・スケール・シアーは数値リスト、``setMatrix`` は
``translate/rotate/scale/shear`` をキーとする辞書を返します。
後者の辞書にはhlibの値型を格納します。
コレクションの ``get=True`` も各対象の計算結果のリストを返します。

単位とsafe
----------

Plugの ``get/set`` は内部単位(cm/rad/秒)、``getu/setu`` は現在のUI単位です。
``safe=True`` は書込み失敗を抑制し、複合値では書ける子だけを書き込みます。
Plugのsafe指定は失敗数を返します。Transformのsafe指定は自身を返します。
``fast=True`` はhlib固有のUndoなし直接更新であり、safeとは別の指定です。

.. code-block:: python

   node.getPlug("ry").setu(90)  # UIがdegの場合90度
   failed = node.getPlug("translate").set((1, 2, 3), safe=True)
   node.setRotation((0, 90, 0), ws=True, unit="deg")

``setRotation`` の第2位置引数は空間になりました。``unit`` は名前付きで指定します。
回転double3の ``set`` も第2位置引数はsafe、unitは名前付きです。
通常のsetterが自身を返すhlibの規則と、om2派生の数学型は維持します。
引数・戻り値の対応範囲は、このページに記載した仕様に従います。

アトリビュートの追加
--------------------

正式名を ``addAttr`` に変更しました。旧 ``addAttribute`` は残していません。
typeを省略するとdoubleです。``at:/dt:`` 接頭辞やMayaの ``at/dt`` も使えます。
``childNames/childShortNames/childSuffixes/subType`` で子を自動生成できます。
hlibでは既定で追加したPlugを返します。``getPlug=False`` を明示した場合のみNoneを返します。

.. code-block:: python

   label = node.addAttr("label", "string", dv="control")
   offset = node.addAttr("offset", "double3", subType="doubleLinear")
   node.addAttr("weight", min=0, max=1, dv=1, k=True)
   node.rename("control", ignoreShape=True)

``rename`` の旧 ``ignore_shape`` 引数も ``ignoreShape`` へ移行しました。

ここでの ``addAttr`` はNodeのメソッドです。``hlib.addAttr(node, ...)`` は
Mayaコマンド用の入口で、従来どおり常にPlugを返し、getPlug引数は受け取りません。
