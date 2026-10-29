# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""標準 logging と Maya のメッセージ表示を連携する。"""

import builtins
import logging
from typing import Any, NoReturn, TextIO

__all__ = ['MayaHandler', 'debug', 'error', 'get_logger', 'info', 'print', 'raise_with_notify', 'warning']
LOGGER_NAME: Any
_VIEWPORT_COLORS: dict
_NO_CAUSE: Any

def _message_from(record: logging.LogRecord) -> str:
    """ビューポート向けにログ本文と引数を文字列へ整形する。

    Args:
        record (logging.LogRecord): 整形するレコード。

    Returns:
        str: getMessage()の結果。詳細トレースとFormatterはScript Editor側だけへ適用する。
    """
    ...


class MayaHandler(logging.Handler):
    """詳細ログをScript Editor、警告以上の本文をビューポートへ出力する。"""
    def emit(self, record: logging.LogRecord) -> None:
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
        ...

def get_logger() -> logging.Logger:
    """Maya 向けハンドラを設定した共有ロガーを取得する。

    Returns:
        logging.Logger: コアパッケージ名のロガー。DEBUGレベル、親への伝播なし。
            reload前のMayaHandlerは現在の型へ置換し、通知を重複させない。
    """
    ...

def debug(message: object, *args: object, **kwargs: object) -> None:
    """診断レベルのログを出力する。

    Maya 上ではScript Editor に出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): logging に渡すメッセージ書式引数。
        **kwargs (object): exc_info、extra、stack_info、stacklevel など logging に渡すオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def info(message: object, *args: object, **kwargs: object) -> None:
    """通常の情報をINFOレベルでScript Editorへ出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): loggingに渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def print(*objects: object, sep: str | None = ..., end: str | None = ..., file: TextIO | None = ..., flush: bool = ...) -> None:
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
    ...

def warning(message: object, *args: object, **kwargs: object) -> None:
    """警告をScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def error(message: object, *args: object, **kwargs: object) -> None:
    """エラーをScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。
    通知して中断する場合はraise_with_notifyを使う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def raise_with_notify(exception_type: type[Exception], message: str, *args: object, from_exception: BaseException | None = ..., **kwargs: object) -> NoReturn:
    """エラーを通知してから指定型の例外を送出する。

    Args:
        exception_type (type[Exception]): 生成する例外クラス。
        message (str): 通知と例外の先頭引数に使うメッセージ。
        *args (object): 例外コンストラクタへ渡す追加位置引数。ログには渡さない。
        from_exception (BaseException | None): 指定時は ``raise ... from from_exception``
            として例外連鎖を明示する(``None`` を渡すと連鎖を明示的に抑制する)。省略時は
            通常の ``raise`` と同じく、except 節内であれば暗黙の連鎖を保持する。
        **kwargs (object): 例外コンストラクタへ渡すキーワード引数。ログには渡さない。

    Returns:
        NoReturn: 正常には戻らない。

    Raises:
        Exception: exception_type で指定した例外。コンストラクタが失敗した場合はその例外。
    """
    ...
