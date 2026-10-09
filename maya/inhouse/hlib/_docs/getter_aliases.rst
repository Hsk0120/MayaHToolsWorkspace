取得・判定APIの呼び出し形式
============================

説明・使用例・APIリファレンスでは、独自の取得メソッドを ``x()`` の形式で記載します。
getに大文字が続く本体 ``getX()`` も同じ引数・戻り値で利用できます。
nodes・plugs・components・commonと公開取得コマンドの全getterが対象です。
正式な処理本体はget付きの入口にあり、省略入口は呼出時の正式getterへ委譲します。
派生クラスのgetterオーバーライドや差し替えも反映します。

.. code-block:: python

   import hlib

   node = hlib.node("pCube1")            # ノードの型に対応するラッパー
   plug = node.plug("translateX")       # ノードからアトリビュートを取得
   plug = hlib.attr("pCube1.translateX") # アトリビュート名から型付きPlugを取得
   value = plug.get()                   # 距離の内部単位cm
   position = node.translate(ws=True) # ワールド空間の位置

引数の名前・順序・既定値・位置/キーワード区分・長短フラグ・戻り値・例外・単位は
正式getterと同じです。省略入口は評価・Undo・キャッシュを追加しません。
``Plug.get()`` / ``getu()`` は値取得のままです。数学型のOpenMaya標準名やJSONの標準API、
get付き照会を持たない保持プロパティは変更しません。
ノードからのPlug取得は ``plug()`` を使います。
省略名のAPIページには本体の引数と説明を掲載し、get付きの参照リンクも省略名へ解決します。

変換チャンネルの名前
--------------------

移動・回転・スケールの取得名は、Mayaのチャンネル名に揃えます。
正式な取得・設定メソッドは ``getTranslate/setTranslate``、``getRotate/setRotate``、
``getScale/setScale``、取得の省略入口は ``translate()/rotate()/scale()`` です。
引数、単位、Undo、``safe/get/fast`` の意味は従来と同じです。

.. code-block:: python

   node = hlib.node("pCube1")
   position = node.translate(ws=True, at=4)
   rotation = node.rotate()
   scale = node.scale()
   node.setTranslate((1, 2, 3), at=4)
   node.setRotate((0.0, 0.0, 0.0))
   node.setScale((1, 1, 1))

   # チャンネルのPlugは明示して取得します。
   translate_plug = node.plug("translate")
   rotate_plug = node.plug("rotate")
   scale_plug = node.plug("scale")

数学型は ``Translate``・``EulerRotate``・``Scale`` です。
旧名の ``Translation``・``EulerRotation`` や旧メソッドは公開しません。
OpenMaya標準の ``MEulerRotation``、``Quaternion.asEulerRotation()``、
Maya標準アトリビュート名に対応する ``useEulerRotation()`` は維持します。
Quaternionからの変換は ``asEulerRotate()`` でも呼び出せます。
JSONの ``math:Translation``・``math:EulerRotation`` の保存タグは従来のままです。
改名前のPython pickleは旧クラスのimport先に依存するため、新しいAPIでは読み込めません。

同名のアトリビュート
----------------------

省略メソッドは同名のMayaアトリビュートや継承プロパティより優先します。
``joint.radius`` はメソッドです。値は ``joint.radius()``、Plugは
``joint.plug("radius")`` で取得します。``transform.matrix()`` は行列の値を取得します。
下の ``compound`` は取得済みのCompoundPlugです。

.. code-block:: python

   joint = hlib.node("joint1")
   radius = joint.radius()
   joint.plug("radius").set(2.0)

   # CompoundPlugにnodeという子があっても、node()は所有ノードの取得です。
   owner = compound.node()
   child = compound["node"]

複数形と静的getter
-------------------

``joints.skinClusters()`` はスキンクラスターを集約した結果を、
``transforms.transform()`` はコレクション自身を返します。
``callEach("translate", ...)`` 等の文字列指定も正式getterと同じ事前検査・実行を行います。
要素ごとの戻り値を返すcallEachと、専用集約を行うgetterの区別は維持します。

静的getterの省略入口はclassmethodです。``Preferences.linearUnit()`` と
``Preferences().linearUnit()`` は、どちらも距離のUI単位を照会します。
正式なstaticmethod/classmethodの定義は変更しません。

公開取得コマンド
-----------------

下記13関数は ``hlib.cmds`` と ``hlib`` の両方から利用できます。
ルートの同名関数は同じ関数オブジェクトの再公開です。
例えば ``hlib.cmds.node is hlib.node`` はTrueになります。
省略関数は呼び出すたびにget付きの処理本体へ委譲し、引数・戻り値・例外を保持します。
``attr(target)`` は照会フラグなしならPlug、照会フラグを指定した場合は
従来のMaya照会値・状態を返します。

.. list-table::
   :header-rows: 1

   * - hlib.cmdsの省略関数
     - 処理本体の名前
   * - ``hlib.cmds.attr()``
     - getAttr
   * - ``hlib.cmds.channelBox()``
     - getChannelBox
   * - ``hlib.cmds.drivenKey()``
     - getDrivenKey
   * - ``hlib.cmds.node()``
     - getNode
   * - ``hlib.cmds.outliner()``
     - getOutliner
   * - ``hlib.cmds.plug()``
     - getPlug
   * - ``hlib.cmds.scene()``
     - getScene
   * - ``hlib.cmds.shelf()``
     - getShelf
   * - ``hlib.cmds.timeSlider()``
     - getTimeSlider
   * - ``hlib.cmds.viewport()``
     - getViewport
   * - ``hlib.cmds.window()``
     - getWindow
   * - ``hlib.cmds.workspaceControl()``
     - getWorkspaceControl
   * - ``hlib.cmds.workspaceLayout()``
     - getWorkspaceLayout

.. code-block:: python

   import hlib

   node = hlib.cmds.node("pCube1")
   plug = hlib.cmds.plug("pCube1.translateX")
   attr = hlib.cmds.attr(plug)       # フラグなしは型付きPlug
   value = attr.get()              # 距離の内部単位cm
   scene = hlib.cmds.scene()       # 現在のシーンパスを保持するScene

   assert hlib.cmds.node is hlib.node
   assert attr is plug

``hlib.scene()`` は取得関数です。旧 ``import hlib.scene`` パッケージを復活させるものではありません。
正式getterを追加した場合は、省略入口と公開宣言も同時に追加してください。

判定メソッド
------------

``isX()`` の判定には、isを省いた ``x()`` の入口も用意します。
説明・使用例・APIリファレンスでは省略名を使い、処理本体はis付きに残します。
引数・既定値・フラグ・例外・戻り値は本体と同じで、呼出し時のoverrideにも追従します。
複数形は従来どおり、保持順の判定結果リストを返します。

.. code-block:: python

   node = hlib.node("pCube1")
   other = hlib.node("pCube2")
   print(node.valid(), node.locked())
   plug = node.plug("translateX")
   print(plug.keyable())
   print(plug.connected(src=True, dst=False))
   print(plug.connectedTo(other.plug("translateX"), src=False, dst=True))
   print(hlib.nodes.Nodes([node]).valid())

   from hlib.common import undo
   print(undo.enabled())

省略名はメソッドです。``node.locked`` ではなく ``node.locked()`` として判定します。
``Vector``・``Matrix``・``EulerRotate``・``Transformation`` に定義した
``isEquivalent()`` にも ``equivalent()`` を用意します。
OpenMayaからそのまま継承する ``isParallel()`` や
``Quaternion.isEquivalent()`` などは、標準の名前を使います。

既存名と重なる判定
~~~~~~~~~~~~~~~~~~

省略名が既存の取得・編集APIと重なる判定は、is付きの名前を使います。
``source()`` で接続元Plugを取得するなど、既存APIの意味と戻り値を維持するためです。

.. list-table::
   :header-rows: 1

   * - 判定名
     - 既存の省略名・操作
   * - ``Node.isType()`` / ``Nodes.isType()``
     - ``type()`` はノード型名を取得
   * - ``Node.isRoot()`` / ``Nodes.isRoot()``
     - 派生クラスの ``root()`` はルートの参照を取得
   * - ``Plug.isSource()``
     - ``source()`` は接続元Plugを取得
   * - ``Plug.isElement()``
     - ``ArrayPlug.element(index)`` は配列要素Plugを取得
   * - ``Plugin.isLoaded()``
     - ``Plugin.loaded()`` はロード済みプラグイン一覧を取得
   * - ``Scene.isNew()``
     - ``new()`` は新規シーンを作成
   * - ``WorkspaceLayout.isCurrent()``
     - ``WorkspaceLayout.current()`` は現在のレイアウトを取得

``Reference.loaded()`` と ``Scene.current()`` は、それぞれのクラスでは
同名の取得・編集APIと重ならないため、判定の省略入口として利用できます。
