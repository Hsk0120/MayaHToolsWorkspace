import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import maya.cmds as cmds

def post_message(text, channel="random", thread_ts=None):
    """
    slackにメッセージを送るための関数

    args:
        text : str 送りたいメッセージ
        channel : 送りたいチャンネル デフォルトはrandomチャンネル
        thread_ts : 送りたいスレッドid, デフォルトNoneの場合メッセージになる
    """
    slack_token = os.getenv("SLACK_API_BOT_TOKEN")
    client = WebClient(token=slack_token)

    try:
        if thread_ts:
            response = client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts
            )
        else:
            response = client.chat_postMessage(
                channel=channel,
                text=text
            )
        return response["ts"]
    except SlackApiError as e:
        cmds.warning(e)
        cmds.warning(e.response["error"])