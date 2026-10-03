"""
Synopsis
--------

.. code-block:: python

    hlib.requirePlugins(plugins, minimum_version=None, module=None, version_plugin=None,
                        minimum_maya=None, name=None, install_hint=None, dialog=True)

製品(モジュールとプラグイン群)の導入を確認し、必要な版が入っていれば全プラグインを
ロードします。入っていない、または版が古い場合はプラグインをロードせず、警告と
ダイアログで導入が必要なことを知らせます。Maya 起動時の ``userSetup.py`` で、
Bifrost など別途インストールする製品を確認する用途を想定しています。

プラグインのロードを行うためシーンは変更しません(プラグインの登録だけが変わります)。
:class:`hlib.environment.PluginPackage` の ``tryLoad`` を 1 回の呼び出しにしたものです。

Return value
------------

``str``
    ``"loaded"``(ロードした)/``"skipped"``(``minimum_maya`` 未満の Maya のため何もしない)/
    ``"missing"``(未導入または版が古い。ロードしていない)/
    ``"outdated"``(導入済みだが、既にロードされているプラグインが古い版)/
    ``"load-failed"``(必要な版は導入済みだが、一部のプラグインをロードできない)。
    ``hlib.environment`` の ``LOADED``・``SKIPPED``・``MISSING``・``OUTDATED``・``LOAD_FAILED``
    と同じ値です。

Related commands
----------------

``maya.cmds.objExists`` / :doc:`ls <../ls/index>`

Flags
-----

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数
     - 型
     - 既定値
     - 説明
   * - ``plugins``
     - ``str | Plugin | Iterable[str | Plugin]``
     - 必須
     - ロードするプラグイン。この順にロードする。
   * - ``minimum_version``
     - ``str | int | tuple[int, ...] | None``
     - ``None``
     - 必要な最小の版(``"3.0.0"`` など)。省略すると版は問わず、導入されていればよい。
   * - ``module``
     - ``str | Module | None``
     - ``None``
     - 版の取得元にする Maya モジュール名(``"Bifrost"`` など)。省略すると ``version_plugin`` の版を使う。
   * - ``version_plugin``
     - ``str | Plugin | None``
     - ``None``
     - 版を調べるプラグイン。省略すると ``plugins`` の先頭。
   * - ``minimum_maya``
     - ``int | None``
     - ``None``
     - 対象とする最小の Maya の年(``2025`` など)。それ未満の Maya では何もしない。
   * - ``name``
     - ``str | None``
     - ``None``
     - 警告に出す製品名。省略すると ``module``、それも無ければ最初のプラグイン名。
   * - ``install_hint``
     - ``str | None``
     - ``None``
     - 警告文に加える導入方法の説明。
   * - ``dialog``
     - ``bool | Callable[[str], None]``
     - ``True``
     - 警告ダイアログの扱い。False で表示しない。関数を渡すと警告文を受け取って呼ぶ。
       バッチ・スタンドアロンでは表示しない。

Examples
--------

.. code-block:: python

    import hlib

    # Maya 2025 以降で Bifrost 3.0.0 以降を確認してロードする
    status = hlib.requirePlugins(
        ("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
        minimum_version="3.0.0", module="Bifrost", version_plugin="bifrostGraph",
        minimum_maya=2025)
    print(status)   # "loaded" / "missing" / ...
"""


def requirePlugins(plugins, minimum_version=None, module=None, version_plugin=None,
                   minimum_maya=None, name=None, install_hint=None, dialog=True):
    """製品の導入を確認し、必要な版が入っていれば全プラグインをロードする。

    Args:
        plugins (str | Plugin | Iterable[str | Plugin]): ロードするプラグイン。この順にロードする。
        minimum_version (str | int | tuple[int, ...] | None): 必要な最小の版。省略すると版は問わない。
        module (str | Module | None): 版の取得元にする Maya モジュール。
        version_plugin (str | Plugin | None): 版を調べるプラグイン。省略すると ``plugins`` の先頭。
        minimum_maya (int | None): 対象とする最小の Maya の年。それ未満の Maya では何もしない。
        name (str | None): 警告に出す製品名。
        install_hint (str | None): 警告文に加える導入方法の説明。
        dialog (bool | Callable[[str], None]): 警告ダイアログの扱い。

    Returns:
        str: ``"loaded"``・``"skipped"``・``"missing"``・``"outdated"``・``"load-failed"`` のいずれか。

    Raises:
        ValueError: plugins が空、minimum_version が版として解釈できない場合。
        TypeError: plugins の要素が文字列でも Plugin でもない場合。
    """
    from ..environment import Plugin
    from ..environment import PluginPackage

    if isinstance(plugins, (str, Plugin)):
        plugins = (plugins,)
    plugins = tuple(plugins)
    if not plugins:
        raise ValueError("plugins must not be empty")
    if name is None:
        name = str(module) if module is not None else str(plugins[0])
    package = PluginPackage(name, plugins=plugins, module=module, version_plugin=version_plugin,
                            minimum_version=minimum_version, minimum_maya=minimum_maya,
                            install_hint=install_hint)
    return package.tryLoad(dialog=dialog)
