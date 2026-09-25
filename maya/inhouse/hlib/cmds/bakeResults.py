"""
Synopsis
--------

.. code-block:: python

    hlib.bakeResults(nodes, **kwargs)

指定したノードのアニメーションをキーフレームへベイクします。

GUIではベイク中にメインペインを非表示にし、終了・例外時に元の表示状態へ戻します。
バッチ実行では表示操作を行いません。

作成・編集操作です。Maya の Undo に対応します。``time=(start, end)`` を
指定しない場合の範囲はMayaコマンドに委譲します。hlibは再生範囲を補いません。

フラグの詳細は `Maya bakeResultsリファレンス
<https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/bakeResults.html>`_
を参照してください。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`setKeyframe <../setKeyframe/index>` / :doc:`currentTime <../currentTime/index>`

Flags
-----

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

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
     - Mayaの既定動作
     - ベイクする時間範囲 (start, end)。
   * - ``simulation (sm)``
     - ``bool``
     - False
     - Trueでシーン全体を各時刻で評価します。
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

from .._core.flags import flag_aliases

import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from ..decorators.viewport import viewport_off


@flag_aliases("bakeResults")
@undo_chunk("hlib.cmds.bakeResults.bakeResults")
@viewport_off()
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
