シーンと参照ファイル
============================================================

Sceneオブジェクトと参照ファイルの取得・操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

シーンオブジェクトの取得
------------------------

.. code-block:: python

    import hlib

    current = hlib.scene()
    print(current)  # 現在のパス。未保存の場合は untitled
    other = hlib.scene("C:/project/scenes/character.ma")
    print(other)    # パスを表示するだけで、ファイルは開かない
    # other.open() # 明示的に開く場合

Scene は取得時のパスを保持します。現在のシーンの切替・名前変更に自動追従しません。
``new()``、``open()``、``save_as()`` を自身で実行した場合は保持パスも更新します。
``save()``、``save_as()``、``is_modified()`` は現在のシーンとパスが一致する場合のみ
使用できます。未保存シーン同士はパスで区別できません。
クラスの定義先は ``hlib.files.Scene``、名前空間クラスは ``hlib.namespaces.Namespace`` です。

旧 ``hlib.scenes`` / ``hlib.session`` は廃止しました。直接importする場合は次の分類を使います。
``hlib.scene()`` など、コマンドから取得する入口は従来どおりです。

.. code-block:: python

    from hlib.files import Scene, list_references
    from hlib.namespaces import Namespace
    from hlib.plugins import Plugin, Plugins
    from hlib.units import Units, native_units
    from hlib.workspace import Workspace
    from hlib.editors import TimeSlider, Viewport, Outliner

シーン情報
----------

.. code-block:: python

   from hlib.files import Scene

   scene = Scene()
   print(scene.path())  # 未保存なら None
   print(scene.is_modified())

参照(reference)の列挙と操作
-------------------------------

.. code-block:: python

   from hlib.files import list_references

   for reference in list_references():
       print(reference.filename(), reference.namespace(), reference.is_loaded())

   top_level = list_references(top_level_only=True)  # ネストした参照を除外

   reference = list_references()[0]
   reference.unload()
   reference.load()
   print(reference.nodes())  # 参照内のノードをラッパーで取得(アンロード中はRuntimeError)

参照ノード自体は ``hlib.nodes.Reference`` として自動解決されます
(``hlib.node("参照ノード名")`` でも取得可能)。``filename``/``namespace``/
``is_loaded``/``nodes``/``parent_reference`` は ``MFnReference`` 経由の
読み取り専用照会、``load``/``unload``/``remove`` は Undo 対応の編集操作です。
