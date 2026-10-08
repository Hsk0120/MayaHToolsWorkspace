"""任意拡張の自動検出・依存不在・衝突・再読み込みを検証する。"""
import importlib
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

import hlib


def mayapy_executable():
    """子プロセス用の mayapy を返す。

    Maya GUI 内では ``sys.executable`` が maya.exe になり、``-c`` を渡すと新しい GUI が起動してしまうため、
    同じフォルダーの mayapy を使う。見つからなければテストを skip する。

    Returns:
        str: mayapy のパス。
    """
    executable = Path(sys.executable)
    if executable.stem.lower() == "mayapy":
        return str(executable)
    candidate = executable.with_name("mayapy.exe" if os.name == "nt" else "mayapy")
    if not candidate.is_file():
        raise unittest.SkipTest("mayapy が見つからない: {}".format(candidate))
    return str(candidate)


class ExtensionsTest(unittest.TestCase):
    def test_bifrost_first_import_in_fresh_process(self):
        """先行importを軽い宣言だけで完了し、後から正常に検出する。"""
        script = '''
import sys
import hlib_bifrost
assert "hlib" not in sys.modules
import maya.standalone
maya.standalone.initialize(name="python")
import hlib
state = hlib._core.extensions.status()["hlib_bifrost"]["state"]
assert state in ("loaded", "unavailable"), state
assert hlib_bifrost.nodes.Graph is not None
old = hlib_bifrost
hlib.reload()
import hlib_bifrost
assert hlib_bifrost is not old
maya.standalone.uninitialize()
'''
        result = subprocess.run([mayapy_executable(), '-c', script],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hlib_extensions_')
        self.path = Path(self.temp.name)
        sys.path.insert(0, self.temp.name)

    def tearDown(self):
        sys.path.remove(self.temp.name)
        for name in list(sys.modules):
            if name.startswith('hlib_fixture_'):
                del sys.modules[name]
        hlib.reload()
        self.temp.cleanup()

    def package(self, name, body):
        path = self.path / name
        path.mkdir()
        (path / '__init__.py').write_text(body, encoding='utf-8')
        importlib.invalidate_caches()
        return path

    def wrappers(self, path, suffix, body, *, type_name, class_name):
        """実装と、公開名・型対応を明示するパッケージ入口を作成する。"""
        folder = path / suffix
        folder.mkdir()
        (folder / '__init__.py').write_text(
            'from .sample import {0}\n__all__ = [{0!r}]\n'
            '_WRAPPER_CLASSES = {{{1!r}: {0}}}\n'.format(class_name, type_name),
            encoding='utf-8')
        (folder / 'sample.py').write_text(body, encoding='utf-8')

    def test_discovery_reload_and_removal(self):
        path = self.package('hlib_fixture_valid', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nclass Sample(Node): pass\n', type_name='fixtureNode', class_name='Sample')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nclass SamplePlug(Plug): pass\n', type_name='fixtureData', class_name='SamplePlug')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()['hlib_fixture_valid']['state'], 'loaded')
        old = hlib.nodes.Node._registry.lookup('fixtureNode')
        self.assertTrue(issubclass(old, hlib.nodes.Node))
        self.assertIsNotNone(hlib.plugs.Plug._registry.lookup('fixtureData'))
        hlib.reload()
        new = hlib.nodes.Node._registry.lookup('fixtureNode')
        self.assertIsNot(old, new)
        self.assertTrue(issubclass(new, hlib.nodes.Node))
        (path / 'nodes' / 'sample.py').unlink()
        (path / 'nodes' / '__init__.py').write_text(
            '__all__ = []\n_WRAPPER_CLASSES = {}\n', encoding='utf-8')
        hlib.reload()
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureNode'))

    def test_unavailable_and_unmarked(self):
        self.package('hlib_fixture_unavailable', 'HLIB_EXTENSION_API = 1\ndef is_available(): return False\n')
        self.package('hlib_fixture_unmarked', '')
        hlib.reload()
        states = hlib._core.extensions.status()
        self.assertEqual(states['hlib_fixture_unavailable']['state'], 'unavailable')
        self.assertEqual(states['hlib_fixture_unmarked']['state'], 'skipped')

    def test_cross_extension_dependency_is_rejected_before_wrapper_import(self):
        """他拡張の継承・関数内importは登録前に拒否する。"""
        base = self.package('hlib_fixture_zbase', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(base, 'nodes', 'from hlib.nodes import Node\nclass Base(Node): pass\n', type_name='fixtureBase', class_name='Base')
        child = self.package('hlib_fixture_achild', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(child, 'nodes', 'from hlib_fixture_zbase.nodes.sample import Base\nclass Child(Base): pass\n', type_name='fixtureChild', class_name='Child')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()['hlib_fixture_achild']['state'], 'error')
        self.assertNotIn('hlib_fixture_achild.nodes', sys.modules)
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureChild'))
        self.assertEqual(hlib._core.extensions.status()['hlib_fixture_zbase']['state'], 'loaded')

    def test_failed_import_recovers_on_first_reload(self):
        """親のimport失敗で孤立した子も更新し、探索パスから外した場合も解除する。"""
        name = 'hlib_fixture_recovery'
        path = self.package(name, 'from . import config\nraise RuntimeError("broken initialization")\n')
        (path / 'config.py').write_text('VALUE = 1\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'error')
        self.assertNotIn(name, sys.modules)
        self.assertIn(name + '.config', sys.modules)
        (path / 'config.py').write_text('VALUE = 22222\n', encoding='utf-8')
        (path / '__init__.py').write_text(
            'from . import config\nHLIB_EXTENSION_API = 1\n'
            'def is_available(): return config.VALUE == 22222\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'loaded')
        self.assertEqual(sys.modules[name + '.config'].VALUE, 22222)
        # 再び失敗させ、親がない状態で探索パスからも削除する。
        (path / '__init__.py').write_text('from . import config\nraise RuntimeError("again")\n', encoding='utf-8')
        hlib.reload()
        sys.path.remove(self.temp.name)
        try:
            hlib.reload()
            self.assertNotIn(name + '.config', sys.modules)
        finally:
            sys.path.insert(0, self.temp.name)

    def test_unavailable_extension_does_not_parse_implementation(self):
        """利用不可なら現Pythonで読めない実装を解析せず、利用可能時は検証する。"""
        name = 'hlib_fixture_optional'
        path = self.package(name, 'HLIB_EXTENSION_API = 1\ndef is_available(): return False\n')
        # バージョンに依存せず、解析されると必ず失敗する構文で検証する。
        (path / 'implementation.py').write_text('def invalid(\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'unavailable')
        self.assertNotIn(name + '.implementation', sys.modules)
        (path / '__init__.py').write_text(
            'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'error')

    def test_reload_removes_all_extensions_before_reimport(self):
        """名前順で後の拡張も最初の再import前に解除し、SDKは保持する。"""
        import types
        self.package('hlib_fixture_zlast', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        first = self.package('hlib_fixture_afirst', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        hlib.reload()
        sdk = types.ModuleType('fixture_external_sdk')
        sys.modules[sdk.__name__] = sdk
        try:
            (first / '__init__.py').write_text(
                'import sys\nassert "hlib_fixture_zlast" not in sys.modules\n'
                'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n', encoding='utf-8')
            hlib.reload()
            self.assertEqual(hlib._core.extensions.status()['hlib_fixture_afirst']['state'], 'loaded')
            self.assertIs(sys.modules[sdk.__name__], sdk)
        finally:
            sys.modules.pop(sdk.__name__, None)

    def test_reentrant_reload_preserves_modules(self):
        """初期化中のreload要求は、一部だけ解除せず拒否する。"""
        from unittest import mock
        self.package('hlib_fixture_reentry', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        hlib.reload()
        module = sys.modules['hlib_fixture_reentry']
        with mock.patch.object(hlib._core.extensions, '_loading', True):
            with self.assertRaises(RuntimeError):
                hlib.reload()
        self.assertIs(sys.modules['hlib_fixture_reentry'], module)

    def test_collision_is_atomic_and_errors_visible(self):
        path = self.package('hlib_fixture_conflict', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nclass Sample(Node): pass\n', type_name='fixturePartial', class_name='Sample')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nclass Sample(Plug): pass\n', type_name='double3', class_name='Sample')
        self.package('hlib_fixture_broken', 'HLIB_EXTENSION_API = 1\ndef is_available(): raise RuntimeError("SDK broken")\n')
        hlib.reload()
        states = hlib._core.extensions.status()
        self.assertEqual(states['hlib_fixture_conflict']['state'], 'error')
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixturePartial'))
        self.assertEqual(states['hlib_fixture_broken']['reason'], 'SDK broken')
        self.assertIsNotNone(hlib.nodes.Node._registry.lookup('transform'))

    def test_registration_failure_restores_both_registries(self):
        """登録途中の障害で先に登録したnodesの型対応も戻す。"""
        from unittest import mock
        path = self.package('hlib_fixture_atomic', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nclass AtomicNode(Node): pass\n', type_name='fixtureAtomicNode', class_name='AtomicNode')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nclass AtomicPlug(Plug): pass\n', type_name='fixtureAtomicPlug', class_name='AtomicPlug')
        registry = hlib.plugs.Plug._registry
        original = registry.register

        def reject(key, cls):
            """指定型の登録直後に障害を発生させる。"""
            original(key, cls)
            if key == 'fixtureAtomicPlug':
                raise RuntimeError('registration interrupted')

        with mock.patch.object(registry, 'register', side_effect=reject):
            hlib._core.extensions._initialize()
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureAtomicNode'))
        self.assertIsNone(registry.lookup('fixtureAtomicPlug'))
        # 明示importでの公開は型登録と独立し、登録失敗で名前を書き換えない。
        self.assertTrue(hasattr(sys.modules['hlib_fixture_atomic.nodes'], 'AtomicNode'))
        self.assertEqual(hlib._core.extensions.status()['hlib_fixture_atomic']['state'], 'error')
        self.assertIsNotNone(hlib.nodes.Node._registry.lookup('transform'))

    def test_unlisted_wrapper_is_not_imported_or_registered(self):
        """実装ファイルを置くだけでは公開・型登録されない。"""
        name = 'hlib_fixture_explicit'
        path = self.package(name, 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        folder = path / 'nodes'
        folder.mkdir()
        (folder / '__init__.py').write_text('__all__ = []\n_WRAPPER_CLASSES = {}\n', encoding='utf-8')
        (folder / 'sample.py').write_text('from hlib.nodes import Node\nclass Sample(Node): pass\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'loaded')
        self.assertNotIn(name + '.nodes.sample', sys.modules)
        self.assertFalse(hasattr(sys.modules[name + '.nodes'], 'Sample'))

    def test_invalid_declaration_does_not_register_other_kinds(self):
        """型対応の不正な値は登録前に検出する。"""
        name = 'hlib_fixture_invalidmap'
        path = self.package(name, 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nclass Sample(Node): pass\n',
                      type_name='fixtureInvalidMapNode', class_name='Sample')
        folder = path / 'plugs'
        folder.mkdir()
        (folder / '__init__.py').write_text('_WRAPPER_CLASSES = {"invalid": object()}\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib._core.extensions.status()[name]['state'], 'error')
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureInvalidMapNode'))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
