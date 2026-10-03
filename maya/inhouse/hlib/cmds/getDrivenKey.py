"""ドライバーと駆動先の関係を取得する。取得だけではキーを作成しない。

Examples
--------
.. code-block:: python

    relation = hlib.getDrivenKey("ctrl.rotateY", "joint.rotateZ")
    relation.setKey(driver_value=0, value=0)
    relation.setKey(driver_value=90, value=45)
"""


def getDrivenKey(driver, driven):
    """既存アトリビュートの組をDrivenKeyとして取得する。

    Args:
        driver (Plug | om2.MPlug | str): ドライバーアトリビュート。文字列は ``"node.attribute"`` 形式。
        driven (Plug | om2.MPlug | str): 駆動されるアトリビュート。
    Returns:
        DrivenKey: 未作成の関係も保持できる。set_keyでキーを作成する。
    """
    from hlib.scene.drivenKey import DrivenKey

    return DrivenKey(driver, driven)
