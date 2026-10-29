# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""反復の処理件数をテキスト1行へ表示する。MayaのGUIバーは作らない。

Mayaに依存せず、指定ストリームと任意のnotify callbackへ描画文字列を渡す。
要素の取出しと描画はprogressBar()の返却イテレーターを反復した時に行う。
"""

import sys
from typing import Any, Callable, Iterable, Iterator, TextIO

_DONE_CELL: str
_TODO_CELL: str
_FRAME: str
_UNKNOWN_TOTAL: str

def _proportion(done: int, total: int, scale: int) -> int:
    """処理済み件数を 0 から scale までの整数へ換算する。

    浮動小数点の丸め誤差で値が1つ小さくなるのを避けるため、整数演算で
    切り捨てる。全体が0件の場合や、処理済み件数が全体に達した・超えた
    場合は scale に揃える。

    Args:
        done (int): 処理済みの件数。
        total (int): 全体の件数。
        scale (int): 換算後の最大値。

    Returns:
        int: 0 以上 scale 以下の整数。
    """
    ...


class _ProgressLine(object):
    """1本の進捗行について、件数の保持・文字列の組み立て・出力を受け持つ。

    処理済みの件数は ``done`` に保持し、``advance`` のたびに1つ増やす。
    見出しは生成時に末尾の空白を取り除いた形で保持し、空なら表示しない。

    Args:
        label (str): 行頭の見出し。
        total (int | None): 全体の件数。不明なら None。
        width (int): バー部分の文字数。
        stream (TextIO): ``write`` を備える出力先。
        notify (Callable[[str], object] | None): 描画した文字列の通知先。
    """
    def __init__(self, label: str, total: int | None, width: int, stream: object, notify: Callable[..., Any] | None) -> None:
        """進捗の保持値を初期化する。ここでは出力しない。

        Args:
            label (str): 末尾の空白を除去して保持する表示名。
            total (int | None): 全体の処理数。不明な場合は None。
            width (int): 進捗バーの表示幅。
            stream (object): 書き込み先。
            notify (callable | None): 描画した文字列を渡す通知先。
        """
        ...
    def render(self) -> str:
        """現在の件数に応じた表示文字列を組み立てる。

        Returns:
            str: 件数が既知ならバー・百分率・件数、不明なら件数だけを並べた文字列。
                行頭復帰や改行は含まない。
        """
        ...
    def draw(self) -> str:
        """行頭へ戻って現在の表示で上書きし、通知先があれば同じ文字列を渡す。

        Returns:
            str: 出力した表示文字列。
        """
        ...
    def advance(self) -> None:
        """処理済み件数を1つ進めて描画し直す。

        Returns:
            None: 値を返さない。
        """
        ...
    def finish(self, quiet: bool = ...) -> None:
        """改行を出力して行を閉じる。

        Args:
            quiet (bool): True なら、改行の書き込みや ``flush`` で起きた
                ``Exception`` を送出せずに捨てる。別の例外が伝わっている
                途中で行を閉じるときに使い、元の例外が後から起きた出力先の
                失敗で置き換わらないようにする。

        Returns:
            None: 値を返さない。
        """
        ...
    def _flush(self) -> None:
        """出力先が ``flush`` を持つ場合だけ呼び出す。

        Returns:
            None: 値を返さない。
        """
        ...
    label: Any
    total: Any
    width: Any
    stream: Any
    notify: Any
    done: Any

def _track(iterable: Iterable, line: _ProgressLine) -> Iterator[object]:
    """要素を順に返しながら、line の件数更新と描画を行うジェネレーター。

    最初の要素を取り出せた時点で0件の行を描画し、利用側が次の要素を
    要求するたび(=直前の要素の処理が終わるたび)に1件進める。途中で
    ``break`` した場合や例外でジェネレーターが閉じられた場合も、描画に
    着手していれば改行で行を閉じる。描画そのもの(出力や ``notify``)が
    例外を送出した場合も同様で、書きかけの行を改行で閉じてから例外を
    伝える。要素が1つも無ければ何も出力しない。

    例外が伝わっている途中で行を閉じる場合、改行の書き込みに失敗しても
    その失敗は捨て、先に起きた例外をそのまま伝える(閉じられた出力先へ
    もう一度書こうとして別の例外に置き換わるのを防ぐ)。最後まで反復
    できた場合の改行の失敗は、そのまま呼び出し側へ伝える。

    Args:
        iterable (Iterable): 反復する対象。
        line (_ProgressLine): 描画を担当する進捗行。

    Yields:
        object: iterable の要素をそのまま返す。
    """
    ...

def progressBar(iterable: Iterable, *, label: str = ..., total: int | None = ..., width: int = ..., stream: TextIO | None = ..., notify: Callable[[str], object] | None = ...) -> Iterator:
    """要素を同じ順序で返しながら、処理済み件数をテキスト1行へ描画する。

    引数検証とlen()は呼出し時に行い、要素の取出しと描画は反復時に行う。
    最初の要素を取り出すと0件を表示し、次の要素を要求するたびに1件進む。
    完走時に改行し、途中終了は返却ジェネレーターのclose()/回収時に行を閉じる。空入力では出力もnotifyもない。
    入力反復・出力・通知の例外は伝播する。例外伝播/close時は改行の通常例外だけを抑制し、正常完了時は抑制しない。

    Args:
        iterable (Iterable): 要素をそのまま返す反復対象。
        label (str): 行頭の見出し。末尾の空白を除き、空なら省略する。
        total (int | None): 非負の全体件数。Noneはlen()を試し、TypeErrorなら件数のみを表示する。
            実際の件数がtotalを超えてもバー/百分率は満杯のまま件数を増やす。
        width (int): バー幅。1以上。
        stream (TextIO | None): write/任意のflushを持つ出力先。Noneは呼出し時のsys.stdout。
            行頭復帰を解釈しない出力先では描画が上書きされない場合がある。
        notify (Callable[[str], object] | None): 各描画の文字列を同期で受け取る。改行/行頭復帰は含まない。
            戻り値は無視し、必要な通知の間引きは呼出し側で行う。

    Returns:
        Iterator: 元の要素を保持順に返すジェネレーター。

    Raises:
        TypeError: labelの型、width/totalの整数型が不正な場合。boolは整数指定として拒否する。
        ValueError: widthが1未満、またはtotalが負の場合。

    Examples:
        >>> import io
        >>> buffer = io.StringIO()
        >>> list(progressBar("ab", label="demo", width=4, stream=buffer))
        ['a', 'b']
        >>> buffer.getvalue().split("\\r")[-1]
        'demo |====| 100% 2/2\\n'
    """
    ...
