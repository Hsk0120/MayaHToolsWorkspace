"""
Synopsis
--------

.. code-block:: python

    hlib.select(nodes=None, **kwargs)

指定したノード・アトリビュート・コンポーネントを選択します。``nodes`` を省略すると
``**kwargs`` だけで ``maya.cmds.select`` を呼びます（``clear=True`` など）。
``nodes`` には Node・Plug・Component に加えて Vertices などのコレクション、
Selection、Maya API 2.0 の MObject・MDagPath・MPlug、およびそれらのリストを
指定できます。Vertices などのコレクションは連続する番号を範囲指定(``vtx[0:99]``)に
まとめて渡すため、要素数が多くても高速です。対応する型は :doc:`/cmds_interop` を参照してください。

選択状態を変更する操作です。Maya の Undo に対応します。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`ls <../ls/index>`

Flags
-----

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | Plug | Component | Components | Selection | str | MObject | MDagPath | MPlug | Iterable | None``
     - None
     - 選択する対象、またはその列。None は kwargs だけで maya.cmds.select を呼ぶ。空の列は ``maya.cmds.select([])`` と同じ。
   * - ``replace (r)``
     - ``bool``
     - True
     - 既存の選択を置き換えます（Maya の既定動作）。
   * - ``add (add)``
     - ``bool``
     - False
     - 既存の選択に追加します。
   * - ``clear (cl)``
     - ``bool``
     - False
     - 選択を解除します（nodes と併用不可）。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の select フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    a = hlib.createNode("transform", name="a")
    b = hlib.createNode("transform", name="b")
    hlib.select([a, b])
    print(hlib.ls(selection=True))
    hlib.select(clear=True)
"""

from ..decorators.undo import undo_chunk

from .._core.flags import flag_aliases

import maya.cmds as cmds


@flag_aliases("select")
@undo_chunk("hlib.cmds.select.select")
def select(nodes=None, **kwargs):
    """指定したノード・アトリビュート・コンポーネントを選択する。

    Args:
        nodes (Node | Plug | Component | Components | Selection | str | om2.MObject | om2.MDagPath | om2.MPlug | Iterable | None):
            選択する対象、またはその列(入れ子のコレクションも展開する)。
            None は kwargs だけで maya.cmds.select を呼ぶ（clear=True など）。
            空の列は maya.cmds.select([]) と同じく扱う。
        **kwargs (object): maya.cmds.select に渡すキーワード引数。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: nodes の要素が対応しない型の場合。
        ValueError: nodes の要素に空文字列、または削除済みの対象が含まれる場合。
        RuntimeError: Maya が選択を拒否した場合。
    """
    from hlib.object import Object as _InputObject

    if nodes is None:
        cmds.select(**kwargs)
        return
    names = _InputObject._input_names(nodes)
    cmds.select(names, **kwargs)
