"""現在の選択を取得時点のSelectionとして保持する。

Examples
--------
.. code-block:: python

    selection = hlib.captureSelection()
    selection.filter(type="joint").restore()
"""


def captureSelection():
    """Selection: 現在の選択を保持する。Channel Boxの選択属性は含めない。"""
    from ..selection import Selection

    return Selection.capture()
