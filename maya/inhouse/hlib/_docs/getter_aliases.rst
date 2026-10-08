get省略の取得入口
==================

getに大文字が続く独自の取得メソッド ``getX()`` は、getを省いた ``x()`` でも呼び出せます。
nodes・plugs・components・commonと公開取得コマンドの全getterが対象です。
正式な処理本体はget付きの入口にあり、省略入口は呼出時の正式getterへ委譲します。
派生クラスのgetterオーバーライドや差し替えも反映します。

.. code-block:: python

   import hlib

   node = hlib.node("pCube1")            # hlib.getNodeと同じ
   plug = node.plug("translateX")       # node.getPlugと同じ
   plug = hlib.attr("pCube1.translateX") # hlib.getAttrと同じ型付きPlug
   value = plug.get()                   # 距離の内部単位cm
   position = node.translation(ws=True) # node.getTranslationと同じ

引数の名前・順序・既定値・位置/キーワード区分・長短フラグ・戻り値・例外・単位は
正式getterと同じです。省略入口は評価・Undo・キャッシュを追加しません。
``Plug.get()`` / ``getu()`` は値取得のままです。数学型のOpenMaya標準名やJSONの標準API、
get付き照会を持たない保持プロパティは変更しません。
ノードからのPlug取得は ``getPlug()`` / ``plug()`` を使います。

同名のアトリビュート
----------------------

省略メソッドは同名のMayaアトリビュートや継承プロパティより優先します。
``joint.radius`` はメソッドです。値は ``joint.radius()``、Plugは
``joint.getPlug("radius")`` で取得します。``transform.matrix()`` も
アトリビュートのPlugではなく、正式 ``getMatrix()`` と同じ値です。
下の ``compound`` は取得済みのCompoundPlugです。

.. code-block:: python

   joint = hlib.node("joint1")
   radius = joint.radius()
   joint.getPlug("radius").set(2.0)

   # CompoundPlugにnodeという子があっても、node()は所有ノードの取得です。
   owner = compound.node()
   child = compound["node"]

複数形と静的getter
-------------------

``joints.skinClusters()`` は ``getSkinClusters()`` の専用集約結果を、
``transforms.transform()`` は ``getTransform()`` と同じコレクション自身を返します。
``callEach("translation", ...)`` 等の文字列指定も正式getterと同じ事前検査・実行を行います。
要素ごとの戻り値を返すcallEachと、専用集約を行うgetterの区別は維持します。

静的getterの省略入口はclassmethodです。``Preferences.linearUnit()`` と
``Preferences().linearUnit()`` は、どちらも ``Preferences.getLinearUnit()`` と同じ照会です。
正式なstaticmethod/classmethodの定義は変更しません。

公開取得コマンド
-----------------

下記の省略名は ``hlib`` と ``hlib.cmds`` の両方から利用できます。
``attr(target)`` は照会フラグなしならPlug、照会フラグを指定した場合は
正式 ``getAttr(target, **kwargs)`` と同じ従来の値・状態を返します。

.. list-table::
   :header-rows: 1

   * - 正式名
     - 省略名
   * - getAttr
     - attr
   * - getChannelBox
     - channelBox
   * - getDrivenKey
     - drivenKey
   * - getNode
     - node
   * - getOutliner
     - outliner
   * - getPlug
     - plug
   * - getScene
     - scene
   * - getShelf
     - shelf
   * - getTimeSlider
     - timeSlider
   * - getViewport
     - viewport
   * - getWindow
     - window
   * - getWorkspaceControl
     - workspaceControl
   * - getWorkspaceLayout
     - workspaceLayout

``hlib.scene()`` は取得関数です。旧 ``import hlib.scene`` パッケージを復活させるものではありません。
正式getterを追加した場合は、省略入口と公開宣言も同時に追加してください。
