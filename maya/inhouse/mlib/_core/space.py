"""オブジェクトAPIのワールド空間指定を検証する。"""


def world_space(value):
    """boolの空間指定を検証する。

    Args:
        value (bool): Trueはワールド空間、Falseはローカル空間。

    Returns:
        bool: 検証済みの指定。

    Raises:
        ValueError: bool以外を指定した場合。
    """
    if type(value) is not bool:
        raise ValueError("worldSpace (ws) must be a bool")
    return value
