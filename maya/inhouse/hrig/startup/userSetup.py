"""hrigの起動処理。依存確認とGUIのチャンネル操作監視を遅延登録する。"""

import hrig_bifrost_startup

hrig_bifrost_startup.initialize()

import hrig_channel_startup

hrig_channel_startup.initialize()
