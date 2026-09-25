"""ドライバーと駆動先の関係を取得する。取得だけではキーを作成しない。

Examples
--------
.. code-block:: python

    relation = hlib.drivenKey("ctrl.rotateY", "joint.rotateZ")
    relation.set_key(driver_value=0, value=0)
    relation.set_key(driver_value=90, value=45)
"""


def drivenKey(driver, driven):
    """既存属性の組をDrivenKeyとして取得する。

    Args:
        driver (Plug | str): ドライバー属性。
        driven (Plug | str): 駆動される属性。
    Returns:
        DrivenKey: 未作成の関係も保持できる。set_keyでキーを作成する。
    """
    from ..animation.driven_key import DrivenKey

    return DrivenKey(driver, driven)
