"""現在の選択を取得時点のSelectionとして保持する。

Examples
--------
.. code-block:: python

    selection = hlib.captureSelection()
    selection.filter(type="joint").select()
"""


def captureSelection():
    """Selection: 現在の選択を保持する。Channel Boxの選択アトリビュートは含めない。"""
    from ..general.selection import Selection

    return Selection.capture()
