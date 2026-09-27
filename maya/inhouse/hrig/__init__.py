"""Maya向けモジュラーリギングパッケージ。

リグ構築機能を追加するためのパッケージ入口です。
"""
from .definition import JointSpec, LayerSpec, RigDefinition, limb_definition


def build_limb(definition=None, backend='bifrost'):
    """Maya/Bifrostを必要な時点で読み込み、最小リグを構築する。
    
    Args:
        definition (RigDefinition | None): 省略時は検証用の3関節定義。
        backend (str): bifrostまたはcpp。既定はbifrost。
    

    Returns:
        LimbRig: 構築した部位の操作用参照。
    """
    from .limb import build_limb as build
    return build(definition, backend=backend)
