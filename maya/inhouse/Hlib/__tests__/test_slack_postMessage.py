"""Slack 投稿疎通を確認する手動テストスクリプト。"""

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
    # まず通常メッセージを投稿し、返却 ts をスレッド親として使う。
    response = client.chat_postMessage(
        channel=slack_channel,
        text="はじめまして :wave: pythonからSlackへ通知テスト:bow:"
    )
    thread_ts = response["ts"]

    # 続けて同一内容をスレッド返信として投稿する。
    response = client.chat_postMessage(
        channel=slack_channel,
        text="はじめまして :wave: pythonからSlackへ通知テスト:bow:",
        thread_ts=thread_ts
    )
except SlackApiError as e:
    # 認証不正やチャンネル不正などの API エラー内容を Maya 側へ通知する。
    cmds.error(e)
    assert e.response["error"]