"""標準 logging と Maya のメッセージ表示を連携する。"""

import builtins
import logging
import os
import types

__all__ = [
    "MayaHandler",
    "debug",
    "error",
    "getLogger",
    "info",
    "print",
    "raiseWithNotify",
    "warning",
]

LOGGER_NAME = __package__.split(".", 1)[0]
_VIEWPORT_COLORS = {
    logging.WARNING: "#ffcc00",
    logging.ERROR: "#ff4d4d",
    logging.CRITICAL: "#ff4d4d",
}
_NO_CAUSE = object()
#: 設定すると、Script Editorのエラー表示でmlib内部のフレームを省かない環境変数。
FULL_TRACEBACK_ENV = "MLIB_FULL_TRACEBACK"
#: 内部フレームとみなすパッケージのフォルダー(このモジュールの親フォルダー)。
_PACKAGE_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
#: 内部フレームの末尾に挟まっても利用者の行とみなさない標準ライブラリ(with文・デコレーター)。
_TRANSPARENT_MODULES = ("contextlib", "functools")


def _message_from(record):
    """ビューポート向けにログ本文と引数を文字列へ整形する。

    Args:
        record (logging.LogRecord): 整形するレコード。

    Returns:
        str: getMessage()の結果。詳細トレースとFormatterはScript Editor側だけへ適用する。
    """
    return record.getMessage()


class MayaHandler(logging.Handler):
    """詳細ログをScript Editor、警告以上の本文をビューポートへ出力する。"""

    def emit(self, record):
        """ログを Script Editor と必要に応じてビューポートへ出力する。

        Script Editorには標準loggingのFormatter・exc_info・stack_infoを適用する。
        WARNING以上では、例外トレースを含まないメッセージ本文をビューポートにも表示する。
        Formatterが失敗した場合は標準書式へ戻し、書式の失敗理由も詳細欄へ表示する。
        Maya APIをimportできなければ出力しない。Maya表示時のRuntimeErrorは抑制する。

        Args:
            record (logging.LogRecord): 出力するレコード。

        Returns:
            None: 値を返さない。
        """
        message = _message_from(record)
        try:
            details = self.format(record)
        except Exception as exc:
            # 通知の書式設定で、呼出元の例外やfinallyの残りの復元を妨げない。
            details = logging.Formatter().format(record)
            details += f"\nログ書式の適用に失敗しました: {exc}"
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
                om2.MGlobal.displayError(details)
            elif record.levelno >= logging.WARNING:
                om2.MGlobal.displayWarning(details)
            else:
                om2.MGlobal.displayInfo(details)
        except RuntimeError:
            pass

        if record.levelno < logging.WARNING:
            return

        try:
            import html  # 通知時だけ使うため、import mlibの時間に含めない。
            import maya.cmds as cmds
            color = _VIEWPORT_COLORS.get(record.levelno, "#ff4d4d")
            cmds.inViewMessage(
                amg=f'<font color="{color}">{html.escape(message)}</font>',
                pos="midCenter",
                fade=True,
            )
        except (ImportError, RuntimeError):
            pass


def getLogger():
    """Maya 向けハンドラを設定した共有ロガーを取得する。

    Returns:
        logging.Logger: コアパッケージ名のロガー。DEBUGレベル、親への伝播なし。
            reload前のMayaHandlerは現在の型へ置換し、通知を重複させない。
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if (
            type(handler).__module__ in {__name__, LOGGER_NAME + ".utils.logger"}
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
    getLogger().debug(message, *args, **kwargs)


def info(message, *args, **kwargs):
    """通常の情報をINFOレベルでScript Editorへ出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): loggingに渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    getLogger().info(message, *args, **kwargs)


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
    """警告をScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    getLogger().warning(message, *args, **kwargs)


def error(message, *args, **kwargs):
    """エラーをScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。
    通知して中断する場合はraiseWithNotifyを使う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    getLogger().error(message, *args, **kwargs)


def raiseWithNotify(exceptionType, message, *args, fromException=_NO_CAUSE, **kwargs):
    """エラーを通知してから指定型の例外を送出する。

    利用者へ通知して中断するツール(HTools等)の入口用。mlib本体の例外は通知せずに送出し、
    Script Editorの表示と二重にしない。

    Args:
        exceptionType (type[Exception]): 生成する例外クラス。
        message (str): 通知と例外の先頭引数に使うメッセージ。
        *args (object): 例外コンストラクタへ渡す追加位置引数。ログには渡さない。
        fromException (BaseException | None): 指定時は ``raise ... from fromException``
            として例外連鎖を明示する(``None`` を渡すと連鎖を明示的に抑制する)。省略時は
            通常の ``raise`` と同じく、except 節内であれば暗黙の連鎖を保持する。
        **kwargs (object): 例外コンストラクタへ渡すキーワード引数。ログには渡さない。

    Returns:
        NoReturn: 正常には戻らない。

    Raises:
        Exception: exceptionType で指定した例外。コンストラクタが失敗した場合はその例外。
    """
    error(message)
    exception = exceptionType(message, *args, **kwargs)
    if fromException is _NO_CAUSE:
        raise exception
    raise exception from fromException


def _internal_file(filename):
    """フレームのファイルがmlib(拡張の ``<パッケージ名>_*`` を含む)の内部か判定する。

    テスト(``__tests__``)のファイルは利用者のコードとして扱う。

    Args:
        filename (str): ``frame.f_code.co_filename``。

    Returns:
        bool: パッケージ、または同じフォルダーに並ぶ拡張パッケージの中ならTrue。
    """
    path = os.path.normcase(os.path.abspath(filename))
    root = os.path.dirname(_PACKAGE_DIR)
    if not path.startswith(root + os.sep):
        return False
    parts = path[len(root) + 1:].split(os.sep)
    base = os.path.basename(_PACKAGE_DIR)
    return (len(parts) > 1 and (parts[0] == base or parts[0].startswith(base + "_"))
            and "__tests__" not in parts)


def _transparent_file(filename):
    """with文・デコレーターの標準ライブラリのフレームか判定する。

    Args:
        filename (str): ``frame.f_code.co_filename``。

    Returns:
        bool: contextlib・functoolsのファイルならTrue。
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    return stem in _TRANSPARENT_MODULES


def _trimmed_traceback(trace):
    """末尾に続くmlib内部のフレームを除いたトレースバックを返す。

    最後の利用者のフレーム(mlib・contextlib・functools以外)より後ろがmlib内部だけの場合に、
    その利用者のフレームで終わる新しいトレースバックを作る。元のトレースバックは変更しない。
    利用者のフレームが無い(mlib内部だけの)場合や、末尾が利用者のコードの場合はそのまま返す。

    Args:
        trace (types.TracebackType | None): 表示するトレースバック。

    Returns:
        types.TracebackType | None: 省略したトレースバック、または元の値。
    """
    entries = []
    while trace is not None:
        entries.append(trace)
        trace = trace.tb_next
    last_user = None
    for index, entry in enumerate(entries):
        filename = entry.tb_frame.f_code.co_filename
        if not _internal_file(filename) and not _transparent_file(filename):
            last_user = index
    if last_user is None or not any(_internal_file(entry.tb_frame.f_code.co_filename)
                                    for entry in entries[last_user + 1:]):
        return entries[0] if entries else None
    trimmed = None
    for entry in reversed(entries[:last_user + 1]):
        trimmed = types.TracebackType(trimmed, entry.tb_frame, entry.tb_lasti, entry.tb_lineno)
    return trimmed


def _install_exception_formatter():
    """Script Editorのエラー表示で、mlib内部のフレームを省く書式関数を設定する。

    Maya公式の差し替え口 ``maya.utils.formatGuiException`` を、元の関数を呼ぶ関数で包む。
    Script Editorは最後のフレームのファイル・行を表示するため、mlibの中で送出した例外も
    利用者がmlibを呼んだ行を表示する。環境変数 ``MLIB_FULL_TRACEBACK`` を空以外にすると
    省かずに表示する(呼出しごとに判定する)。再読み込みでは以前の包みを外して設定し直す。
    Mayaが無い環境では何もしない。

    Returns:
        bool: 設定した場合はTrue。
    """
    try:
        # Mayaの無い環境(静的検査)でもloggerをimportできるよう、設定時に読み込む。
        import maya.utils as maya_utils
    except ImportError:
        return False
    current = getattr(maya_utils, "formatGuiException", None)
    if current is None:
        return False
    previous = getattr(current, "_mlib_previous", current)

    def format_gui_exception(exception_type, exception, trace, detail=2):
        """mlib内部のフレームを省いてからMayaの書式関数へ渡す。

        Args:
            exception_type (type): 例外の型。
            exception (BaseException): 例外。
            trace (types.TracebackType | None): トレースバック。
            detail (int): Mayaの表示の詳細度。

        Returns:
            str: Script Editorへ表示する文字列。
        """
        if not os.environ.get(FULL_TRACEBACK_ENV):
            try:
                trace = _trimmed_traceback(trace)
            except Exception:
                pass  # 省略の失敗でMayaのエラー表示自体を妨げない。
        return previous(exception_type, exception, trace, detail)

    format_gui_exception._mlib_previous = previous
    maya_utils.formatGuiException = format_gui_exception
    return True


_install_exception_formatter()
