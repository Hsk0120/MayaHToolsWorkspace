"""Skin Weight Kit(右端に縦に置くスキンのウェイト作業用のパネル)の表示・非表示を切り替える。

本体は maya/inhouse/SkinWeightKit のパッケージ(skinWeightKit)。このファイルはHToolsのメニューから開くための入口だけ。
"""

import skinWeightKit

if __name__ == "__main__":
    skinWeightKit.toggle()
