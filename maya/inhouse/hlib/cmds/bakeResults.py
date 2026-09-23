"""
Synopsis
--------

.. code-block:: python

    hlib.bakeResults(nodes, **kwargs)

指定したノードのアニメーションをキーフレームへベイクします。

作成・編集操作です。Maya の Undo に対応します。``time=(start, end)`` を
指定しないと Maya の現在の再生範囲が使われます。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`setKeyframe <../setKeyframe/index>` / :doc:`currentTime <../currentTime/index>`

Flags
-----

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | str | Iterable[Node | str]``
     - 必須
     - ベイク対象のノード、またはその列。
   * - ``time (t)``
     - ``tuple[float, float]``
     - 再生範囲
     - ベイクする時間範囲 (start, end)。
   * - ``simulation (sim)``
     - ``bool``
     - True
     - 各フレームを実評価してベイクします。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の bakeResults フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    node = hlib.createNode("transform", name="example")
    hlib.bakeResults(node, time=(1, 24), attribute=["translateX"])
"""

import maya.cmds as cmds


def bakeResults(nodes, **kwargs):
    """指定したノードのアニメーションをキーフレームへベイクする。

    Args:
        nodes (Node | str | Iterable[Node | str]): ベイク対象のノード、またはその列。
        **kwargs (object): maya.cmds.bakeResults に渡すキーワード引数
            （``time=(start, end)`` など）。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: nodes の要素が Node/str 以外の場合。
        ValueError: nodes が空、または要素が空文字列の場合。
        RuntimeError: Maya がベイクを拒否した場合。
    """
    from .._core.coerce import to_names

    names = to_names(nodes)
    if not names:
        raise ValueError("nodes には1つ以上のノードを指定してください")
    cmds.bakeResults(*names, **kwargs)
