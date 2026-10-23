取得・判定APIの呼び出し形式
============================

独自の取得メソッドは ``getX()`` に統一します。説明・使用例・Sphinxも同じ表記です。
getを省いた重複入口と取得コマンドの短名ファイルは廃止しました。
数学演算、OpenMaya標準メソッド、保持する値のプロパティはこの統合の対象外です。
判定メソッドの呼び出し形式は下記を参照してください。

.. code-block:: python

   import mlib

   node = mlib.getNode("pCube1")
   plug = node.getPlug("translateX")
   value = plug.get()                         # cm/rad/秒
   ui_value = plug.get(uiUnits=True)           # 現在のUI単位の数値
   position = node.getTranslate(ws=True, at=4)
   node.setTranslate((1, 2, 3), at=4)
   node.setRotate((0.0, 0.0, 0.0))

``mlib.getNode`` と ``mlib.cmds.getNode`` は同じ公開関数です。
``getPlug`` も同じくルートと ``mlib.cmds`` で公開します。
公開コマンドは ``getNode/getPlug/createNode/ls/delete/duplicate/select`` の7入口です。
参照は ``getPlug``、値は ``Plug.get``、状態は ``isLocked`` 等の専用メソッドで取得します。
特定時刻の照会などは ``maya.cmds.getAttr`` を直接使います。

アトリビュートと値の区別
------------------------

``node.getMatrix()`` は数学値、``node.getPlug("matrix")`` はPlugを返します。
取得の省略メソッドを取り除いたため、``node.matrix`` などのMayaアトリビュート名を
直接解決できます。Mayaへ問い合わせるメソッドは括弧を付けて呼びます。

.. code-block:: python

   matrix = node.getMatrix()
   matrix_plug = node.getPlug("matrix")
   radius = joint.getRadius()
   joint.getPlug("radius").set(2.0)
   vertex = mesh.getVertex(idx=0)
   cvs = curve.getCVs()

``Component.index``、``Components.indices``、数学型の ``Matrix.translate`` 等は保持値の
プロパティです。``MMatrix.getElement``、``MVector.length`` 等の標準名も維持します。
変換の値型は ``Translate/EulerRotate/Scale``、取得・設定は
``getTranslate/setTranslate``・``getRotate/setRotate``・``getScale/setScale`` です。

複数形と静的取得
------------------

``joints.getSkinClusters()`` 等の専用集約、各対象の結果を保持順に返す取得、
コレクション自身を返す取得の区別は維持します。
``callEach("getTranslate", ...)`` の文字列指定にも正式名を使います。
``Namespace.getCurrent()`` 等のクラスメソッドもget付きで呼びます。
現在のUI単位を調べる場合は ``maya.cmds.currentUnit(query=True, linear=True)`` 等を直接使います。

接続・単位・階層
------------------

``plug.getSource()`` は既定で変換ノードを飛ばし、
``getSource(skipConversionNodes=False)`` は直結元を返します。
出力側は ``getDestinations`` です。両方向は ``getConnections`` に集約しました。
値のUI単位は ``get(uiUnits=True)`` / ``set(value, uiUnits=True)`` で指定します。
UI単位を選択した複合値は数値tupleとし、内部単位の数学型へUI数値を入れません。

``getShapes()`` はShape取得、``getChildren()`` は子・子孫取得です。
子孫・探索順・末端は ``allDescendents/order/leaves/includeSelf`` で選択します。
詳細は :doc:`api_methods` と :doc:`api_arguments` を参照してください。

判定メソッド
--------------

判定は ``isX()`` / ``hasX()`` です。独自のis省略入口は廃止し、正式名へ統一しました。
旧名の互換別名は提供しません。正式メソッドの引数・例外・戻り値は維持します。
Undoの有効状態も ``mlib.common.undo.isEnabled()`` で照会します。

.. code-block:: python

   node.isValid()
   node.isLocked()
   plug.isConnected(src=True, dst=False)
   plug.isConnectedTo(other.getPlug("translateX"), src=False, dst=True)

OpenMaya継承メソッドと、既存の ``isSource/isElement/isRoot/isType`` 等の標準入口は維持します。
