"""hlib JSONの形式とバージョン。"""
from dataclasses import dataclass, field


@dataclass
class JsonDocument:
    """任意データと明示指定のメタデータ。ユーザー名やシーンパスは自動収集しない。"""
    data: object
    metadata: dict = field(default_factory=dict)

    def toData(self):
        """形式バージョン1のJSON基本値を返す。"""
        from .codec import encode
        return {"format": "hlib.json", "version": 1, "metadata": encode(self.metadata), "data": encode(self.data)}

    @classmethod
    def fromData(cls, value):
        """形式・版を検証して読み込む。未対応版はValueError。

        Args:
            value (dict): format、version、metadata、data を持つ保存データ。

        Returns:
            JsonDocument: 復号した値とメタデータを持つドキュメント。
        """
        from .codec import decode
        if not isinstance(value, dict) or value.get("format") != "hlib.json" or type(value.get("version")) is not int or value["version"] != 1:
            raise ValueError("Unsupported hlib JSON format/version")
        metadata = decode(value["metadata"])
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")
        return cls(decode(value["data"]), metadata)
