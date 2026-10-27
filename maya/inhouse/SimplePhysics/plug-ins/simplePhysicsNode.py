"""Simple PhysicsのMaya Python API 2.0プラグイン入口。"""

from maya.api import OpenMaya as om

from simplePhysics import node


def maya_useNewAPI():
    """MayaへPython API 2.0を使用することを通知する。"""


def initializePlugin(plugin):
    """計算ノードを明示的なロード時に登録する。"""
    function = om.MFnPlugin(plugin, "Simple Physics", "0.1.0", "Any")
    function.registerNode(node.SimplePhysicsNode.TYPE_NAME, node.SimplePhysicsNode.TYPE_ID,
                          node.SimplePhysicsNode.creator, node.SimplePhysicsNode.initialize)


def uninitializePlugin(plugin):
    """Mayaの通常のアンロード手順でノード登録を解除する。"""
    om.MFnPlugin(plugin).deregisterNode(node.SimplePhysicsNode.TYPE_ID)
