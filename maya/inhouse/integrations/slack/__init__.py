"""Slack 通知送信ユーティリティ。"""

import os


def post_message(text, channel="random", thread_ts=None):
    """
    slackにメッセージを送るための関数

    args:
        text : str 送りたいメッセージ
        channel : 送りたいチャンネル デフォルトはrandomチャンネル
        thread_ts : 送りたいスレッドid, デフォルトNoneの場合メッセージになる
    """
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError as error:
        raise RuntimeError("slack_sdk is required to post Slack messages") from error

    slack_token = os.getenv("SLACK_API_BOT_TOKEN")
    if not slack_token:
        raise RuntimeError("SLACK_API_BOT_TOKEN is not set")
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
    except SlackApiError as error:
        raise RuntimeError(error.response["error"]) from error