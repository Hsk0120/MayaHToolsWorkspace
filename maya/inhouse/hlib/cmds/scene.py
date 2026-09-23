"""
Synopsis
--------

.. code-block:: python

    hlib.scene(path=None)

現在のシーン、または指定パスを表す Scene オブジェクトを取得します。
生成だけではシーンの読み込み・保存・選択変更を行いません。
パスは取得時に保持し、外部でシーンを切り替えても自動追従しません。

Return value
------------

``Scene``
    パスを保持するオブジェクト。print でパス、未保存なら untitled を表示します。

Flags
-----

.. list-table::
   :header-rows: 1

   * - 引数
     - 型
     - 既定値
     - 説明
   * - path
     - str | Path | None
     - None
     - None は現在のシーン。指定時は絶対パスに変換して保持します。存在確認はしません。

Examples
--------

.. code-block:: python

    import hlib

    current = hlib.scene()
    print(current)
    other = hlib.scene("C:/project/scenes/character.ma")
    print(other)
    # 実際に開く場合のみ実行します。
    # other.open()
"""


def scene(path=None):
    """現在または指定パスの Scene を取得する。

    Args:
        path (str | Path | None): シーンパス。省略時は現在のシーン。

    Returns:
        Scene: パスを保持するオブジェクト。

    Raises:
        ValueError: パスが空または未対応の型の場合。
    """
    from ..files import Scene

    return Scene(path)
