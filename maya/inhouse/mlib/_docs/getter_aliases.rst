取得・判定APIの呼び出し形式
============================

独自の取得メソッドは ``getX()`` に統一します。説明・使用例・Sphinxも同じ表記です。
getを省いた重複入口と取得コマンドの短名ファイルは廃止しました。
数学演算、OpenMaya標準メソッド、判定、保持する値のプロパティはこの統合の対象外です。

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
``getAttr/getPlug/getScene/getChannelBox/getShelf/getTimeSlider/getViewport/getWindow/``
``getWorkspaceControl/getWorkspaceLayout/getOutliner/getDrivenKey`` もget付きの名前で使用します。
``getAttr`` は照会フラグなしならPlug、フラグ指定時はMayaコマンドの照会値を返します。

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
JSONの保存キー・タグはこの統合では変更しません。

複数形と静的取得
------------------

``joints.getSkinClusters()`` 等の専用集約、各対象の結果を保持順に返す取得、
コレクション自身を返す取得の区別は維持します。
``callEach("getTranslate", ...)`` の文字列指定にも正式名を使います。
``Preferences.getLinearUnit()`` 等の静的メソッドもget付きで呼びます。

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

判定は ``isX()`` / ``hasX()`` です。既存の ``valid()/getLocked()/connected()`` 等の
is省略入口は維持しています。取得の統合を理由に新しい判定別名は追加しません。
引数・例外・戻り値は判定本体と同じです。

.. code-block:: python

   node.isValid()
   node.isLocked()
   plug.isConnected(src=True, dst=False)
   plug.isConnectedTo(other.getPlug("translateX"), src=False, dst=True)

OpenMaya継承メソッドと、既存の ``isSource/isElement/isRoot/isType`` 等の標準入口は維持します。
