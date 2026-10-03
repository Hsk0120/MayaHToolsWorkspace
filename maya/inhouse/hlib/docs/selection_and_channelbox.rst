選択の保存とChannel Box
=======================

Selection
---------

``hlib.captureSelection()`` は取得時点の選択を保持します。
後からMayaの選択を変更しても、保持内容は変わりません。

.. code-block:: python

   import hlib

   saved = hlib.captureSelection()
   nodes = saved.nodes()
   joints = saved.nodes(type="joint")
   components = saved.components()
   owners = saved.owners()

   # 別の処理で選択を変更したあと、元の対象を再選択
   saved.select()

``items()`` は保持した全対象、``plugs()`` はアトリビュート参照を返します。
``components()`` はshapeと種類ごとにVertices・Edges・Faces・UVs・CVsにまとめます。
``nodes()`` にコンポーネントの所有ノードは含みません。所有者は ``owners()`` で取得します。

.. code-block:: python

   joints = saved.filter(type="joint")
   vertices = saved.filter(type="vtx")
   joints.select(mode="add")
   joints.select(mode="remove")
   saved.select(missing="error")

選択変更は各メソッド内でUndoチャンクにまとめます。
``missing="skip"`` が既定値で、削除済みの対象を除外します。
``missing="error"`` は無効な対象があれば、選択を変更する前に例外にします。
空の集合の ``select(mode="replace")`` は選択解除、追加・除外は何もしません。

明示した対象からも生成できます。

.. code-block:: python

   from hlib.scene.selection import Selection

   selection = Selection(["pCube1", "pCubeShape2.vtx[0:3]"])

名前の文字列のほか、Node・Plug・コンポーネント・Vertices などのコレクション・
Selection と、Maya API 2.0 の MObject・MDagPath・MPlug・MSelectionList も指定できます。
Selection は反復可能なので、``cmds.select(selection)`` や ``hlib.select(selection)`` のように
そのまま渡すと各要素の名前に展開されます(:doc:`cmds_interop`)。
削除済みの要素を含む場合は ``select()`` を使ってください。

ノードの名前変更とDAGインスタンスのパスを追跡します。
順序はMayaのアクティブ選択リストの順で、クリック順を保証するものではありません。
頂点・エッジ・フェース・UV・NURBSカーブCVに対応し、それ以外の
コンポーネントはTypeErrorになります。トポロジー変更後の番号や、UVセット変更後の
UVの同一性は保証しません。``items()`` と ``len()`` には削除済み参照も残ります。

ChannelBox
----------

既存のChannel Boxを参照します。GUIのない環境やUIが存在しない場合は
RuntimeErrorになります。新しいUIは生成しません。

.. code-block:: python

   import hlib

   channel = hlib.getChannelBox()
   plugs = channel.selectedPlugs()
   nodes = channel.displayedNodes()
   attributes = channel.selectedAttributes()

``selectedPlugs()`` は選択アトリビュートをPlugとして返します。短縮名やaliasを解決し、
各ノードに存在しないアトリビュートと重複を除外します。未選択なら空リストです。
アトリビュート値の取得・変更には返されたPlugのメソッドを使います。

``section`` には ``main``、``shape``、``history``、``output``、``all`` を指定できます。
``selectedPlugs()`` の既定値は ``all``、
``displayedNodes()`` と ``selectedAttributes()`` の既定値は ``main`` です。
表示ノードはMayaがその欄のobjectListとして返す対象です。

.. code-block:: python

   shape_plugs = channel.selectedPlugs(section="shape")
   channel.clearSelection()

``clearSelection()`` はアトリビュートのUI選択を解除します。
``hlib.getChannelBox("既存コントロール名")`` で独自UIも参照できます。
Channel Boxのアトリビュート選択とシーンのアクティブ選択は別です。
``captureSelection()`` はChannel Boxの選択アトリビュートを取得しません。
