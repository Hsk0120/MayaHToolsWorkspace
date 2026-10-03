"""オブジェクトAPIのMSpace指定を検証する。"""
from maya.api.OpenMaya import MSpace


def world_space(space):
    """対応する空間を検証し、ワールド空間かを返す。

    Args:
        space (int): MSpace.kObject/kTransform/kWorld。

    Returns:
        bool: kWorldならTrue。kObject/kTransformはローカル空間。

    Raises:
        ValueError: boolまたは対応外の空間の場合。
    """
    if type(space) is not int or space not in (MSpace.kObject, MSpace.kTransform, MSpace.kWorld):
        raise ValueError("space must be MSpace.kObject, kTransform, or kWorld")
    return space == MSpace.kWorld
