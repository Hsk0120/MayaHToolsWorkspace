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
``worldSpace`` と ``ws`` は一方だけを指定します。他の長短名の併用規則は各APIを参照してください。
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
   * - 選択した頂点をShapeごとにまとめる
     - ``Selection.capture().filter("vertex").getComponents()``
     - :class:`~mlib.common.selection.Selection`
   * - Meshやカーブの要素を取得する
     - Transformから ``getShape()``、Meshは ``getVertices()``、NurbsCurveは ``getCVs()``
     - :doc:`autoapi/mlib/components/index`
   * - ターゲットのデルタを編集する
     - ``getTargetDeltas()``、``setTargetDeltas()``、``resetTargetVertices()``
     - :class:`~mlib.nodes.blendShape.BlendShape`
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

.. code-block:: python

   joint = Joint("newJoint", create=True)
   control = Transform("newControl", create=True)

``create=True`` は新規作成です。指定名が既にある場合はMayaの規則で連番化されます。
作成には名前だけで初期化でき、Maya nodeTypeへ一意に登録された具象クラスが必要です。
詳細は :meth:`~mlib.nodes.node.Node.__new__` を参照してください。

複数形は保持順に実行し、後続の失敗で先行変更を自動では戻しません。
同じ値をまとめて設定する例です。要素別の引数は :meth:`~mlib.nodes.node.Nodes.callEach` で渡します。

.. code-block:: python

   joints = mlib.ls(type="joint")
   joints.setRadius(1)

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
