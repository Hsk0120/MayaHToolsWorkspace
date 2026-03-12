from importlib import reload
import HTools; reload(HTools)
from HTools.decorator import maya_standalone
from HTools.utils import progress_bar
from HTools.slack import post_message
import time

@maya_standalone
def wait_function():
    print("***** start *****")
    thread_ts = post_message("***** start *****")
    for i in progress_bar(range(10), prefix="Progress:", size=50, slack_thread_ts=thread_ts):
        time.sleep(0.1)
        # post_message(str(i), thread_ts=thread_ts)
    print("***** end *****")
    post_message("***** end *****", thread_ts=thread_ts)
    
if __name__ == "__main__":
    wait_function()