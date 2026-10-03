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
state = hlib.extensions.status()["hlib_bifrost"]["state"]
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

    def wrappers(self, path, suffix, body):
        folder = path / suffix
        folder.mkdir()
        (folder / '__init__.py').write_text('', encoding='utf-8')
        (folder / 'sample.py').write_text(body, encoding='utf-8')

    def test_discovery_reload_and_removal(self):
        path = self.package('hlib_fixture_valid', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nfrom hlib.extensions import node_wrapper\n@node_wrapper("fixtureNode")\nclass Sample(Node): pass\n')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nfrom hlib.extensions import plug_wrapper\n@plug_wrapper("fixtureData")\nclass SamplePlug(Plug): pass\n')
        hlib.reload()
        self.assertEqual(hlib.extensions.status()['hlib_fixture_valid']['state'], 'loaded')
        old = hlib.nodes.Node._registry.lookup('fixtureNode')
        self.assertTrue(issubclass(old, hlib.nodes.Node))
        self.assertIsNotNone(hlib.plugs.Plug._registry.lookup('fixtureData'))
        hlib.reload()
        new = hlib.nodes.Node._registry.lookup('fixtureNode')
        self.assertIsNot(old, new)
        self.assertTrue(issubclass(new, hlib.nodes.Node))
        (path / 'nodes' / 'sample.py').unlink()
        hlib.reload()
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureNode'))

    def test_unavailable_and_unmarked(self):
        self.package('hlib_fixture_unavailable', 'HLIB_EXTENSION_API = 1\ndef is_available(): return False\n')
        self.package('hlib_fixture_unmarked', '')
        hlib.reload()
        states = hlib.extensions.status()
        self.assertEqual(states['hlib_fixture_unavailable']['state'], 'unavailable')
        self.assertEqual(states['hlib_fixture_unmarked']['state'], 'skipped')

    def test_cross_extension_dependency_is_rejected_before_wrapper_import(self):
        """他拡張の継承・関数内importは登録前に拒否する。"""
        base = self.package('hlib_fixture_zbase', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(base, 'nodes', 'from hlib.nodes import Node\nfrom hlib.extensions import node_wrapper\n@node_wrapper("fixtureBase")\nclass Base(Node): pass\n')
        child = self.package('hlib_fixture_achild', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(child, 'nodes', 'from hlib_fixture_zbase.nodes.sample import Base\nfrom hlib.extensions import node_wrapper\n@node_wrapper("fixtureChild")\nclass Child(Base): pass\n')
        hlib.reload()
        self.assertEqual(hlib.extensions.status()['hlib_fixture_achild']['state'], 'error')
        self.assertNotIn('hlib_fixture_achild.nodes', sys.modules)
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureChild'))
        self.assertEqual(hlib.extensions.status()['hlib_fixture_zbase']['state'], 'loaded')

    def test_failed_import_recovers_on_first_reload(self):
        """親のimport失敗で孤立した子も更新し、探索パスから外した場合も解除する。"""
        name = 'hlib_fixture_recovery'
        path = self.package(name, 'from . import config\nraise RuntimeError("broken initialization")\n')
        (path / 'config.py').write_text('VALUE = 1\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib.extensions.status()[name]['state'], 'error')
        self.assertNotIn(name, sys.modules)
        self.assertIn(name + '.config', sys.modules)
        (path / 'config.py').write_text('VALUE = 22222\n', encoding='utf-8')
        (path / '__init__.py').write_text(
            'from . import config\nHLIB_EXTENSION_API = 1\n'
            'def is_available(): return config.VALUE == 22222\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib.extensions.status()[name]['state'], 'loaded')
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
        self.assertEqual(hlib.extensions.status()[name]['state'], 'unavailable')
        self.assertNotIn(name + '.implementation', sys.modules)
        (path / '__init__.py').write_text(
            'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n', encoding='utf-8')
        hlib.reload()
        self.assertEqual(hlib.extensions.status()[name]['state'], 'error')

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
            self.assertEqual(hlib.extensions.status()['hlib_fixture_afirst']['state'], 'loaded')
            self.assertIs(sys.modules[sdk.__name__], sdk)
        finally:
            sys.modules.pop(sdk.__name__, None)

    def test_reentrant_reload_preserves_modules(self):
        """初期化中のreload要求は、一部だけ解除せず拒否する。"""
        from unittest import mock
        self.package('hlib_fixture_reentry', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        hlib.reload()
        module = sys.modules['hlib_fixture_reentry']
        with mock.patch.object(hlib.extensions, '_loading', True):
            with self.assertRaises(RuntimeError):
                hlib.reload()
        self.assertIs(sys.modules['hlib_fixture_reentry'], module)

    def test_collision_is_atomic_and_errors_visible(self):
        path = self.package('hlib_fixture_conflict', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nfrom hlib.extensions import node_wrapper\n@node_wrapper("fixturePartial")\nclass Sample(Node): pass\n')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nfrom hlib.extensions import plug_wrapper\n@plug_wrapper("double3")\nclass Sample(Plug): pass\n')
        self.package('hlib_fixture_broken', 'HLIB_EXTENSION_API = 1\ndef is_available(): raise RuntimeError("SDK broken")\n')
        hlib.reload()
        states = hlib.extensions.status()
        self.assertEqual(states['hlib_fixture_conflict']['state'], 'error')
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixturePartial'))
        self.assertEqual(states['hlib_fixture_broken']['reason'], 'SDK broken')
        self.assertIsNotNone(hlib.nodes.Node._registry.lookup('transform'))

    def test_registration_failure_restores_both_registries(self):
        """登録途中の障害で先に登録したnodesと公開名も戻す。"""
        from unittest import mock
        path = self.package('hlib_fixture_atomic', 'HLIB_EXTENSION_API = 1\ndef is_available(): return True\n')
        self.wrappers(path, 'nodes', 'from hlib.nodes import Node\nfrom hlib.extensions import node_wrapper\n@node_wrapper("fixtureAtomicNode")\nclass AtomicNode(Node): pass\n')
        self.wrappers(path, 'plugs', 'from hlib.plugs import Plug\nfrom hlib.extensions import plug_wrapper\n@plug_wrapper("fixtureAtomicPlug")\nclass AtomicPlug(Plug): pass\n')
        registry = hlib.plugs.Plug._registry
        original = registry.register

        def reject(key, cls):
            """指定型の登録直後に障害を発生させる。"""
            original(key, cls)
            if key == 'fixtureAtomicPlug':
                raise RuntimeError('registration interrupted')

        with mock.patch.object(registry, 'register', side_effect=reject):
            hlib.extensions._initialize()
        self.assertIsNone(hlib.nodes.Node._registry.lookup('fixtureAtomicNode'))
        self.assertIsNone(registry.lookup('fixtureAtomicPlug'))
        self.assertFalse(hasattr(sys.modules['hlib_fixture_atomic.nodes'], 'AtomicNode'))
        self.assertEqual(hlib.extensions.status()['hlib_fixture_atomic']['state'], 'error')
        self.assertIsNotNone(hlib.nodes.Node._registry.lookup('transform'))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
