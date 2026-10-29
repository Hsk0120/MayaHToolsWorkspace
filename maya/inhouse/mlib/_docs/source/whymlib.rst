なぜ mlib ?
===========

**mlibは、PyMELのようにMayaのノードをPythonのオブジェクトとして扱うためのライブラリです。**

ノード名の文字列をコマンドへ渡して操作する代わりに、取得したノードオブジェクトから
メソッドを呼び出します。TransformやJointなど、Mayaのノード型に対応するクラスが
操作をまとめるため、対象とその処理を一緒に扱えます。

この考え方をアトリビュートやコンポーネント（頂点・エッジ・フェース・CV・UV）にも広げ、
取得・設定・接続をそれぞれのオブジェクトから行えます。
マトリクスやクォータニオンもオブジェクトとして取得し、そのまま計算へ使えます。
mlibはPyMELに依存せず、独自のAPIを提供します。

.. code-block:: python

   import mlib

   control = mlib.ls("control")[0]
   control.setTranslate((1, 2, 3))
   control.getPlug("visibility").set(True)
   matrix = control.getMatrix(worldSpace=True)

この例の ``control`` は既存のTransform名です。以下の作成例はMaya内で実行できます。
mlibはMaya標準のコマンド・OpenMayaと併用する基礎ライブラリです。

クラス設計の概要
----------------------------------------------------------------------

役割を「シーン上の対象」と「計算に使う値」に分けています。
ノードやアトリビュートのラッパーはシーンを参照し、数学型は取得した値を保持します。
``Node``・``Plug``・``Component`` の共通基底は :class:`~mlib.core.object.Object` です。
数学型や複数形コレクションは別の役割です。対象の検索には ``mlib.ls`` を使います。

.. list-table::
   :header-rows: 1
   :widths: 18 27 55

   * - 分類
     - 代表クラス
     - 役割
   * - ``nodes``
     - Node・Transform・Joint・SkinCluster
     - ノード全体の操作。対象の型に合ったメソッドを提供
   * - ``plugs``
     - Plug・Double3Plug・MultiPlug
     - アトリビュートの取得・設定・接続。コンパウンドアトリビュートやマルチアトリビュートもオブジェクトとして扱う
   * - ``components``
     - Vertex・CV・Edge・Face・UV
     - コンポーネント（頂点・エッジ・フェース・CV・UV）を参照し、座標や接続情報を扱う
   * - ``maths``
     - Matrix・Quaternion・Vector・EulerRotation
     - シーンから取得した値の計算。計算だけではシーンを変更しない
   * - ``common``
     - Selection・Namespace・Plugin・ScriptJobs
     - 選択・参照関係・プラグイン・イベントと既存の共通計算を扱う
   * - ``cmds``
     - getNode・getPlug・createNode・lsなどの基礎7関数
     - 対象の取得・作成の入口。検索には ``mlib.ls()``、作成には ``mlib.createNode()`` を使う

``nodes`` に手書きクラスが無いnodeTypeのノードも ``Node`` 固定にはならず、Mayaの継承チェーン上で
最も近い登録クラスを基底にしたクラスが自動生成され、``mlib.nodes.<TypeName>`` で取得できます。
手書き・自動生成のどちらも ``isinstance`` はMayaの抽象祖先を含まないため、Mayaの継承に基づく
判定は ``isType()`` で行います(:ref:`dynamic-node-classes`)。

ここでいうコンポーネントは、Mayaの形状を構成する要素です。
例えばメッシュの頂点・エッジ・フェースや、カーブのCVを指します。
具体的な操作は :mod:`~mlib.components` の各クラスを参照してください。

代表クラスだけを抜き出した図です。三角の矢印は基底クラスを指します。
クラス名をクリックするとAPIリファレンスへ移動できます。

ノード：Joint・Mesh・NurbsCurve
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _includes/nodes.rst

アトリビュート：Plug
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _includes/plugs.rst

コンポーネント：頂点・エッジ・フェース・CV・UV
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. include:: _includes/components.rst

数学型：マトリクス・回転・ベクトル
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python共通の基底クラス ``object`` から、``maya.api.OpenMaya`` （Python API 2.0）、
mlibの数学型へと継承が続きます。``object`` はPython組み込みのクラスです。
OpenMayaのクラス名はAutodesk公式リファレンス（Maya 2027）、
mlibのクラス名はこのドキュメントのAPIリファレンスへリンクしています。

.. include:: _includes/maths.rst

数学型はそれぞれ対応するOpenMayaの型を直接継承しています。
例えば ``Matrix`` は ``MMatrix`` の派生クラスで、mlibの操作メソッドを追加しています。

``Shape`` と ``Transform`` はどちらもDAGノードです。
シーン上でShapeがTransformの子になることと、クラスの継承は別の関係です。
単数クラスは1対象を操作し、複数形クラスは複数の対象を保持します。

**Mayaへの問い合わせはメソッド、保持する値はプロパティを基本とします。**
例えば ``node.getName()`` は現在の名前を問い合わせ、``plug.getNode()`` は保持する所有ノード参照です。
``matrix`` や ``quaternion`` の成分を変更しても、取得元ノードへ自動反映されません。
反映には ``setMatrix()`` や ``setRotate()`` を明示的に呼びます。

ノード単位で操作する
----------------------------------------------------------------------

``mlib.ls()`` の検索結果には、実際のノード型に対応したクラスのインスタンスが入ります。
JointならJointの操作、SkinClusterならウェイト関連の操作を、その対象から呼べます。

.. code-block:: python

   import mlib

   source = mlib.createNode("transform", name="mlibDemo_source")
   target = mlib.createNode("transform", name="mlibDemo_target")

   source.setTranslate((1, 2, 3))
   source.setScale((2, 2, 2))
   source.getPlug("useOutlinerColor").set(True)
   source.getPlug("outlinerColor").set((0.3, 0.7, 1.0))
   target.setMatrix(source.getMatrix(worldSpace=True), worldSpace=True)

.. list-table:: 便利な操作の例
   :header-rows: 1

   * - 対象
     - メソッド
     - 用途
   * - Node
     - ``getType()`` / ``isType()``
     - MayaのnodeType名を取得し、Mayaの継承チェーンで型を判定する
   * - Node
     - ``mfn()``
     - そのノードで最も具体的なOpenMayaのfunction setを取得する
   * - Transform
     - ``getMatrix()`` / ``setMatrix()``
     - マトリクスを取得・反映する
   * - Transform
     - ``resetAttrs()``
     - translate・rotate・scale・shearを既定値へ戻す
   * - Transform
     - ``addConstraint()`` / ``deleteConstraints()``
     - コンストレイントを作成・削除する
   * - Joint
     - ``freezeRotate()`` / ``jointOrientToRotate()``
     - rotateとjointOrientの間で姿勢を移す
   * - SkinCluster
     - ``getWeights()`` / ``setWeights()``
     - スキンウェイトを取得・反映する

複数の対象へ同じ操作を行う場合は、単数のメソッドを ``for`` で呼びます。
複数形クラス(``Joints``・``SkinClusters`` 等)は、重複を除いた参照を保持順に持つ容器です。

.. code-block:: python

   for transform in (source, target):
       transform.setTranslate((0, 5, 0))
   matrices = [transform.getMatrix(worldSpace=True) for transform in (source, target)]

アトリビュート単位で操作する
----------------------------------------------------------------------

アトリビュートは ``Plug`` オブジェクトとして扱います。ノード名とアトリビュート名を毎回連結する代わりに、
取得したアトリビュートから読み書きや接続を行えます。説明と使用例は ``getPlug()`` に統一しています。

.. code-block:: python

   # 上の作成例で用意したsourceとtargetを使用
   translate_x = source.getPlug("tx")
   translate_x.set(10)
   value = translate_x.get()

   source.getPlug("tx").connectTo(target.getPlug("tx"))
   target.getPlug("tx").disconnect(source.getPlug("tx"))

   target.getPlug("visibility").set(False)
   target.getPlug("visibility").setFlags(locked=True)

``tx`` と ``translateX`` は同じアトリビュートを指します。接続は
``source.getPlug("tx") >> target.getPlug("tx")`` のように演算子でも書けます。
``a >> b`` は ``a.connectTo(b)`` で接続先 ``b`` を、``a << b`` は ``a.connect(b)`` で自身 ``a`` を、
``a // b`` は ``a`` から ``b`` への接続の解除(``b.disconnect(a)``)で接続先 ``b`` を返します。
いずれもUndoに記録される通常経路だけで、マルチアトリビュート全体への ``>>`` はMayaと同じく
``RuntimeError`` になるため、空き要素への接続は ``a.connectTo(multi, nextAvailable=True)`` を使います。
``translate`` のような3成分アトリビュートは ``Double3Plug``、マルチアトリビュートは ``MultiPlug`` など、
アトリビュートの構造に合ったラッパーが選ばれます。``plug.getType()`` はMayaのアトリビュート型名
(``doubleLinear``・``double3`` など)を返し、ラッパーのクラスは ``type(plug)`` で調べます。

ノードの ``setRotate()`` は姿勢を扱い、``getPlug("rotate").set()`` はrotateアトリビュートの値を扱います。
JointのjointOrientなどがある場合、この2つは同じ操作とは限りません。
Mayaコマンドへ渡すときは ``getFullName()`` で名前へ変換します。値・接続・単位の仕様は
:class:`~mlib.plugs.plug.Plug` と :doc:`getting_started` を参照してください。

マトリクス・クォータニオンを取得して計算する
----------------------------------------------------------------------

取得した値がそのまま数学オブジェクトになるため、マルチアトリビュートから型を組み立て直さずに
積・逆マトリクス・回転補間などへ進めます。``mlib.maths`` の数学型は
OpenMaya API 2.0の対応する型を継承しています。

マトリクスの合成・逆マトリクス
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

次の例は、あるTransformのワールドマトリクスを、基準Transformに対する相対マトリクスへ変換します。
Mayaの行ベクトル規約では、相対マトリクスに基準のワールドマトリクスを右から掛けると元に戻せます。

.. code-block:: python

   import mlib

   reference = mlib.createNode("transform", name="mlibDemo_reference")
   driven = mlib.createNode("transform", name="mlibDemo_driven")
   reference.setTranslate((10, 0, 0))
   driven.setTranslate((12, 3, 0))

   reference_world = reference.getMatrix(worldSpace=True)
   driven_world = driven.getMatrix(worldSpace=True)
   relative = driven_world * reference_world.inverse()

   restored_world = relative * reference_world
   driven.setMatrix(restored_world, worldSpace=True)

``*`` でマトリクスの積、``inverse()`` で逆マトリクスを扱えます。
逆マトリクスを求める例では、ゼロスケールなどの特異なマトリクスを避けてください。
空間やマトリクスの適用条件は :class:`~mlib.maths.matrix.Matrix` と
:class:`~mlib.nodes.transform.Transform` の各メソッドを参照してください。

クォータニオンの補間
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

回転は ``getQuaternion()`` で取得し、``slerp()`` で補間した結果をそのまま反映できます。

.. code-block:: python

   import mlib

   start = mlib.createNode("transform", name="mlibDemo_start")
   end = mlib.createNode("transform", name="mlibDemo_end")
   result = mlib.createNode("transform", name="mlibDemo_result")
   end.setRotate((0, 90, 0))

   q_start = start.getQuaternion(worldSpace=True)
   q_end = end.getQuaternion(worldSpace=True)
   q_middle = q_start.slerp(q_end, 0.5)
   result.setRotate(q_middle, worldSpace=True)

   rotation_matrix = q_middle.asMatrix()

``0.5`` は2つの回転の中間です。Quaternionには角度単位を別途指定しません。
数値で回転を渡す場合は既定が度です(ラジアンは ``unit="rad"``)。EulerRotate・Quaternionは
内部がラジアンの値で、``unit`` に関係なくそのまま渡せます。
この例は現在の姿勢を計算するもので、アニメーションキーは作成しません。
詳しい演算は :mod:`~mlib.maths` の各クラスを参照してください。

ツール開発での使い分け
----------------------------------------------------------------------

* 対象の検索は ``mlib.ls()``、作成は ``mlib.createNode()``。
* ノード全体の操作はNode派生、アトリビュートの操作はPlug、形状の一部はComponent。
* 計算はMatrix・Quaternionなどの値で行い、結果の反映は明示的なsetter。
* 通常の編集はUndo有効時に記録。複数操作を一つのツールとしてまとめる場合に外側でUndoをまとめる。
* ``fast=True`` があるメソッドは、Undo不要の処理で明示して使う。

Maya標準のコマンドをそのまま使う場面もあります。mlibですべてを置き換える必要はありません。
mlibが提供しないコマンド・UI・ファイル操作は ``maya.cmds`` や標準ライブラリを使い、
必要な結果を ``mlib.ls()`` で参照へ変換します。

その他のクラスは :doc:`modules` を参照してください。
