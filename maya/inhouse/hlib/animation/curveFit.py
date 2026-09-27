"""外部数値ライブラリなしで3次B-splineの制御点を近似する。"""

import math


class CurveFit:
    """等間隔clamped knotを持つ3次カーブの正則化最小二乗フィット。"""

    @staticmethod
    def basis(count, parameter):
        """0〜1のパラメータで基底重みを計算する。

        Args:
            count (int): 4以上のCV数。
            parameter (float): 正規化カーブパラメータ。

        Returns:
            list[float]: CVごとの重み。
        """
        if count < 4 or not 0 <= parameter <= 1:
            raise ValueError("Use count >= 4 and parameter in 0..1")
        if parameter == 1:
            return [0.0] * (count - 1) + [1.0]
        knots = [0.0] * 4 + [i / (count - 3) for i in range(1, count - 3)] + [1.0] * 4
        weights = [float(knots[i] <= parameter < knots[i + 1]) for i in range(len(knots) - 1)]
        for degree in range(1, 4):
            result = []
            for i in range(len(weights) - 1):
                left = knots[i + degree] - knots[i]
                right = knots[i + degree + 1] - knots[i + 1]
                result.append(
                    (weights[i] * (parameter - knots[i]) / left if left else 0)
                    + (weights[i + 1] * (knots[i + degree + 1] - parameter) / right if right else 0)
                )
            weights = result
        return weights

    @classmethod
    def fit(cls, points, count):
        """折れ線の弦長をパラメータとしてCVを近似する。

        Args:
            points (Sequence[Sequence[float]]): 同一空間・単位の3次元点、2点以上。
            count (int): CV数、4〜32。

        Returns:
            list[list[float]]: 同じ空間・単位のCV座標。

        Note:
            少ないサンプルでは直線配置へ弱く正則化する。折れ角や弧長の完全一致は保証しない。
        """
        if type(count) is not int or not 4 <= count <= 32 or len(points) < 2:
            raise ValueError("Expected >=2 points and 4..32 controls")
        if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
            raise ValueError("Expected finite 3D points")
        distances = [0.0]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))
        if distances[-1] <= 1e-10:
            raise ValueError("Point chain has zero length")
        basis = [cls.basis(count, d / distances[-1]) for d in distances]
        matrix = [[0.0] * (count + 3) for _ in range(count)]
        for row, point in zip(basis, points):
            for i in range(count):
                for j in range(count):
                    matrix[i][j] += row[i] * row[j]
                for axis in range(3):
                    matrix[i][count + axis] += row[i] * point[axis]
        for i in range(count):
            matrix[i][i] += 1e-7
            for axis in range(3):
                matrix[i][count + axis] += 1e-7 * (
                    points[0][axis] + (points[-1][axis] - points[0][axis]) * i / (count - 1)
                )
        for col in range(count):
            pivot = max(range(col, count), key=lambda r: abs(matrix[r][col]))
            matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
            scale = matrix[col][col]
            matrix[col] = [v / scale for v in matrix[col]]
            for row in range(count):
                if row != col:
                    scale = matrix[row][col]
                    matrix[row] = [a - scale * b for a, b in zip(matrix[row], matrix[col])]
        result = [row[count:] for row in matrix]
        result[0], result[-1] = list(points[0]), list(points[-1])
        return result
