mlib入門
========

既存のMayaノードを取得し、アトリビュートや形状の参照を次の操作へ渡す基本を説明します。
個別の引数・返却値・制限は、各APIのリファレンスを参照してください。

実行環境
--------

対象はMaya 2022〜2027のPython 3環境です。Maya付属のPythonを使用します。

.. list-table:: MayaとPythonのバージョン（Windows）
   :header-rows: 1

   * - Maya
     - Python
   * - 2022
     - 3.7
   * - 2023
     - 3.9
   * - 2024
     - 3.10
   * - 2025・2026
     - 3.11
   * - 2027
     - 3.13

``mlib`` フォルダの親フォルダを、Pythonの検索パス（``PYTHONPATH`` または ``sys.path``）へ追加してください。
例えば ``C:/tools/mlib`` に配置した場合は、Script EditorのPythonタブで次を実行します。

.. code-block:: python

   import sys
   sys.path.insert(0, "C:/tools")
   import mlib

以降の例もScript EditorのPythonタブで実行します。作成・編集の例は現在のシーンを変更します。

コマンドは ``import mlib`` の後、``mlib.createNode()`` のように呼び出します。
クラスは ``mlib.nodes``・``mlib.maths`` など、所属するパッケージから取得します。

ノードとアトリビュート
----------------------

.. code-block:: python

   import mlib

   node = mlib.createNode("transform", name="mlibExample")
   plug = node.getPlug("translateX")
   plug.set(10)

   print(node.getName())
   print(plug.get())
   print(mlib.ls(type="transform"))

``createNode`` は作成した型に対応するラッパーを返します。
既存ノードは ``mlib.ls("ノード名やパターン")`` で検索でき、完全DAGパスも指定できます。
``ls`` は通常ラッパーのリストを返し、``type="joint"``・``type="skinCluster"`` の場合は
それぞれ ``Joints``・``SkinClusters`` を返します。

アトリビュートは :meth:`~mlib.nodes.node.Node.getPlug` で取得した
:class:`~mlib.plugs.plug.Plug` の ``get()``・``set()`` で読み書きします。
``node.tx`` もPlugを返しますが、代入ではなく ``node.tx.set(10)`` で値を変更します。

値の単位は距離cm・角度rad・時刻秒を基本とします。Plugを現在のUI単位で扱う場合は
``get(uiUnits=True)``・``set(..., uiUnits=True)`` を使います。
``maya.cmds`` へ渡すフラグ値はMayaの単位規則に従います。

.. _tool-undo-chunk:

通常の編集はUndo有効時に記録され、上の作成と値変更は別々のUndoになります。
複数の呼出し全体を一回で戻す場合は、外側でまとめます。

.. code-block:: python

   from mlib.decorator import undoChunk

   with undoChunk("editControl"):
       node.setTranslate((1, 2, 3))
       node.getPlug("visibility").set(False)

対応するAPIの ``fast=True`` はUndoなしの直接更新で、Undo設定は変更しません。
``Plug.set(safe=True)`` は対応する書込み失敗数を返し、成功した成分の更新は残します。
未対応条件や他のsetterのsafeの意味は、各メソッドを参照してください。
Mayaのコマンドのフラグを受け取る入口(``mlib.ls`` 等)は、Mayaと同じ長短の名前を受け付け、長短の一方だけを指定します。
署名の ``_UNSET``・``Ellipsis`` は省略判定用の内部値です。

名前・選択・型から取得する
--------------------------

``maya.cmds.ls`` と同じように、``mlib.ls`` で名前・選択・型から対象を検索します。
名前の文字列ではなく、対象に対応するNode・Plug・Componentを返します。
次の例は ``pCube1`` が存在するシーンが前提です。

.. code-block:: python

   import mlib

   nodes = mlib.ls("pCube*")
   selected = mlib.ls(selection=True)
   joints = mlib.ls(type="joint")
   plugs = mlib.ls("pCube1.tx")
   vertices = mlib.ls("pCube1.vtx[0:3]", type="vertex")

   for node in nodes:
       print(node.getName())

通常の戻り値はリストです。1件だけ取り出す場合も、結果があることを確認して ``nodes[0]`` のように取得します。
一致する対象がなければ空になります。検索はノードの作成や選択変更を行いません。
コンポーネントの範囲は単体の参照へ展開され、上の ``vertices`` には4つのVertexが入ります。
``type="vertex"`` は頂点だけを抽出する指定で、ノードやフェースを頂点へ変換する指定ではありません。
取得したノードのアトリビュートは ``node.getPlug("名前")`` でも参照できます。

目的から使い方を探す
--------------------

目的に近い入口から、引数と操作対象を確認してください。

.. list-table::
   :header-rows: 1

   * - 目的
     - 基本の書き方
     - API
   * - 名前や条件で既存対象を探す
     - ``mlib.ls("名前やパターン")``、``mlib.ls(selection=True)``
     - :doc:`autoapi/mlib/cmds/index`
   * - 値・単位・接続を扱う
     - ``node.getPlug("translateX").get()``、``plug.getSource()``
     - :class:`~mlib.plugs.plug.Plug`
   * - ノードの型を調べ、Mayaの継承で判定する
     - ``node.getType()``、``node.isType("shape")``、``node.getType(inherited=True)``
     - :meth:`~mlib.nodes.node.Node.isType`、:ref:`dynamic-node-classes`
   * - ユーザー定義アトリビュートを列挙する
     - ``node.getPlugs(userDefined=True)``。名前は ``[p.getLongName() for p in plugs]``。
       ``userDefined=True`` は ``cmds.listAttr`` のフラグと併用できません(TypeError)
     - :meth:`~mlib.nodes.node.Node.getPlugs`
   * - 選択した頂点をShapeごとにまとめる
     - ``Selection.capture().filter("vertex").getComponents()``
     - :class:`~mlib.common.selection.Selection`
   * - Meshやカーブの要素を取得する
     - Transformから ``getShape()``、Meshは ``getVertices()``、NurbsCurveは ``getCVs()``
     - :doc:`autoapi/mlib/components/index`
   * - 選択頂点のスキンウェイトを再配分する
     - ``skin.redistributeWeights(mlib.ls(selection=True, type="vertex"))``
     - :meth:`~mlib.nodes.skinCluster.SkinCluster.redistributeWeights`
   * - 選択を保持して復元する
     - ``Selection.capture()`` で保持し、その ``select()`` で選択に反映
     - :class:`~mlib.common.selection.Selection`
   * - プラグインや拡張の状態を調べる
     - ``package.tryLoad()``、``extensions.getDiagnostics()``
     - :class:`~mlib.common.pluginPackage.PluginPackage`、:mod:`mlib.core.extensions`

表中の ``Selection``・``PluginPackage`` は ``from mlib.common import ...`` で取得します。
``package`` はPluginPackageのインスタンスです。
``extensions`` は ``from mlib.core import extensions`` で取得します。
形状・デフォーマの例では、対象Shapeや所属頂点を各APIの条件に合わせて指定してください。

クラスを直接importして使う
--------------------------

クラスは所属するサブパッケージからimportします。``Node``・``Joint``・``Matrix`` などを
``mlib`` 直下へ再公開する入口はありません。

.. code-block:: python

   from mlib.nodes import Node, Joint, Transform
   from mlib.maths import Matrix

   joint = Joint("joint1")  # 既存のJoint
   node = Node("pCube1")    # 実際のnodeTypeに対応するラッパー
   matrix = Matrix()       # 単位マトリクス

具象クラスによる既存取得は、そのクラスまたは派生型を受理します。
``Joint("transform1")`` はTypeError、``Transform("joint1")`` はJointを返します。
名前や型からまとめて検索する場合は ``mlib.ls`` を使います。

ノードの作成は :func:`~mlib.cmds.createNode.createNode`\ (``mlib.createNode``。``cmds.createNode`` 相当)
だけで行います。クラスのconstructorは既存ノードの取得専用で、作成を指示する引数や
クラスメソッドはありません。

.. code-block:: python

   joint = mlib.createNode("joint", name="newJoint")           # Joint
   control = mlib.createNode("transform", name="newControl")   # Transform
   shape = mlib.createNode("mesh", parent=control)             # Mesh。親を省略するとtransformが自動で作られます
   quick = mlib.createNode("multiplyDivide", fast=True)        # OpenMayaで直接作成。Undoに記録されません

戻り値は作成したノードの実際のnodeTypeに対応するラッパーです。指定名が既にある場合は
Mayaの規則で連番化されます。``name``・``parent``・``shared``・``skipSelect`` と
その短縮名は ``cmds.createNode`` と同じ意味で、追加のMayaフラグもそのまま渡せます。
詳細は :func:`~mlib.cmds.createNode.createNode` を参照してください。

複数形(``Joints``・``SkinClusters`` 等)は、重複を除いたノード参照を保持順に持つ容器です。
各要素への操作は、単数のメソッドを ``for`` で呼びます。

.. code-block:: python

   for joint in mlib.ls(type="joint"):
       joint.setRadius(1)

.. _dynamic-node-classes:

動的ノードクラス
----------------

``mlib.nodes`` に手書きクラスが無いnodeType(``pointLight``・``airField``・``wrap`` など)のノードも、
``mlib.ls``・``mlib.getNode``・``mlib.createNode`` の結果は ``Node`` 固定ではなく、
そのnodeTypeに対応するクラスのインスタンスになります。クラスは最初に要求されたときに
型名の先頭を大文字にした名前(``pointLight`` なら ``PointLight``)で自動生成され、
``mlib.nodes.PointLight`` のように ``mlib.nodes.<TypeName>`` でも取得できます。
``getType()`` はラッパーのクラス名ではなくMayaのnodeType名をそのまま返します。

.. code-block:: python

   import mlib

   light = mlib.createNode("pointLight", name="mlibLightShape")
   print(type(light).__name__)                      # PointLight
   print(isinstance(light, mlib.nodes.PointLight))  # True
   print(isinstance(light, mlib.nodes.Shape))       # True。基底は最寄りの登録クラス
   print(light.getType())                           # pointLight
   print(light.isType("light"))                     # True。Mayaの継承チェーンで判定

   same = mlib.nodes.PointLight("mlibLightShape")   # 具象クラスを明示した取得も可能

基底はMayaの継承チェーン(``cmds.nodeType(inherited=True)``)上で最も近い登録クラスで、
``pointLight`` なら ``Shape``、``wrap`` なら ``Node``、``symmetryConstraint`` なら
``Constraint`` です。登録クラスと生成対象の間にある抽象型(``geometryFilter``・
``containerBase``・``entity`` など)のクラスは作られず、生成クラス同士が親子になることも
ありません。生成クラスについて保証するのは「最寄りの登録クラスの派生である」ことだけです。

手書きクラスも同様で、``SkinCluster`` は ``Node`` の直接の派生、``Transform`` は
``DagNode`` の直接の派生です。したがって ``isinstance`` はMayaの抽象祖先を含む継承関係を
表しません。Mayaの継承に基づく判定は ``isType()`` か ``getType(inherited=True)``\ (基底型から
自身への順の ``list[str]``)で行います。``type(node) is mlib.nodes.Node`` のような厳密な型比較も、
未登録型が生成クラスになるため ``isinstance`` か ``isType()`` に置き換えてください。

.. code-block:: python

   skin = mlib.ls(type="skinCluster")[0]
   print(skin.isType("geometryFilter"))                      # True
   print("geometryFilter" in skin.getType(inherited=True))   # True
   print(isinstance(skin, mlib.nodes.GeometryFilter))        # False。手書きクラスは抽象祖先を継承しない

``mlib.nodes.GeometryFilter`` のように抽象型を要求した場合も同じ規則でクラスが生成されますが、
対応するインスタンスが無いため ``isinstance`` には使えません。Mayaが認識しない型名
(プラグイン未ロードを含む)は ``AttributeError``、``mlib.nodes.pointLight`` のような
先頭小文字の綴りも ``AttributeError`` です。生成クラスは ``mlib.nodes.__all__`` と
APIリファレンスには載りません。

生成クラスは要求時に作られてキャッシュされ、次の3つの契機で廃棄されます。
廃棄後の取得では作り直されるため、保持していたクラス参照に対する ``isinstance`` は偽になり、
そのクラスを明示した取得は ``TypeError`` になります。保持中の生成クラスは
``mlib.nodes.<TypeName>`` で取り直してください。

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 契機
     - 内容
   * - 型登録表の変更
     - ``register``・``replace``・``clear`` による登録の追加・置換と、拡張(``mlib_*``)の登録・解除
   * - ``mlib.reload()``
     - 型登録表を作り直すため、生成クラスもすべて廃棄する
   * - プラグインのロード/アンロード
     - :class:`~mlib.common.plugin.Plugin` の ``load()``・``unload()``\ (``PluginPackage`` 経由を含む)で
       継承キャッシュと生成クラスを廃棄する。``cmds.loadPlugin`` の直接呼出しやPlug-in Managerの操作には追従しない

再読み込み
----------

.. code-block:: python

   import mlib
   mlib.reload()

本体を再読み込みし、拡張を再探索して型登録を作り直します。
import済みのクラスや保持したラッパーは自動では置き換わらないため、必要な参照を取得し直します。
詳細は :func:`~mlib.reload` を参照してください。

次に読むページ
--------------

* :doc:`whymlib` — 参照と値に分ける考え方
* :doc:`modules` — 用途ごとのモジュールとAPI
* :doc:`autoapi/mlib/index` — 公開パッケージと7つのコマンド入口
