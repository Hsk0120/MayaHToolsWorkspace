"""公開名の表記とreload後の廃止名除去を検証する。"""

import ast
import importlib
from pathlib import Path
import unittest

import mlib


class PublicCamelCaseTest(unittest.TestCase):
    """内部実装と公開APIを分けて命名規約を検査する。"""

    def test_public_definitions_use_camel_case(self):
        """公開クラスと関数を対象に命名規約を検査する。"""
        root = Path(mlib.__file__).parent
        failures = []
        for path in root.rglob('*.py'):
            relative = path.relative_to(root)
            if any(part in ('__tests__', '_docs') for part in relative.parts):
                continue
            if path.stem.startswith('_'):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            # フォルダ名で内部扱いにせず、関数の公開は明示一覧から判定する。
            exported = set()
            for statement in tree.body:
                if isinstance(statement, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == '__all__'
                        for target in statement.targets):
                    try:
                        exported = set(ast.literal_eval(statement.value))
                    except (ValueError, TypeError):
                        pass
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    if node.name.startswith('_'):
                        continue
                    definitions = node.body
                else:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in exported:
                        continue
                    definitions = [node]
                for definition in definitions:
                    if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    name = definition.name
                    if name.startswith('_'):
                        continue
                    if path.name == 'logger.py' and name in ('get_logger', 'raise_with_notify'):
                        continue
                    # 既存の型登録/値読出し/reloadプロトコルは配置変更で改名しない。
                    if (relative.as_posix(), getattr(node, 'name', None), name) in {
                            ('core/registry.py', 'NodeRegistry', 'wrapper_class'),
                            ('core/attributeType.py', 'is_internal_data_type', 'is_internal_data_type'),
                            ('core/attributeType.py', 'value_reader', 'value_reader'),
                            ('core/reload.py', 'reload_package', 'reload_package')}:
                        continue
                    if '_' in name:
                        failures.append('{}:{} {}'.format(relative, definition.lineno, name))
        self.assertEqual(failures, [])

    def test_reload_discards_old_public_functions(self):
        """旧版を読み込んだセッションを模して廃止名の残留を検出する。"""
        cases = (
            ('mlib.decorator', 'undo_chunk', 'undoChunk'),
            ('mlib.decorator', 'undo_transaction', 'undoTransaction'),
            ('mlib.common', 'progress_bar', 'progressBar'),
            ('mlib.common.units', 'distance_to_ui', 'distanceToUi'),
            ('mlib.common.module', 'is_at_least', 'Module'),
            ('mlib.common.plugin', 'is_at_least', 'Plugin'),
            ('mlib.common.pluginPackage', 'is_at_least', 'PluginPackage'),
        )
        for module_name, old, new in cases:
            module = importlib.import_module(module_name)
            setattr(module, old, object())
        mlib.reload()
        for module_name, old, new in cases:
            module = importlib.import_module(module_name)
            with self.subTest(module=module_name):
                self.assertNotIn(old, vars(module))
                self.assertTrue(callable(getattr(module, new)))

    def test_properties_keep_constructor_contracts(self):
        """保持propertyの表記にかかわらず構築引数を維持する。"""
        from mlib.common import PluginPackage
        package = PluginPackage('Example', plugins=('example',), minimum_version='3.0', minimum_maya=2025)
        self.assertEqual(package.minimumVersion.parts, (3, 0))
        self.assertEqual(package.minimumMaya, 2025)
        self.assertNotIn('minimum_version', vars(type(package)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
