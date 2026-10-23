"""数学値の固定pickleとreload参照を検証する。"""

import base64
import copy
import importlib
import pickle
import sys
import unittest

from mlib import maths
from mlib import util

# protocol 2の固定データを現在のパッケージ名へ移行したpickle。
# 別プロセスで保存した関数パスと型の値を固定し、現在のpickle往復だけで代用しない。
_PICKLE_FIXTURES = [('Vector',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy52ZWN0b3IKVmVjdG9yCnEBRz/wAAAAAAAAR0AAAAAAAAAAR0AIAAAAAAAAh3EChnEDUnEELg=='),
 ('Translate',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy50cmFuc2xhdGUKVHJhbnNsYXRlCnEBRz/wAAAAAAAAR0AAAAAAAAAAR0AIAAAAAAAAh3EChnEDUnEELg=='),
 ('Scale',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy5zY2FsZQpTY2FsZQpxAUc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAIdxAoZxA1JxBC4='),
 ('Shear',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy5zaGVhcgpTaGVhcgpxAUc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAIdxAoZxA1JxBC4='),
 ('Quaternion',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy5xdWF0ZXJuaW9uClF1YXRlcm5pb24KcQEoRz+5mZmZmZmaRz/JmZmZmZmaRz/TMzMzMzMzRz/szMzMzMzNdHEChnEDUnEELg=='),
 ('EulerRotate',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy5ldWxlclJvdGF0ZQpFdWxlclJvdGF0ZQpxAShHP7mZmZmZmZpHP8mZmZmZmZpHP9MzMzMzMzNLBXRxAoZxA1JxBC4='),
 ('Matrix',
  'gAJjbWxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjbWxpYi5tYXRocy5tYXRyaXgKTWF0cml4CnEBKEcAAAAAAAAAAEc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAEdAEAAAAAAAAEdAFAAAAAAAAEdAGAAAAAAAAEdAHAAAAAAAAEdAIAAAAAAAAEdAIgAAAAAAAEdAJAAAAAAAAEdAJgAAAAAAAEdAKAAAAAAAAEdAKgAAAAAAAEdALAAAAAAAAEdALgAAAAAAAHRxAoZxA1JxBC4=')]


class MathRefactoringTest(unittest.TestCase):
    """保存済みデータと依存順の再読み込みを検証する。"""

    def test_current_package_pickle_rebuild_paths(self):
        """現在の名前で保存した7数学型の固定pickleを読み込む。"""
        for name, payload in _PICKLE_FIXTURES:
            value = pickle.loads(base64.b64decode(payload))
            self.assertIs(type(value), getattr(maths, name))
            self.assertEqual(value.__reduce_ex__(2)[0].__module__, "mlib.maths.vector")
            if name in ("Vector", "Translate", "Scale", "Shear"):
                self.assertEqual(tuple(value), (1.0, 2.0, 3.0))
            elif name == "Quaternion":
                self.assertEqual(tuple(value), (0.1, 0.2, 0.3, 0.9))
            elif name == "EulerRotate":
                self.assertEqual(tuple(value), (0.1, 0.2, 0.3))
                self.assertEqual(value.orderName, "zyx")
            else:
                self.assertEqual(value.values, tuple(float(index) for index in range(16)))

    def test_shared_helpers_reloaded_before_math_types(self):
        """依存順のreloadで新helperを全数学型へ渡し、判定cacheを再作成する。"""
        import mlib
        state_cache = util._STATEFUL_TYPES
        copy.copy(maths.Vector(1, 2, 3))
        self.assertTrue(state_cache)
        mlib.reload()
        current = importlib.import_module("mlib.util")
        self.assertIsNot(current._STATEFUL_TYPES, state_cache)
        for name in ("vector", "quaternion", "eulerRotate", "matrix"):
            module = importlib.import_module("mlib.maths." + name)
            self.assertIs(module._copy_state, current._copy_state)
            self.assertIs(module._checked_index, current._checked_index)
            self.assertIs(module._foreign_comparison, current._foreign_comparison)
        value = mlib.maths.Vector(1, 2, 3)
        self.assertEqual(tuple(copy.deepcopy(value)), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(pickle.loads(pickle.dumps(value))), (1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
