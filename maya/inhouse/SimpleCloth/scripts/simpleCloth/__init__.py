"""Simple Cloth: Maya向けの独立XPBD布ツール。"""

from .api import (addCollider, bake, create, getColliders, getConnection, getMap,
                  loadPlugin, loadPreset, paintMap, remove, removeCollider, reset,
                  savePreset, setMap, setVertexWeights)


def show():
    """Maya GUIでSimple Clothの設定画面を開く。"""
    # バッチでの計算・テスト時にはUIモジュールを読み込まない。
    from . import ui
    return ui.show()


__all__ = ["addCollider", "bake", "create", "getColliders", "getConnection", "getMap",
           "loadPlugin", "loadPreset", "paintMap", "remove", "removeCollider", "reset",
           "savePreset", "setMap", "setVertexWeights", "show"]
