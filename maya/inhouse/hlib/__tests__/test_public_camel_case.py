"""公開名の表記とreload後の廃止名除去を検証する。"""

import ast
import importlib
from pathlib import Path
import unittest

import hlib


class PublicCamelCaseTest(unittest.TestCase):
    """内部実装と公開APIを分けて命名規約を検査する。"""

    def test_public_definitions_use_camel_case(self):
        """UI内部基底から継承する公開メソッドも対象にする。"""
        root = Path(hlib.__file__).parent
        failures = []
        inherited_bases = {'_Editor', '_WindowReference'}
        for path in root.rglob('*.py'):
            relative = path.relative_to(root)
            if any(part in ('__tests__', 'docs', '_core') for part in relative.parts):
                continue
            if path.stem.startswith('_') and path.stem not in ('_editor', '_windowReference'):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    if node.name.startswith('_') and node.name not in inherited_bases:
                        continue
                    definitions = node.body
                else:
                    definitions = [node]
                for definition in definitions:
                    if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    name = definition.name
                    if name.startswith('_'):
                        continue
                    if path.name == 'logger.py' and name in ('get_logger', 'raise_with_notify'):
                        continue
                    if '_' in name:
                        failures.append('{}:{} {}'.format(relative, definition.lineno, name))
        self.assertEqual(failures, [])

    def test_reload_discards_old_public_functions(self):
        """旧版を読み込んだセッションを模して廃止名の残留を検出する。"""
        cases = (
            ('hlib.decorators', 'undo_chunk', 'undoChunk'),
            ('hlib.decorators.undo', 'undo_transaction', 'undoTransaction'),
            ('hlib.utils', 'progress_bar', 'progressBar'),
            ('hlib.utils.units', 'distance_to_ui', 'distanceToUi'),
            ('hlib.json', 'load_document', 'loadDocument'),
            ('hlib.json.storage', 'load_document', 'loadDocument'),
            ('hlib.environment.module', 'is_at_least', 'Module'),
            ('hlib.environment.plugin', 'is_at_least', 'Plugin'),
            ('hlib.environment.pluginPackage', 'is_at_least', 'PluginPackage'),
        )
        for module_name, old, new in cases:
            module = importlib.import_module(module_name)
            setattr(module, old, object())
        hlib.reload()
        for module_name, old, new in cases:
            module = importlib.import_module(module_name)
            with self.subTest(module=module_name):
                self.assertNotIn(old, vars(module))
                self.assertTrue(callable(getattr(module, new)))

    def test_properties_and_storage_keep_distinct_contracts(self):
        """保持propertyを改名しても構築引数と保存データは変えない。"""
        from hlib.environment import PluginPackage
        from hlib.json.document import JsonDocument
        package = PluginPackage('Example', plugins=('example',), minimum_version='3.0', minimum_maya=2025)
        self.assertEqual(package.minimumVersion.parts, (3, 0))
        self.assertEqual(package.minimumMaya, 2025)
        self.assertNotIn('minimum_version', vars(type(package)))
        document = JsonDocument({'minimum_version': 'saved', 'palette_source': 'saved'})
        restored = JsonDocument.fromData(document.toData())
        self.assertEqual(restored.data, document.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
