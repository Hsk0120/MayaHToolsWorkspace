"""標準 logging と Maya のメッセージ表示を連携する。"""

import builtins
import html
import logging


LOGGER_NAME = "hlib"
_VIEWPORT_COLORS = {
    logging.WARNING: "#ffcc00",
    logging.ERROR: "#ff4d4d",
    logging.CRITICAL: "#ff4d4d",
}


def _message_from(record):
    """ログレコードのメッセージと引数を文字列へ整形する。

    Args:
        record (logging.LogRecord): 整形するレコード。

    Returns:
        str: getMessage() の結果。例外トレースや Formatter は適用しない。
    """
    return record.getMessage()


class MayaHandler(logging.Handler):
    """ログレコードを Maya の Script Editor とビューポートへ出力するハンドラ。"""

    def emit(self, record):
        """ログを Script Editor と必要に応じてビューポートへ出力する。

        WARNING 以上ではビューポートにも表示する。Maya API を import できなければ出力しない。Maya 表示時の RuntimeError は抑制する。

        Args:
            record (logging.LogRecord): 出力するレコード。

        Returns:
            None: 値を返さない。
        """
        message = _message_from(record)
        try:
            import maya.cmds as cmds
            # mayapy初期化前はMGlobalの表示APIを呼ばない。
            if not hasattr(cmds, "about"):
                return
            import maya.api.OpenMaya as om2
        except ImportError:
            return

        try:
            if record.levelno >= logging.ERROR:
                om2.MGlobal.displayError(message)
            elif record.levelno >= logging.WARNING:
                om2.MGlobal.displayWarning(message)
            else:
                om2.MGlobal.displayInfo(message)
        except RuntimeError:
            pass

        if record.levelno < logging.WARNING:
            return

        try:
            import maya.cmds as cmds
            color = _VIEWPORT_COLORS.get(record.levelno, "#ff4d4d")
            cmds.inViewMessage(
                amg=f'<font color="{color}">{html.escape(message)}</font>',
                pos="midCenter",
                fade=True,
            )
        except (ImportError, RuntimeError):
            pass


def get_logger():
    """Maya 向けハンドラを設定した共有ロガーを取得する。

    Returns:
        logging.Logger: 名前がhlibのロガー。DEBUGレベル、親への伝播なし。
            reload前のMayaHandlerは現在の型へ置換し、通知を重複させない。
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if (
            type(handler).__module__ == __name__
            and type(handler).__name__ == "MayaHandler"
            and not isinstance(handler, MayaHandler)
        ):
            logger.removeHandler(handler)
            handler.close()
    if not any(isinstance(handler, MayaHandler) for handler in logger.handlers):
        logger.addHandler(MayaHandler())
    return logger


def debug(message, *args, **kwargs):
    """診断レベルのログを出力する。

    Maya 上ではScript Editor に出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): logging に渡すメッセージ書式引数。
        **kwargs (object): exc_info、extra、stack_info、stacklevel など logging に渡すオプション。

    Returns:
        None: 値を返さない。
    """
    get_logger().debug(message, *args, **kwargs)


def info(message, *args, **kwargs):
    """通常の情報をINFOレベルでScript Editorへ出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): loggingに渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    get_logger().info(message, *args, **kwargs)


def print(*objects, sep=" ", end="\n", file=None, flush=False):
    """Python標準のprintと同じ規則で出力する。

    Mayaでは通常Script Editorへ表示する。ログレベル・ビューポート通知は付けず、
    file指定や改行なし出力を維持する。INFOログが必要な場合はinfoを使う。

    Args:
        *objects (object): 出力する値。
        sep (str | None): 値の区切り。Noneは標準値の空白。
        end (str | None): 末尾。Noneは標準値の改行。
        file (TextIO | None): 書込み先。Noneは現在のsys.stdout。
        flush (bool): Trueなら出力先をフラッシュする。

    Returns:
        None: 値を返さない。
    """
    builtins.print(*objects, sep=sep, end=end, file=file, flush=flush)


def warning(message, *args, **kwargs):
    """警告レベルのログを出力する。

    Maya 上ではScript Editor とビューポートに出力する。例外は送出しない。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): logging に渡すメッセージ書式引数。
        **kwargs (object): exc_info、extra、stack_info、stacklevel など logging に渡すオプション。

    Returns:
        None: 値を返さない。
    """
    get_logger().warning(message, *args, **kwargs)


def error(message, *args, **kwargs):
    """エラーレベルのログを出力する。

    Maya 上ではScript Editor とビューポートに出力する。例外は送出しない。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): logging に渡すメッセージ書式引数。
        **kwargs (object): exc_info、extra、stack_info、stacklevel など logging に渡すオプション。

    Returns:
        None: 値を返さない。
    """
    get_logger().error(message, *args, **kwargs)


_UNSET = object()


def raise_with_notify(exception_type, message, *args, from_exception=_UNSET, **kwargs):
    """エラーを通知してから指定型の例外を送出する。

    Args:
        exception_type (type[Exception]): 生成する例外クラス。
        message (str): 通知と例外の先頭引数に使うメッセージ。
        *args (object): 例外コンストラクタへ渡す追加位置引数。ログには渡さない。
        from_exception (BaseException | None): 指定時は ``raise ... from from_exception``
            として例外連鎖を明示する（``None`` を渡すと連鎖を明示的に抑制する）。省略時は
            通常の ``raise`` と同じく、except 節内であれば暗黙の連鎖を保持する。
        **kwargs (object): 例外コンストラクタへ渡すキーワード引数。ログには渡さない。

    Returns:
        NoReturn: 正常には戻らない。

    Raises:
        Exception: exception_type で指定した例外。コンストラクタが失敗した場合はその例外。
    """
    error(message)
    exception = exception_type(message, *args, **kwargs)
    if from_exception is _UNSET:
        raise exception
    raise exception from from_exception


__all__ = [
    "MayaHandler",
    "debug",
    "error",
    "get_logger",
    "info",
    "print",
    "raise_with_notify",
    "warning",
]
