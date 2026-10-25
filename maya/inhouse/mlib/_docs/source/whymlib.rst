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
   matrix = control.getMatrix(ws=True)

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
     - Plug・Double3Plug・ArrayPlug
     - アトリビュートの取得・設定・接続。複合アトリビュートや配列もオブジェクトとして扱う
   * - ``components``
     - Vertex・CV・Edge・Face・UV
     - コンポーネント（頂点・エッジ・フェース・CV・UV）を参照し、座標や接続情報を扱う
   * - ``maths``
     - Matrix・Quaternion・Vector・EulerRotate
     - シーンから取得した値の計算。計算だけではシーンを変更しない
   * - ``common``
     - Selection・Namespace・Plugin・ScriptJobs
     - 選択・参照関係・プラグイン・イベントと既存の共通計算を扱う
   * - ``cmds``
     - getNode・getPlug・createNode・lsなどの基礎7関数
     - 対象の取得・作成の入口。検索には ``mlib.ls()``、作成には ``mlib.createNode()`` を使う

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
TRSやピボットをまとめる :class:`~mlib.maths.transformation.Transformation` は、
これらの値を保持するクラスで、OpenMaya型の派生ではありません。

``Shape`` と ``Transform`` はどちらもDAGノードです。
シーン上でShapeがTransformの子になることと、クラスの継承は別の関係です。
単数クラスは1対象、複数形クラスは複数対象を扱います。

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
   target.setMatrix(source.getMatrix(ws=True), ws=True)

.. list-table:: 便利な操作の例
   :header-rows: 1

   * - 対象
     - メソッド
     - 用途
   * - Transform
     - ``getMatrix()`` / ``setMatrix()``
     - マトリクスを取得・反映する
   * - Transform
     - ``addConstraint()`` / ``deleteConstraints()``
     - コンストレイントを作成・削除する
   * - Joint
     - ``freezeRotate()`` / ``jointOrientToRotate()``
     - rotateとjointOrientの間で姿勢を移す
   * - SkinCluster
     - ``getWeights()`` / ``setWeights()``
     - スキンウェイトを取得・反映する
   * - Mesh・NurbsCurve
     - ``mirror()``
     - 指定した軸・空間で頂点またはCVを反転する

同じ操作を複数の対象へ適用する場合は、複数形クラスを使えます。

.. code-block:: python

   transforms = mlib.nodes.Transforms([source, target])
   transforms.setTranslate((0, 5, 0))
   matrices = transforms.getMatrix(ws=True)

一括操作の戻り値と事前検証の範囲は各メソッドの仕様に従います。
操作の一覧と返却型は :mod:`~mlib.nodes` と :doc:`modules` を参照してください。

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

``tx`` と ``translateX`` は同じアトリビュートを指します。
``translate`` のような3成分アトリビュートは ``Double3Plug``、配列アトリビュートは ``ArrayPlug`` など、
アトリビュートの構造に合ったラッパーが選ばれます。

ノードの ``setRotate()`` は姿勢を扱い、``getPlug("rotate").set()`` はrotateアトリビュートの値を扱います。
JointのjointOrientなどがある場合、この2つは同じ操作とは限りません。
Mayaコマンドへ渡すときは ``getFullName()`` で名前へ変換します。値・接続・単位の仕様は
:class:`~mlib.plugs.plug.Plug` と :doc:`getting_started` を参照してください。

マトリクス・クォータニオンを取得して計算する
----------------------------------------------------------------------

取得した値がそのまま数学オブジェクトになるため、配列から型を組み立て直さずに
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

   reference_world = reference.getMatrix(ws=True)
   driven_world = driven.getMatrix(ws=True)
   relative = driven_world * reference_world.inverse()

   restored_world = relative * reference_world
   driven.setMatrix(restored_world, ws=True)

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
   end.setRotate((0, 90, 0), unit="deg")

   q_start = start.getQuaternion(ws=True)
   q_end = end.getQuaternion(ws=True)
   q_middle = q_start.slerp(q_end, 0.5)
   result.setRotate(q_middle, ws=True)

   rotation_matrix = q_middle.asMatrix()

``0.5`` は2つの回転の中間です。Quaternionには角度単位を別途指定しません。
数値で回転を渡す場合は既定がラジアンで、上の例では ``unit="deg"`` を明示しています。
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
