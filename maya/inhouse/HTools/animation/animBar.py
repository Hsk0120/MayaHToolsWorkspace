"""Anim Bar(タイムスライダーの上に置くアニメーション作業用のツールバー)の表示・非表示を切り替える。

本体は maya/inhouse/AnimBar のパッケージ(animBar)。このファイルはHToolsのメニューから開くための入口だけ。
"""

import animBar

if __name__ == "__main__":
    animBar.toggle()
