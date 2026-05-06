"""maya_standalone デコレータと進捗通知の手動テストスクリプト。"""

from importlib import reload
import HTools; reload(HTools)
from HTools.decorator import maya_standalone
from HTools.utils import progress_bar
from HTools.slack import post_message
import time

@maya_standalone
def wait_function():
    """スタンドアロン初期化下で進捗バーと Slack 通知を検証します。"""
    print("***** start *****")
    # 先頭メッセージを投稿し、進捗通知のスレッド先として利用する。
    thread_ts = post_message("***** start *****")

    # 進捗表示を伴って疑似待機し、最後に完了通知を送る。
    for i in progress_bar(range(10), prefix="Progress:", size=50, slack_thread_ts=thread_ts):
        time.sleep(0.1)
        # post_message(str(i), thread_ts=thread_ts)
    print("***** end *****")
    post_message("***** end *****", thread_ts=thread_ts)
    
if __name__ == "__main__":
    wait_function()