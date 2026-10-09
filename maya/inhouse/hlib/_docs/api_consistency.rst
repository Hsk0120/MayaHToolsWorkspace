命名・戻り型の統一
======================

取得・設定・変換
------------------

hlib独自の取得は ``position()``、設定は ``setPosition()`` のように表記します。
取得本体のget付きメソッドも維持し、説明・使用例・API一覧では省略名を標準にします。
判定の ``is/has``、数学演算、保持値のプロパティ、OpenMaya標準名は維持します。
メソッド内のアトリビュート表記は ``Attr/Attrs``、ユーザー追加分は ``Extra`` です。
廃止した旧名の互換別名はありません。更新後はMayaを再起動するか ``hlib.reload()`` を実行し、
保持していたラッパーと数学値を取得し直してください。

.. list-table:: 主な移行先
   :header-rows: 1

   * - 旧名
     - 現在の呼び出し
   * - ``resetAttributes()`` / ``setAttributeFlags()``
     - ``resetAttrs()`` / ``setAttrFlags()``
   * - ``getExtraAttributes()`` / ``userAttributeNames()``
     - ``extraAttrs()`` / ``extraAttrNames()``
   * - ``moveAttributeOrder()`` / ``attributeCount()``
     - ``moveAttrOrder()`` / ``attrCount()``
   * - ``getT()/setT()``、``getQ()/setQ()``、Transformの ``getX()/setX()``
     - ``translate()/setTranslate()``、``quaternion()/setQuaternion()``、``transformation()/setTransformation()``
   * - PointComponentの ``getX()/setX()``
     - ``positionX()/setPositionX()``。Y/Zも同じ形式。
   * - ``Mesh.getNormals()``
     - ``Mesh.vertexNormals()``。頂点ごとの平均法線を ``list[Vector]`` で返す。
   * - ``Matrix.determinant()`` / ``Matrix.toTransformation()``
     - ``Matrix.det4x4()`` / ``Matrix.asTransformation()``

``getS/setS``、``getSh/setSh``、``getM/setM`` も廃止しました。
``jointOrientQuaternion()`` は旧 ``getJOQ()`` の正式名です。
Plugの ``get()/set()``、成分名そのものを指すUVの ``u()/setU()`` 等は維持します。

引数の長短名
----------------

対応メソッドでは ``idx/index``、``src/source``、``dst/destination``、``attr/attribute``、
``attrs/attributes``、``f/force`` の両名を受け付けます。使用例はショートを基本とします。
元の引数名・位置・既定値は維持し、新しい別名はキーワードで追加しています。
長短の同時指定や、位置引数と別名による二重指定は、同値でも編集前にTypeErrorになります。

.. code-block:: python

   node.resetAttrs(attrs=["tx", "ry"])
   node.resetAttrs(attributes=["tx", "ry"])
   array.element(idx=3, create=True)
   array.element(index=3, create=True)
   calc.connectInput(idx=0, src=source_plug, f=True)

接続方向を表す ``source/destination`` は参照先を渡す引数とは別です。
既存の ``force/f`` のOR評価などは変更していません。OpenMaya継承メソッドの引数に
独自の長短別名を追加することもありません。各メソッドのArgsを参照してください。

数学値のコピーと自身更新
----------------------------

コピー操作は ``inverse/normal/mirror``、自身の更新は ``invertIt/mirrorIt`` の形です。
OpenMaya標準の例外として ``Vector.normalize()`` は自身を更新します。
コピーは新しいhlib値を返し、自身を返す更新メソッドは同じインスタンスを返します。

.. code-block:: python

   from hlib.maths import Quaternion, Vector

   q = Quaternion.fromAxisAngle((0, 1, 0), 0.5)
   inverse = q.inverse()  # qは変更しない
   q.invertIt()          # q自身を更新する
   reflected = q.mirror("x")
   q.mirrorIt("x")
   v = Vector(1, 2, 3)
   unit = v.unit()       # ゼロ値を拒否する正規化コピー
   v.unitIt()            # 同じ検証で自身を更新する

旧 ``normalized()`` は ``unit()``、旧 ``mirrored()`` は ``mirror()``、
従来の自身を更新する ``mirror()`` は ``mirrorIt()`` へ移行してください。
標準の ``normal()`` はOpenMayaのゼロ値処理を維持します。

変換と戻り型
----------------

型変換は ``as`` に統一します。数学値を返す継承メソッドも対応するhlib型を返します。
数値・真偽値・文字列、生API取得入口の ``mplug()/mpath()/mnode()`` と関数セット、
対応するhlib型のないMPoint・単位値・クラス定数は維持します。
``points()/cvPositions()`` のMPointArrayは、点の第4成分を失わないため維持します。

.. list-table:: 演算条件を区別する変換名
   :header-rows: 1

   * - メソッド
     - 動作
   * - ``asMatrix()/asQuaternion()/asEulerRotation()/asAxisAngle()``
     - OpenMaya標準の演算でhlib型を返す。
   * - ``Quaternion.asUnitMatrix()``
     - 旧 ``toMatrix()``。正規化した回転行列。ゼロ四元数は拒否する。
   * - ``Quaternion.asCanonicalAxisAngle()``
     - 旧 ``toAxisAngle()``。正規化し、角度を0〜piへ整える。
   * - ``Quaternion.asDecomposedEulerRotate(order="xyz")``
     - 旧 ``toEuler()``。正規化した行列を指定順序で分解する。
   * - ``Quaternion.asSwingTwist()``
     - 旧 ``toSwingTwist()``。swingとtwistをhlibのQuaternionで返す。

EulerRotateの ``toMatrix()/toQuaternion()`` は ``asMatrix()/asQuaternion()`` です。
JSON用の ``toData()``、OptionVarの ``toDict()`` は ``asData()``、``asDict()`` へ移行します。
保存するキーやデータ形式は変更していません。
