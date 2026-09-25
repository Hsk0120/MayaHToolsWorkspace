"""任意拡張の自動検出・依存不在・衝突・再読み込みを検証する。"""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest

import hlib


class ExtensionsTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
