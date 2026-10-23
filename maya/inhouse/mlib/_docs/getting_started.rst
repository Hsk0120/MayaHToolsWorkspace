mlib入門
========

mlibの読み込みからノード・アトリビュート操作までの基本を説明します。
機能ごとの詳しい使用例は :doc:`usage` から参照できます。

実行環境
--------

ワークスペースのバージョン別起動バッチから Maya を起動すると、
``maya/inhouse`` が Python の検索パスに追加されます。
以下は Maya の Script Editor の Python タブで実行する例です。
ノード作成例は現在のシーンにノードを追加します。

使用例では ``import mlib`` を基本とし、コマンドは ``mlib.createNode()`` や
``mlib.ls()`` のように mlib 直下から呼び出します。クラスを直接利用する場合は、
``mlib.nodes.Node`` など所属パッケージから取得します。

ノードとアトリビュート
--------------------------

通常の編集はコマンド・メソッドの内部でUndoをまとめるため、外側を
``undoChunk`` で囲む必要はありません。各呼び出しを個別の操作として扱います。

.. code-block:: python

   import mlib

   node = mlib.createNode("transform", name="mlibExample")
   node.getPlug("visibility").set(False)

   print(node.getName())
   print(node.getPlug("visibility").get())
   print(mlib.ls(type="transform"))

この例では、アトリビュート変更とノード作成は別々のUndoになります。
複数の呼び出し全体を一回で戻すツールを開発する場合のみ、
:ref:`tool-undo-chunk` の方法でまとめます。

``createNode`` は ``maya.cmds.createNode`` にキーワード引数を渡し、
対応するラッパーを返します。既存ノードは ``mlib.getNode("ノード名")`` で取得できます。
``ls`` は ``maya.cmds.ls`` の引数を受け取り、通常はラッパーのリストを返します。
``type="joint"`` と ``type="skinCluster"`` は、それぞれ ``Joints`` と
``SkinClusters`` コレクションを返します。

ノードのアトリビュートは、:meth:`~mlib.nodes.node.Node.getPlug` で取得した
:class:`~mlib.plugs.plug.Plug` オブジェクトを通して操作します。
説明と使用例では、取得メソッドを ``getPlug()`` のようにget付きの正式名で記載します。
getを省いた取得メソッドの別名は提供しません（:doc:`getter_aliases`）。

対象の種類を判別して取得する
----------------------------

ノード・アトリビュート・コンポーネント（頂点・エッジ・フェース・CV・UV）を
同じ入口で取得したい場合は ``mlib.core.object`` から ``Object`` をimportします。
既存対象の参照を返し、新しいノードは作成しません。
以下は ``pCube1`` が存在するシーンでの例です。

.. code-block:: python

   from mlib.core.object import Object

   node = Object("pCube1")          # Transform
   plug = Object("pCube1.tx")       # DoubleLinearPlug
   vertex = Object("pCube1.vtx[0]") # Vertex
   print(isinstance(node, Object))  # True
   print(Object(node) is node)      # True

``Object`` は単数の ``Node``・``Plug``・``Component`` の共通基底です。
数学型と複数形コレクションは継承しません。
要素範囲は ``Object`` ではなく ``mlib.common.Selection("pCube1.vtx[0:3]")`` で取得します。
アトリビュートとコンポーネントの名前が重なる場合はMayaの選択解決に従います。
アトリビュートとして明示する場合は ``node.getPlug()`` または ``mlib.getPlug()`` を使います。
対象の種類が決まっている既存コードでは ``mlib.getNode()``・``mlib.getPlug()`` をそのまま使えます。

目的から使い方を探す
--------------------

取得した参照を次の操作へ渡す例と、値・単位・復元範囲の説明をまとめています。

.. list-table::
   :header-rows: 1

   * - 目的
     - 基本の書き方
     - 詳細
   * - 選択した頂点をまとめて編集
     - ``mlib.common.Selection.capture().filter("vertex").getComponents()``
     - :doc:`guide_geometry`
   * - アトリビュートの値を取得
     - ``node.getPlug("translateX").get()``、UI単位は ``get(uiUnits=True)``
     - :doc:`cmds_interop`
   * - 作成した形状を編集
     - 戻り値の型を確認し、Transformは ``getShape()`` を取得
     - :doc:`guide_commands`
   * - ターゲットの頂点を除外・デルタを保存
     - ``resetTargetVertices``、``getTargetDeltas``、``setTargetDeltas``
     - :doc:`guide_deformers`
   * - 選択頂点のスキンウェイトを再配分
     - ``skin.redistributeWeights(mlib.ls(sl=True, type="vertex"))``
     - :doc:`guide_deformers`
   * - 選択を保持・復元
     - ``Selection.capture()`` で保持し、保持した参照の ``select()`` で復元
     - :doc:`selection_and_channelbox`
   * - 更新を高速化
     - 操作の対応条件を確認して ``fast=True``
     - :doc:`fast_edit`
   * - プラグインと拡張の状態を確認
     - ``tryLoad() == LOADED``、``extensions.getDiagnostics()``
     - :doc:`guide_environment`、:doc:`extensions`

.. code-block:: python

   # baseの頂点を選択している状態。返却されたweight Plugを続けて使用する。
   bs = mlib.getNode("faceBlendShape")
   weight = bs.addTarget(mlib.getNode("smileMesh"))
   weight.set(0.5)
   bs.resetTargetVertices(weight, mlib.ls(sl=True, type="vertex"))

メソッドの通常更新はUndoに対応します。``fast=True`` はUndoなしの対応操作に
限られます。作成コマンドの数値フラグはMayaのUI単位、オブジェクトの値操作は
cm・radian・秒を基本にするため、両者をつなぐときは :doc:`cmds_interop` を参照してください。

クラスを直接importして使う
---------------------------

``mlib.createNode``/``mlib.ls``/``mlib.getNode`` などのコマンドは ``mlib`` 直下で
使える一方、``Node``/``Joint``/``Matrix`` のようなクラス自体は ``mlib`` 直下には
公開されません。所属するサブパッケージから import します。

.. code-block:: python

   import mlib
   from mlib.nodes import Node, Joint
   from mlib.maths import Matrix

   nodes = mlib.ls(sl=True)      # 選択中のノードをラッパーのリストで取得
   joint = Joint("joint1")       # 既存ノードを直接ラップ
   matrix = Matrix()             # 単位行列(om2.MMatrix の派生)

``create=False``（既定）で具象クラスを呼び出すと、そのクラスまたは派生型に対応する
既存ノードを取得します。``Joint("transform1")`` のような非互換の型はTypeErrorです。
``Transform("joint1")`` は、Transformの派生型であるJointを返します。
種類を指定せず実際のMaya nodeTypeから自動選択する場合は、
``mlib.getNode("ノード名")`` / ``Node("ノード名")`` を使ってください。

新規作成は、具象クラスに ``create=True`` をキーワードで指定します。

.. code-block:: python

   from mlib.nodes import Joint, Transform, MultiplyDivide

   joint = Joint("newJoint", create=True)
   control = Transform("newControl", create=True)
   multiply = MultiplyDivide("newMultiply", create=True)

指定名が既にある場合はMayaの規則で連番化され、通常のUndoで作成を戻せます。
``create`` はbool限定で、Trueの場合は空でない文字列の名前が必要です。
作成可能なクラスと制約は :doc:`guide_nodes` の「クラスからノードを作成する」を参照してください。
既存取得の ``mlib.getNode()`` や ``mlib.getPlug()`` に ``create`` を渡す形式は追加していません。

再読み込み
----------

.. code-block:: python

   import mlib
   mlib.reload()

再読み込みは mlib 内の依存関係をもとに行われます。
古いクラスのインスタンスや ``from ... import ...`` で取得済みの参照は
自動では置き換わらないため、必要な参照・ラッパーを取得し直してください。

次に読むページ
----------------

* :doc:`guide_commands` — シーン編集・選択・キー設定
* :doc:`guide_plugs` — アトリビュートの値・接続・配列
* :doc:`usage` — 機能別ガイドの一覧
