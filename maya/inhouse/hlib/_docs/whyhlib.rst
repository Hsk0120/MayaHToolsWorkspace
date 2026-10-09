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

   control = hlib.node("control")
   control.setTranslate((1, 2, 3))
   control.plug("visibility").set(True)
   matrix = control.matrix(ws=True)

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
     - Matrix・Quaternion・Vector・EulerRotate
     - シーンから取得した値の計算。計算だけではシーンを変更しない
   * - ``common``
     - Scene・Selection・Color・Viewport・Preferences・ScriptJob
     - シーン、表示、作業環境、イベント、汎用処理を浅い共通入口から扱う
   * - ``cmds``
     - node・createNode・lsなどの関数
     - 対象の取得・作成の入口。通常は ``hlib.node()`` のように呼ぶ

ここでいうコンポーネントは、Mayaの形状を構成する要素です。
例えばメッシュの頂点・エッジ・フェースや、カーブのCVを指します。
具体的な操作は :doc:`guide_geometry` を参照してください。

代表クラスだけを抜き出した図です。三角の矢印は基底クラスを指します。
クラス名をクリックするとAPIリファレンスへ移動できます。

ノード：Joint・Mesh・NurbsCurve
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Node
          class DagNode
          class Transform
          class Joint
          class Shape
          class Mesh
          class NurbsCurve
          Node <|-- DagNode
          DagNode <|-- Transform
          Transform <|-- Joint
          DagNode <|-- Shape
          Shape <|-- Mesh
          Shape <|-- NurbsCurve
          click DagNode href "autoapi/hlib/nodes/dagNode/DagNode.html#hlib.nodes.dagNode.DagNode" "hlib.nodes.dagNode.DagNode" _self
          click Joint href "autoapi/hlib/nodes/joint/Joint.html#hlib.nodes.joint.Joint" "hlib.nodes.joint.Joint" _self
          click Mesh href "autoapi/hlib/nodes/mesh/Mesh.html#hlib.nodes.mesh.Mesh" "hlib.nodes.mesh.Mesh" _self
          click Node href "autoapi/hlib/nodes/node/Node.html#hlib.nodes.node.Node" "hlib.nodes.node.Node" _self
          click NurbsCurve href "autoapi/hlib/nodes/nurbsCurve/NurbsCurve.html#hlib.nodes.nurbsCurve.NurbsCurve" "hlib.nodes.nurbsCurve.NurbsCurve" _self
          click Shape href "autoapi/hlib/nodes/shape/Shape.html#hlib.nodes.shape.Shape" "hlib.nodes.shape.Shape" _self
          click Transform href "autoapi/hlib/nodes/transform/Transform.html#hlib.nodes.transform.Transform" "hlib.nodes.transform.Transform" _self
   </pre>

アトリビュート：Plug
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Plug
          class CompoundPlug
          class Double3Plug
          class ArrayPlug
          class MatrixPlug
          Plug <|-- CompoundPlug
          CompoundPlug <|-- Double3Plug
          Plug <|-- ArrayPlug
          Plug <|-- MatrixPlug
          click ArrayPlug href "autoapi/hlib/plugs/arrayPlug/ArrayPlug.html#hlib.plugs.arrayPlug.ArrayPlug" "hlib.plugs.arrayPlug.ArrayPlug" _self
          click CompoundPlug href "autoapi/hlib/plugs/compoundPlug/CompoundPlug.html#hlib.plugs.compoundPlug.CompoundPlug" "hlib.plugs.compoundPlug.CompoundPlug" _self
          click Double3Plug href "autoapi/hlib/plugs/double3Plug/Double3Plug.html#hlib.plugs.double3Plug.Double3Plug" "hlib.plugs.double3Plug.Double3Plug" _self
          click MatrixPlug href "autoapi/hlib/plugs/matrixPlug/MatrixPlug.html#hlib.plugs.matrixPlug.MatrixPlug" "hlib.plugs.matrixPlug.MatrixPlug" _self
          click Plug href "autoapi/hlib/plugs/plug/Plug.html#hlib.plugs.plug.Plug" "hlib.plugs.plug.Plug" _self
   </pre>

コンポーネント：頂点・エッジ・フェース・CV・UV
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Component
          class PointComponent
          class Vertex
          class CV
          class Edge
          class Face
          class UV
          Component <|-- PointComponent
          PointComponent <|-- Vertex
          PointComponent <|-- CV
          Component <|-- Edge
          Component <|-- Face
          Component <|-- UV
          click CV href "autoapi/hlib/components/cv/CV.html#hlib.components.cv.CV" "hlib.components.cv.CV" _self
          click Component href "autoapi/hlib/components/component/Component.html#hlib.components.component.Component" "hlib.components.component.Component" _self
          click Edge href "autoapi/hlib/components/edge/Edge.html#hlib.components.edge.Edge" "hlib.components.edge.Edge" _self
          click Face href "autoapi/hlib/components/face/Face.html#hlib.components.face.Face" "hlib.components.face.Face" _self
          click PointComponent href "autoapi/hlib/components/pointComponent/PointComponent.html#hlib.components.pointComponent.PointComponent" "hlib.components.pointComponent.PointComponent" _self
          click UV href "autoapi/hlib/components/uv/UV.html#hlib.components.uv.UV" "hlib.components.uv.UV" _self
          click Vertex href "autoapi/hlib/components/vertex/Vertex.html#hlib.components.vertex.Vertex" "hlib.components.vertex.Vertex" _self
   </pre>

数学型：行列・回転・ベクトル
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python共通の基底クラス ``object`` から、``maya.api.OpenMaya`` （Python API 2.0）、
hlibの数学型へと継承が続きます。``object`` はPython組み込みのクラスです。
OpenMayaのクラス名はAutodesk公式リファレンス（Maya 2026）、
hlibのクラス名はこのドキュメントのAPIリファレンスへリンクしています。

.. raw:: html

   <pre class="mermaid mermaid-fit">
      classDiagram
          direction TB
          class Matrix
          class Quaternion
          class EulerRotate
          class Vector
          class MMatrix["OpenMaya.MMatrix"]
          class MQuaternion["OpenMaya.MQuaternion"]
          class MEulerRotation["OpenMaya.MEulerRotation"]
          class MVector["OpenMaya.MVector"]
          class object["object（Python組み込み）"]
          object <|-- MMatrix
          object <|-- MQuaternion
          object <|-- MEulerRotation
          object <|-- MVector
          MMatrix <|-- Matrix
          MQuaternion <|-- Quaternion
          MEulerRotation <|-- EulerRotate
          MVector <|-- Vector
          click MMatrix href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_matrix.html" "Autodesk Python API 2.0: MMatrix" _self
          click MQuaternion href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_quaternion.html" "Autodesk Python API 2.0: MQuaternion" _self
          click MEulerRotation href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_euler_rotation.html" "Autodesk Python API 2.0: MEulerRotation" _self
          click MVector href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_vector.html" "Autodesk Python API 2.0: MVector" _self
          click EulerRotate href "autoapi/hlib/maths/eulerRotate/EulerRotate.html#hlib.maths.eulerRotate.EulerRotate" "hlib.maths.eulerRotate.EulerRotate" _self
          click Matrix href "autoapi/hlib/maths/matrix/Matrix.html#hlib.maths.matrix.Matrix" "hlib.maths.matrix.Matrix" _self
          click Quaternion href "autoapi/hlib/maths/quaternion/Quaternion.html#hlib.maths.quaternion.Quaternion" "hlib.maths.quaternion.Quaternion" _self
          click Vector href "autoapi/hlib/maths/vector/Vector.html#hlib.maths.vector.Vector" "hlib.maths.vector.Vector" _self
   </pre>

数学型はそれぞれ対応するOpenMayaの型を直接継承しています。
例えば ``Matrix`` は ``MMatrix`` の派生クラスで、hlibの操作メソッドを追加しています。

``Shape`` と ``Transform`` はどちらもDAGノードです。
シーン上でShapeがTransformの子になることと、クラスの継承は別の関係です。
単数クラスは1対象、複数形クラスは複数対象を扱います。

**Mayaへの問い合わせはメソッド、保持する値はプロパティを基本とします。**
例えば ``node.name()`` は現在の名前を問い合わせ、``plug.node()`` は保持する所有ノード参照です。
``matrix`` や ``quaternion`` の成分を変更しても、取得元ノードへ自動反映されません。
反映には ``setMatrix()`` や ``setRotate()`` を明示的に呼びます。

ノード単位で操作する
----------------------------------------------------------------------

``hlib.node()`` は実際のノード型に対応したクラスを返します。
JointならJointの操作、SkinClusterならウェイト関連の操作を、その対象から呼べます。

.. code-block:: python

   import hlib

   source = hlib.createNode("transform", name="hlibDemo_source")
   target = hlib.createNode("transform", name="hlibDemo_target")

   source.setTranslate((1, 2, 3))
   source.setScale((2, 2, 2))
   source.setOutlinerColor((0.3, 0.7, 1.0))
   target.setMatrix(source.matrix(ws=True), ws=True)

.. list-table:: 便利な操作の例
   :header-rows: 1

   * - 対象
     - メソッド
     - 用途
   * - Transform
     - ``matrix()`` / ``setMatrix()``
     - 変換行列を取得・反映する
   * - Transform
     - ``addConstraint()`` / ``deleteConstraints()``
     - 拘束を作成・削除する
   * - Joint
     - ``freezeRotate()`` / ``jointOrientToRotate()``
     - rotateとjointOrientの間で姿勢を移す
   * - SkinCluster
     - ``weights()`` / ``setWeights()``
     - スキンウェイトを取得・反映する
   * - Mesh・NurbsCurve
     - ``mirror()``
     - 指定した軸・空間で頂点またはCVを反転する

同じ操作を複数の対象へ適用する場合は、複数形クラスを使えます。

.. code-block:: python

   transforms = hlib.nodes.Transforms([source, target])
   transforms.setTranslate((0, 5, 0))
   matrices = transforms.matrix(ws=True)

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

   source.plug("tx").connectTo(target.plug("tx"))
   target.plug("tx").disconnect(source.plug("tx"))

   target.plug("visibility").set(False)
   target.plug("visibility").setFlags(locked=True)

``tx`` と ``translateX`` は同じアトリビュートを指します。
``translate`` のような3成分アトリビュートは ``Double3Plug``、配列アトリビュートは ``ArrayPlug`` など、
アトリビュートの構造に合ったラッパーが選ばれます。

ノードの ``setRotate()`` は姿勢を扱い、``plug("rotate").set()`` はrotateアトリビュートの値を扱います。
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
   reference.setTranslate((10, 0, 0))
   driven.setTranslate((12, 3, 0))

   reference_world = reference.matrix(ws=True)
   driven_world = driven.matrix(ws=True)
   relative = driven_world * reference_world.inverse()

   restored_world = relative * reference_world
   driven.setMatrix(restored_world, ws=True)

``*`` で行列積、``inverse()`` で逆行列を扱えます。
逆行列を求める例では、ゼロスケールなどの特異な行列を避けてください。
空間・積の順序・親子変換については :doc:`matrices` にまとめています。

クォータニオンの補間
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

回転も ``quaternion()`` で取得し、``slerp()`` で補間した結果をそのまま反映できます。

.. code-block:: python

   import hlib

   start = hlib.createNode("transform", name="hlibDemo_start")
   end = hlib.createNode("transform", name="hlibDemo_end")
   result = hlib.createNode("transform", name="hlibDemo_result")
   end.setRotate((0, 90, 0), unit="deg")

   q_start = start.quaternion(ws=True)
   q_end = end.quaternion(ws=True)
   q_middle = q_start.slerp(q_end, 0.5)
   result.setRotate(q_middle, ws=True)

   rotation_matrix = q_middle.asMatrix()

``0.5`` は2つの回転の中間です。Quaternionには角度単位を別途指定しません。
数値で回転を渡す場合は既定がラジアンで、上の例では ``unit="deg"`` を明示しています。
この例は現在の姿勢を計算するもので、アニメーションキーは作成しません。
詳しい演算は :doc:`guide_maths` を参照してください。

ツール開発での使い分け
----------------------------------------------------------------------

* 対象の取得・作成は ``hlib.node()`` や ``hlib.createNode()``。
* ノード全体の操作はNode派生、アトリビュートの操作はPlug、形状の一部はComponent。
* 計算はMatrix・Quaternionなどの値で行い、結果の反映は明示的なsetter。
* 通常の編集は各メソッドのUndo対応を利用。複数操作を一つのツールとしてまとめる場合に外側でUndoをまとめる。
* ``fast=True`` があるメソッドは、Undo不要の処理で明示して使う。

Maya標準のコマンドをそのまま使う場面もあります。hlibですべてを置き換える必要はありません。
シーン編集・ファイル操作・UI操作ではUndoの対応範囲が異なるため、各APIの説明を参照してください。

その他のクラスは :doc:`modules` を参照してください。
