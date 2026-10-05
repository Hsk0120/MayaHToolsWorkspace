コマンドによるシーン編集
============================================================

選択・複製・グループ化・キー設定など、hlib直下のコマンドを使います。
引数の短縮表記は :doc:`flag_aliases` を参照してください。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

シーン編集コマンド
------------------

.. code-block:: python

   import hlib
   from maya import cmds

   a = hlib.createNode("transform", name="a")
   b = hlib.createNode("transform", name="b")

   print(cmds.objExists(a))          # True
   copy = hlib.duplicate(a, name="aCopy")
   parent = hlib.createGroup([a, b], name="grp")
   empty = hlib.createGroup(name="emptyGrp", empty=True)

   hlib.delete(copy)

対象の引数には名前の文字列のほか、Node・Plug・Vertex などのコンポーネント、
Vertices などのコレクション、Selection、Maya API 2.0 の MObject・MDagPath・MPlug と
それらのリストを指定できます。変換の規則と、hlib のオブジェクトを ``maya.cmds`` へ
そのまま渡す場合の仕様は :doc:`cmds_interop` を参照してください。

``duplicate``/``group`` はいずれも作成したノードのラッパーを返します。
``createNode``/``group`` の ``parent`` は所有ノードへ解決します(Plug を渡すとその
ノードが親になります)。``group`` に空のリストを渡すと、現在の選択をグループ化せずに
``ValueError`` になります。
``group`` は ``nodes`` を省略すると ``maya.cmds.group`` と同じく現在の選択を
グループ化します。空のグループを作る場合は ``empty=True`` を指定してください
（選択も無く ``empty`` も指定しない場合は Maya がエラーを送出します）。
``delete`` は複数ノードもまとめて受け付けます。Plug(アトリビュート)を渡すと ``TypeError`` です
(``maya.cmds.delete`` はアトリビュートを削除せず何もしないため)。動的アトリビュートの削除は
``plug.delete()``、所有ノードの削除は ``hlib.delete(plug.node())`` を使ってください。

選択とアニメーション
--------------------

.. code-block:: python

   import hlib
   from maya import cmds

   a = hlib.createNode("transform", name="animationA")
   b = hlib.createNode("transform", name="animationB")

   hlib.select([a, b])
   print(hlib.ls(selection=True))
   hlib.select(clear=True)

   cmds.currentTime(1)
   cmds.setKeyframe(a.plug("translateX"), value=0.0)
   cmds.currentTime(24)
   cmds.setKeyframe(a.plug("translateX"), value=10.0)

   hlib.bakeResults(a, time=(1, 24), attribute=["translateX"], simulation=True)

``select`` は ``maya.cmds.select`` と同じ引数を受け付けます。``nodes`` を省略すると
``clear=True`` のような選択操作専用のフラグだけで呼び出せます。
時刻やキー操作は ``maya.cmds`` を使用します。現在時刻の照会は
``cmds.currentTime(query=True)`` と明示します。
``bakeResults`` は時間範囲を補いません。``time=(start, end)`` を明示してください。
``simulation`` の既定値はFalseです。シーン全体の評価が必要ならTrueを指定します。
GUIではベイク中のメインペインを非表示にし、終了時に元の状態へ戻します。

アトリビュートの取得・設定・接続（``getAttr``/``setAttr``/``connectAttr``/``addAttr``）は
コマンドとしては用意していません。``node.plug("attrName")`` が返す ``Plug`` の
``get()``/``set()``/``connectTo()``、および ``node.addAttr()`` を使ってください。
``Plug`` は ``maya.cmds.getAttr(plug)`` のように maya.cmds へそのまま渡すこともできます
（:doc:`cmds_interop`）。

ノードのアトリビュートは、:meth:`~hlib.nodes.node.Node.plug` で取得した
:class:`~hlib.plugs.plug.Plug` オブジェクトを通して操作します。
本ドキュメントの使用例は ``plug()`` に統一しています。
アトリビュート取得は ``plug()`` に統一しています。

コマンドの命名と役割
--------------------

ファイル名と関数名を動詞+対象へ統一しています。``ls`` は一覧取得の慣用名として維持します。
旧名の互換入口はありません。

.. list-table::
   :header-rows: 1

   * - 旧名
     - 現在の名前
   * - ``constraint``
     - ``addConstraint``
   * - ``curve``
     - ``createCurve``
   * - ``ikHandle``
     - ``createIkHandle``
   * - ``sets``
     - ``createSet``
   * - ``group``
     - ``createGroup``
   * - ``node``
     - ``getNode``
   * - ``plug``
     - ``getPlug``
   * - ``scene``
     - ``getScene``
   * - ``channelBox``
     - ``getChannelBox``
   * - ``outliner``
     - ``getOutliner``
   * - ``timeSlider``
     - ``getTimeSlider``
   * - ``viewport``
     - ``getViewport``
   * - ``drivenKey``
     - ``getDrivenKey``

``create`` / ``add`` は生成・追加専用です。拘束の照会は
``constraint.targets()`` / ``constraint.weightPlugs()``、編集は
``constraint.setWeight()`` を使います。セットは
``object_set.members()`` / ``add()`` / ``remove()`` を使います。
``getDrivenKey`` は関係取得のみで、キーの生成は ``setKey()`` です。
