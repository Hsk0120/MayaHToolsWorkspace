"""現在のタイムラインを操作する TimeSlider を取得する。

Examples
--------
.. code-block:: python

    slider = hlib.timeSlider()
    print(slider.playback_range())
    with slider.preserve_time():
        slider.set_current_time(10)
"""


def timeSlider(control=None):
    """TimeSliderを取得する。生成だけでは時刻やUIを変更しない。

    Args:
        control (str | None): timeControl名。省略時はメインタイムスライダー。

    Returns:
        TimeSlider: 現在のタイムラインを操作するオブジェクト。
    """
    from ..scenes import TimeSlider

    return TimeSlider(control)
