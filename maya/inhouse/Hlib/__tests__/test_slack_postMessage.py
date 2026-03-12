import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import maya.cmds as cmds

# デバッグレベルのログを出力します
logging.basicConfig(level=logging.DEBUG)

slack_token = os.getenv("SLACK_API_BOT_TOKEN")
slack_channel = "random"
client = WebClient(token=slack_token)

try:
    response = client.chat_postMessage(
        channel=slack_channel,
        text="はじめまして :wave: pythonからSlackへ通知テスト:bow:"
    )
    thread_ts = response["ts"]

    response = client.chat_postMessage(
        channel=slack_channel,
        text="はじめまして :wave: pythonからSlackへ通知テスト:bow:",
        thread_ts=thread_ts
    )
except SlackApiError as e:
    # You will get a SlackApiError if "ok" is False
    # str like 'invalid_auth', 'channel_not_found'
    cmds.error(e)
    assert e.response["error"]