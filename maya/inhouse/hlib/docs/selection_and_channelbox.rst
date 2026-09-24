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
   saved.restore()

``items()`` は保持した全対象、``plugs()`` は属性参照を返します。
``components()`` はshapeと種類ごとにVertices・Edges・Faces・UVs・CVsにまとめます。
``nodes()`` にコンポーネントの所有ノードは含みません。所有者は ``owners()`` で取得します。

.. code-block:: python

   joints = saved.filter(type="joint")
   vertices = saved.filter(type="vtx")
   joints.add_to_selection()
   joints.remove_from_selection()
   saved.restore(missing="error")

選択変更は各メソッド内でUndoチャンクにまとめます。
``missing="skip"`` が既定値で、削除済みの対象を除外します。
``missing="error"`` は無効な対象があれば、選択を変更する前に例外にします。
空の集合の ``restore()`` は選択解除、追加・除外は何もしません。

明示した対象からも生成できます。

.. code-block:: python

   from hlib.selection import Selection

   selection = Selection(["pCube1", "pCubeShape2.vtx[0:3]"])

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

   channel = hlib.channelBox()
   plugs = channel.selected_plugs()
   nodes = channel.displayed_nodes()
   attributes = channel.selected_attributes()

``selected_plugs()`` は選択属性をPlugとして返します。短縮名やaliasを解決し、
各ノードに存在しない属性と重複を除外します。未選択なら空リストです。
属性値の取得・変更には返されたPlugのメソッドを使います。

``section`` には ``main``、``shape``、``history``、``output``、``all`` を指定できます。
``selected_plugs()`` の既定値は ``all``、
``displayed_nodes()`` と ``selected_attributes()`` の既定値は ``main`` です。
表示ノードはMayaがその欄のobjectListとして返す対象です。

.. code-block:: python

   shape_plugs = channel.selected_plugs(section="shape")
   channel.clear_selection()

``clear_selection()`` は属性のUI選択を解除します。
``hlib.channelBox("既存コントロール名")`` で独自UIも参照できます。
Channel Boxの属性選択とシーンのアクティブ選択は別です。
``captureSelection()`` はChannel Boxの選択属性を取得しません。
