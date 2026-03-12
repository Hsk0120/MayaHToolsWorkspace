import time
import sys
from HTools.slack import post_message

def progress_bar(iterable, prefix="", size=60, file=sys.stdout, slack_channel=None, slack_thread_ts=None):
    count = len(iterable)
    
    def show(j):
        x = int(size * j / count)
        text = f"{prefix}[{'#' * x}{'.' * (size - x)}] {j}/{count}\r"
        file.write(text)
        file.flush()

        # チャンネル指定がある場合、チャンネルに送信
        if slack_channel:
            post_message(text, channel=slack_channel)

        # スレッド指定がある場合、スレに送信
        if slack_thread_ts:
            post_message(text, thread_ts=slack_thread_ts)
    
    show(0)
    for i, item in enumerate(iterable, 1):
        yield item
        show(i)
    file.write("\n")
    file.flush()

if __name__ == "__main__":
    # 使用例
    for i in progress_bar(range(100), prefix="Progress:", size=50):
        time.sleep(0.1)