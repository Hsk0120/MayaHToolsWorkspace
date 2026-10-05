"""Slack 通知送信ユーティリティ。"""

import os


def post_message(text, channel="random", thread_ts=None):
    """Slackへメッセージを投稿し、投稿のタイムスタンプを返す。

    Args:
        text (str): 投稿する本文。
        channel (str): 投稿先チャンネル。既定はrandom。
        thread_ts (str | None): 返信先のタイムスタンプ。省略時は新規投稿。

    Returns:
        str: 投稿したメッセージのタイムスタンプ。

    Raises:
        RuntimeError: SDK・環境変数SLACK_API_BOT_TOKENがない、またはSlack APIが失敗した場合。
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