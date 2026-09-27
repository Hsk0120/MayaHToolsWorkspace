"""部位空間の距離を扱うSoft IK。伸長なし、softnessは距離単位。"""

import math


def softened_distance(distance, length, softness):
    """到達距離を連続に減衰する参照実装。

    Args:
        distance (float): 根元から目標までの距離。
        length (float): 2本の骨長の和。
        softness (float): 0以上、全長以下の減衰範囲。

    Returns:
        float: 部位空間の減衰後の距離。入力と同じ距離単位。

    Raises:
        ValueError: 非有限値、負の距離、不正な骨長や減衰範囲の場合。
    """
    if not all(math.isfinite(v) for v in (distance, length, softness)):
        raise ValueError("Expected finite parameters")
    if distance < 0 or length <= 0 or not 0 <= softness <= length:
        raise ValueError("Invalid Soft IK parameters")
    threshold = length - softness
    if softness == 0 or distance <= threshold:
        return min(distance, length)
    return threshold + softness * (1 - math.exp(-(distance - threshold) / softness))


def build_graph(name, length):
    """Bifrostで距離・softnessから目標位置倍率を計算するグラフを構築する。

    Args:
        name (str): DGグラフ名。
        length (float): 正の固定チェーン長。

    Returns:
        Graph: distance、softness入力とratio出力を持つグラフ。
    """
    from hlib_bifrost import Graph

    if not math.isfinite(length) or length <= 0:
        raise ValueError("length must be positive and finite")
    graph = Graph.create(name)
    try:
        return _populate_graph(graph, length)
    except Exception:
        from maya import cmds
        import hlib

        parent = cmds.listRelatives(graph.name(), parent=True, fullPath=True)[0]
        hlib.delete(parent)
        raise


def _populate_graph(graph, length):
    """作成済みグラフへSoft IK演算を追加する。

    Args:
        graph (Graph): 空のBifrostグラフ。
        length (float): 正のチェーン長。距離はシーン単位。


    Returns:
        Graph: 演算を追加したグラフ。
    """
    from hlib_bifrost import Port

    root = graph.root
    root.add_port("distance", "float")
    root.add_port("softness", "float")
    root.add_port("ratio", "float", output=True)

    def feed(value, port):
        """定数またはポートを演算入力へ割り当てる。

        Args:
            value (float | Port): 入力する値または接続元。
            port (Port): 接続先のポート。
        """
        if isinstance(value, Port):
            value.connect(port)
        else:
            port.set_default(value)

    def multi(kind, values, output="output"):
        """同型の可変数入力演算を追加する。

        Args:
            kind (str): Core::Mathの演算名。
            values (Sequence[float | Port]): 入力する定数またはポート。
            output (str): 結果ポート名。既定はoutput。


        Returns:
            Port: 生成した演算の結果ポート。
        """
        node = root.add_node("BifrostGraph,Core::Math," + kind)
        for index, value in enumerate(values):
            feed(value, node.add_port("v" + str(index), "float"))
        return node.port(output)

    def clamp(value, low, high):
        """既存clamp Compoundへ固定ポートで接続する。

        Args:
            value (float | Port): 制限対象。
            low (float | Port): 下限。
            high (float | Port): 上限。


        Returns:
            Port: 制限後の結果ポート。
        """
        node = root.add_node("BifrostGraph,Core::Math,clamp")
        for key, val in (("value", value), ("min", low), ("max", high)):
            feed(val, node.port(key))
        return node.port("clamped")

    distance = multi("max", (root.io_port("distance"), 0.000001), "maximum")
    soft = clamp(root.io_port("softness"), 0.000001, length)
    threshold = multi("subtract", (length, soft))
    excess = multi("max", (multi("subtract", (distance, threshold)), 0), "maximum")
    exponent = multi("divide", (multi("multiply", (-1, excess)), soft))
    power = root.add_node("BifrostGraph,Core::Math,power")
    feed(math.e, power.port("base"))
    feed(exponent, power.port("exponent"))
    softened = multi(
        "add", (threshold, multi("multiply", (soft, multi("subtract", (1, power.port("power"))))))
    )
    limited = multi("min", (distance, softened), "minimum")
    multi("divide", (limited, distance)).connect(root.io_port("ratio", output=True))
    return graph
