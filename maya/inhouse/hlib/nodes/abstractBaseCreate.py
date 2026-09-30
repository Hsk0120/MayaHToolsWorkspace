"""Mayaの形状計算ノードに共通する基底型。"""
from .._core.registry import node_wrapper
from .node import Node


@node_wrapper("abstractBaseCreate")
class AbstractBaseCreate(Node):
    """Mayaの形状計算ノードに共通する基底型。"""
