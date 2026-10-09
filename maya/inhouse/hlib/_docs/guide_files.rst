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

``isNew()`` は保持パスがNoneかを判定し、``repr(scene)`` も保持パスを表示します。
Scene は取得時のパスを保持します。現在のシーンの切替・名前変更に自動追従しません。
``new()``、``open()``、``saveAs()`` を自身で実行した場合は保持パスも更新します。
``save()``、``saveAs()``、``modified()`` は現在のシーンとパスが一致する場合のみ
使用できます。未保存シーン同士はパスで区別できません。
クラスの定義先は ``hlib.common.Scene``、名前空間クラスは ``hlib.common.Namespace`` です。

直接importする場合は ``hlib.common`` を使います。
``hlib.scene()`` など、コマンドから取得する入口は従来どおりです。

.. code-block:: python

    from hlib.common import Scene, Namespace, Plugin, Preferences, Workspace
    from hlib.common import TimeSlider, Viewport, Outliner
    from hlib.common.references import listReferences

シーン情報
----------

.. code-block:: python

   from hlib.common import Scene

   scene = Scene()
   print(scene.path)  # 未保存なら None
   print(scene.modified())

参照(reference)の列挙と操作
-------------------------------

.. code-block:: python

   from hlib.common.references import listReferences

   for reference in listReferences():
       print(reference.filename(), reference.associatedNamespace(), reference.loaded())

   top_level = listReferences(top_level_only=True)  # ネストした参照を除外

   reference = listReferences()[0]
   reference.unload()
   reference.load()
   print(reference.nodes())  # 参照内のノードをラッパーで取得(アンロード中はRuntimeError)

参照ノード自体は ``hlib.nodes.Reference`` として自動解決されます
(``hlib.node("参照ノード名")`` でも取得可能)。``filename``/``namespace``/
``loaded``/``nodes``/``parentReference`` は ``MFnReference`` 経由の
読み取り専用照会、``load``/``unload``/``remove`` は Undo 対応の編集操作です。
