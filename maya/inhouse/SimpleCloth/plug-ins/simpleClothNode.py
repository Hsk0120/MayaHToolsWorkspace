"""Simple ClothのMaya Python API 2.0プラグイン入口。"""

from maya import cmds
from maya.api import OpenMaya as om

from simpleCloth import node


def maya_useNewAPI():
    """MayaへPython API 2.0の使用を通知する。"""


def initializePlugin(plugin):
    """計算ノードと標準Attribute Paint Tool用のマップを登録する。"""
    function = om.MFnPlugin(plugin, "Simple Cloth", "0.1.0", "Any")
    function.registerNode(node.SimpleClothNode.TYPE_NAME, node.SimpleClothNode.TYPE_ID,
                          node.SimpleClothNode.creator, node.SimpleClothNode.initialize)
    cmds.makePaintable(node.SimpleClothNode.TYPE_NAME, "maxDistanceMap", attrType="doubleArray")


def uninitializePlugin(plugin):
    """Mayaの通常手順でノードとペイント登録を解除する。"""
    om.MFnPlugin(plugin).deregisterNode(node.SimpleClothNode.TYPE_ID)
    cmds.makePaintable(node.SimpleClothNode.TYPE_NAME, "maxDistanceMap", remove=True)
