なぜ hlib ?
===========

**hlibは、PyMELのようにMayaのノードをPythonのオブジェクトとして扱うためのライブラリです。**

ノード名の文字列をコマンドへ渡して操作する代わりに、取得したノードオブジェクトから
メソッドを呼び出します。TransformやJointなど、Mayaのノード型に対応するクラスが
操作をまとめるため、対象とその処理を一緒に扱えます。

この考え方をアトリビュートやコンポーネント（頂点・エッジ・フェース・CV・UV）にも広げ、
取得・設定・接続をそれぞれのオブジェクトから行えます。
行列やクォータニオンもオブジェクトとして取得し、そのまま計算へ使えます。
hlibはPyMELに依存せず、独自のAPIを提供します。

.. code-block:: python

   import hlib

   control = hlib.getNode("control")
   control.set_translate((1, 2, 3))
   control.plug("visibility").set(True)
   matrix = control.get_matrix(ws=True)

この例の ``control`` は既存のTransform名です。以下の作成例はMaya内で実行できます。
hlibはMaya標準のコマンド・OpenMayaと併用する基礎ライブラリです。

クラス設計の概要
----------------------------------------------------------------------

役割を「シーン上の対象」と「計算に使う値」に分けています。
ノードやアトリビュートのラッパーはシーンを参照し、数学型は取得した値を保持します。

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
     - Matrix・Quaternion・Vector・EulerRotation
     - シーンから取得した値の計算。計算だけではシーンを変更しない
   * - ``general``
     - Scene・Selection・Color・Viewport
     - シーン・選択・色・UIなど、ノードやアトリビュート以外のMaya共通概念
   * - ``cmds``
     - getNode・createNode・lsなどの関数
     - 対象の取得・作成の入口。通常は ``hlib.getNode()`` のように呼ぶ

ここでいうコンポーネントは、Mayaの形状を構成する要素です。
例えばメッシュの頂点・エッジ・フェースや、カーブのCVを指します。
具体的な操作は :doc:`guide_geometry` を参照してください。

継承によって共通の操作をまとめています。主要な関係は次の通りです。
全クラスの図はページ末尾に掲載しています。

.. code-block:: text

   Node                          Plug
   ├─ DagNode                    ├─ CompoundPlug
   │  ├─ Transform               │  └─ Double3Plug
   │  │  └─ Joint                ├─ ArrayPlug
   │  └─ Shape                   └─ MatrixPlug など
   │     ├─ Mesh
   │     └─ NurbsCurve など       Component
   ├─ SkinCluster                ├─ PointComponent
   ├─ Constraint                 │  ├─ Vertex
   └─ AnimCurve など             │  └─ CV
                                 └─ Edge・Face・UV
   Nodes
   └─ Transforms
      └─ Joints

``Shape`` と ``Transform`` はどちらもDAGノードです。
シーン上でShapeがTransformの子になることと、クラスの継承は別の関係です。
単数クラスは1対象、複数形クラスは複数対象を扱います。

**Mayaへの問い合わせはメソッド、保持する値はプロパティを基本とします。**
例えば ``node.name()`` は現在の名前を問い合わせ、``plug.node`` は保持する所有ノード参照です。
``matrix`` や ``quaternion`` の成分を変更しても、取得元ノードへ自動反映されません。
反映には ``set_matrix()`` や ``set_rotate()`` を明示的に呼びます。

ノード単位で操作する
----------------------------------------------------------------------

``hlib.getNode()`` は実際のノード型に対応したクラスを返します。
JointならJointの操作、SkinClusterならウェイト関連の操作を、その対象から呼べます。

.. code-block:: python

   import hlib

   source = hlib.createNode("transform", name="hlibDemo_source")
   target = hlib.createNode("transform", name="hlibDemo_target")

   source.set_translate((1, 2, 3))
   source.set_scale((2, 2, 2))
   source.set_outliner_color((0.3, 0.7, 1.0))
   target.set_matrix(source.get_matrix(ws=True), ws=True)

.. list-table:: 便利な操作の例
   :header-rows: 1

   * - 対象
     - メソッド
     - 用途
   * - Transform
     - ``get_matrix()`` / ``set_matrix()``
     - 変換行列を取得・反映する
   * - Transform
     - ``add_constraint()`` / ``delete_constraints()``
     - 拘束を作成・削除する
   * - Joint
     - ``freeze_rotation()`` / ``joint_orient_to_rotate()``
     - rotateとjointOrientの間で姿勢を移す
   * - SkinCluster
     - ``get_weights()`` / ``set_weights()``
     - スキンウェイトを取得・反映する
   * - Mesh・NurbsCurve
     - ``mirror()``
     - 指定した軸・空間で頂点またはCVを反転する

同じ操作を複数の対象へ適用する場合は、複数形クラスを使えます。

.. code-block:: python

   transforms = hlib.nodes.Transforms([source, target])
   transforms.set_translate((0, 5, 0))
   matrices = transforms.get_matrix(ws=True)

一括操作の戻り値と事前検証の範囲は各メソッドの仕様に従います。
詳しくは :doc:`guide_nodes` と :doc:`modules` を参照してください。

アトリビュート単位で操作する
----------------------------------------------------------------------

アトリビュートは ``Plug`` オブジェクトとして扱います。ノード名とアトリビュート名を毎回連結する代わりに、
取得したアトリビュートから読み書きや接続を行えます。説明と使用例は ``plug()`` に統一しています。

.. code-block:: python

   # 上の作成例で用意したsourceとtargetを使用
   translate_x = source.plug("tx")
   translate_x.set(10)
   value = translate_x.get()

   source.plug("tx").connect(target.plug("tx"))
   source.plug("tx").disconnect(target.plug("tx"))

   target.plug("visibility").set(False)
   target.plug("visibility").set_flags(locked=True)

``tx`` と ``translateX`` は同じアトリビュートを指します。
``translate`` のような3成分アトリビュートは ``Double3Plug``、配列アトリビュートは ``ArrayPlug`` など、
アトリビュートの構造に合ったラッパーが選ばれます。

ノードの ``set_rotate()`` は姿勢を扱い、``plug("rotate").set()`` はrotateアトリビュートの値を扱います。
JointのjointOrientなどがある場合、この2つは同じ操作とは限りません。
詳しい受付対象は :doc:`cmds_interop` を参照してください。

行列・クォータニオンを取得して計算する
----------------------------------------------------------------------

取得した値がそのまま数学オブジェクトになるため、配列から型を組み立て直さずに
積・逆行列・回転補間などへ進めます。``hlib.maths`` の数学型は
OpenMaya API 2.0の対応する型を継承しています。

行列の合成・逆行列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

次の例は、あるTransformのワールド行列を、基準Transformに対する相対行列へ変換します。
Mayaの行ベクトル規約では、相対行列に基準のワールド行列を右から掛けると元に戻せます。

.. code-block:: python

   import hlib

   reference = hlib.createNode("transform", name="hlibDemo_reference")
   driven = hlib.createNode("transform", name="hlibDemo_driven")
   reference.set_translate((10, 0, 0))
   driven.set_translate((12, 3, 0))

   reference_world = reference.get_matrix(ws=True)
   driven_world = driven.get_matrix(ws=True)
   relative = driven_world * reference_world.inverse()

   restored_world = relative * reference_world
   driven.set_matrix(restored_world, ws=True)

``*`` で行列積、``inverse()`` で逆行列を扱えます。
逆行列を求める例では、ゼロスケールなどの特異な行列を避けてください。
空間・積の順序・親子変換については :doc:`matrices` にまとめています。

クォータニオンの補間
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

回転も ``get_quaternion()`` で取得し、``slerp()`` で補間した結果をそのまま反映できます。

.. code-block:: python

   import hlib

   start = hlib.createNode("transform", name="hlibDemo_start")
   end = hlib.createNode("transform", name="hlibDemo_end")
   result = hlib.createNode("transform", name="hlibDemo_result")
   end.set_rotate((0, 90, 0), unit="deg")

   q_start = start.get_quaternion(ws=True)
   q_end = end.get_quaternion(ws=True)
   q_middle = q_start.slerp(q_end, 0.5)
   result.set_rotate(q_middle, ws=True)

   rotation_matrix = q_middle.to_matrix()

``0.5`` は2つの回転の中間です。Quaternionには角度単位を別途指定しません。
数値で回転を渡す場合は既定がラジアンで、上の例では ``unit="deg"`` を明示しています。
この例は現在の姿勢を計算するもので、アニメーションキーは作成しません。
詳しい演算は :doc:`guide_maths` を参照してください。

ツール開発での使い分け
----------------------------------------------------------------------

* 対象の取得・作成は ``hlib.getNode()`` や ``hlib.createNode()``。
* ノード全体の操作はNode派生、アトリビュートの操作はPlug、形状の一部はComponent。
* 計算はMatrix・Quaternionなどの値で行い、結果の反映は明示的なsetter。
* 通常の編集は各メソッドのUndo対応を利用。複数操作を一つのツールとしてまとめる場合に外側でUndoをまとめる。
* ``fast=True`` があるメソッドは、Undo不要の処理で明示して使う。

Maya標準のコマンドをそのまま使う場面もあります。hlibですべてを置き換える必要はありません。
シーン編集・ファイル操作・UI操作ではUndoの対応範囲が異なるため、各APIの説明を参照してください。

.. include:: _generated/full_class_diagram.rst

図のクラス名から対応するAPIリファレンスへ移動できます。
図はソースから生成され、内部の基底クラスも含みます。通常の利用では、上記の代表クラスから
必要な操作を選び、詳細は :doc:`modules` で確認してください。
