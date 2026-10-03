"""FramePlayer(コマ送り確認用の動画プレイヤー)とMayaのタイムスライダーを連携させる画面を開く。

本体は maya/inhouse/FramePlayer のパッケージ(frameplayer)。このファイルはHToolsのメニューから開くための入口だけ。
"""

import frameplayer

if __name__ == "__main__":
    frameplayer.show()
