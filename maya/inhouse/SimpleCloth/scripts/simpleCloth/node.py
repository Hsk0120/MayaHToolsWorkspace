"""Simple ClothのメッシュDGノード。固定刻みの履歴をノードごとに所有する。"""

import json
import math

from maya.api import OpenMaya as om

from . import solver


# name: (default, minimum, maximum)。長さは常にcm、時間は秒。
SCALARS = {
    "maxDistance": (30.0, 0.0, None),
    "stretchCompliance": (0.000001, 0.0, None),
    "bendCompliance": (0.01, 0.0, None),
    "particleMass": (0.1, 0.000001, None),
    "damping": (2.0, 0.0, None),
    "animDrive": (0.0, 0.0, None),
    "backstopRadius": (0.0, 0.0, None),
    "backstopDistance": (0.0, None, None),
    "collisionThickness": (0.2, 0.0, None),
    "selfCollisionThickness": (0.2, 0.0, None),
    "friction": (0.1, 0.0, 1.0),
    "blend": (1.0, 0.0, 1.0),
    "solverRate": (120.0, 1.0, 480.0),
}
INTEGERS = {"iterations": (8, 1, 100), "maxSteps": (4000, 1, 20000), "resetSerial": (0, 0, None)}
OUTPUTS = ("outputMesh", "stretchError", "residualPenetration", "maxDistanceError")


class SimpleClothNode(om.MPxNode):
    """静止トポロジーとアニメーションメッシュから独立した布メッシュを生成する。"""

    TYPE_NAME = "simpleClothSolver"
    # 開発用ID。配布時にはAutodeskの正式割当てIDへ置き換える。
    TYPE_ID = om.MTypeId(0x0007F7A1)
    attributes = {}

    def __init__(self):
        """Mayaが所有するインスタンスの再生キャッシュを初期化する。"""
        super().__init__()
        self._signature = None
        self._cache = []

    @classmethod
    def creator(cls):
        """登録したクラスのインスタンスをMayaへ渡す。"""
        return cls()

    @classmethod
    def initialize(cls):
        """保存可能な入力、ペイント用配列、メッシュ出力を定義する。"""
        cls.attributes = {}

        def register(name, attribute):
            """アトリビュートを登録し、compute用の参照を保持する。"""
            cls.addAttribute(attribute)
            cls.attributes[name] = attribute

        for values, kind in ((SCALARS, om.MFnNumericData.kDouble), (INTEGERS, om.MFnNumericData.kInt)):
            for name, (default, minimum, maximum) in values.items():
                function = om.MFnNumericAttribute()
                attribute = function.create(name, name, kind, default)
                if minimum is not None:
                    function.setMin(minimum)
                if maximum is not None:
                    function.setMax(maximum)
                register(name, attribute)
        function = om.MFnNumericAttribute()
        register("selfCollision", function.create("selfCollision", "selfCollision", om.MFnNumericData.kBoolean, False))
        for name in ("time", "startFrame"):
            function = om.MFnUnitAttribute()
            register(name, function.create(name, name, om.MFnUnitAttribute.kTime, 0.0))
        for name, default in (("gravity", (0, -980, 0)), ("wind", (0, 0, 0))):
            function = om.MFnNumericAttribute()
            attribute = function.createPoint(name, name)
            function.default = default
            register(name, attribute)
        for name, default in (("referenceData", "{}"), ("colliderTypes", "[]")):
            function = om.MFnTypedAttribute()
            register(name, function.create(name, name, om.MFnData.kString, om.MFnStringData().create(default)))
        function = om.MFnTypedAttribute()
        register("maxDistanceMap", function.create("maxDistanceMap", "maxDistanceMap", om.MFnData.kDoubleArray))
        for name in ("inputMesh", "outputMesh"):
            function = om.MFnTypedAttribute()
            attribute = function.create(name, name, om.MFnData.kMesh)
            function.storable = False
            function.writable = name != "outputMesh"
            register(name, attribute)
        function = om.MFnMatrixAttribute()
        register("inputMatrix", function.create("inputMatrix", "inputMatrix"))
        function = om.MFnMatrixAttribute()
        attribute = function.create("colliderMatrix", "colliderMatrix")
        function.array = True
        register("colliderMatrix", attribute)
        for name in ("colliderRadius", "colliderHeight"):
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.kDouble, 0)
            function.array = True
            function.setMin(0)
            register(name, attribute)
        for name in OUTPUTS[1:]:
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.kDouble, 0)
            function.storable = False
            function.writable = False
            register(name, attribute)
        for name, attribute in cls.attributes.items():
            if name not in OUTPUTS:
                for output in OUTPUTS:
                    cls.attributeAffects(attribute, cls.attributes[output])

    def schedulingType(self):
        """時間コンテキストでの入力サンプルとキャッシュ更新を直列化する。"""
        return om.MPxNode.kGloballySerial

    def _sample(self, time, reference, kinds):
        """指定時刻の接続元メッシュとコライダーを読み、編集検出キーを返す。"""
        context = om.MDGContext(om.MTime(time, om.MTime.kSeconds))
        function = om.MFnDependencyNode(self.thisMObject())
        mesh_plug = function.findPlug("inputMesh", False)
        if not mesh_plug.isDestination:
            raise ValueError("Simple Cloth: 入力メッシュが接続されていません")
        mesh = om.MFnMesh(mesh_plug.source().asMObject(context))
        counts, vertices = mesh.getVertices()
        if list(counts) != reference["counts"] or list(vertices) != reference["vertices"]:
            raise ValueError("Simple Cloth: 入力トポロジーが変わりました。セットアップを作り直してください")
        matrix_plug = function.findPlug("inputMatrix", False)
        if not matrix_plug.isDestination:
            raise ValueError("Simple Cloth: 入力のワールドマトリクスが接続されていません")
        matrix = om.MFnMatrixData(matrix_plug.source().asMObject(context)).matrix()
        if abs(matrix.det4x4()) < 1.0e-10:
            raise ValueError("Simple Cloth: 入力にゼロスケールは使用できません")
        points = [om.MVector(point * matrix) for point in mesh.getPoints()]
        normal_matrix = matrix.inverse().transpose()
        normals = [(om.MVector(normal) * normal_matrix).normal() for normal in mesh.getVertexNormals(False)]
        colliders = []
        for index, kind in enumerate(kinds):
            plug = function.findPlug("colliderMatrix", False).elementByLogicalIndex(index)
            if not plug.isDestination:
                raise ValueError("Simple Cloth: コライダーの接続がありません。専用UIから削除してください")
            matrix = om.MFnMatrixData(plug.source().asMObject(context)).matrix()
            transform = om.MTransformationMatrix(matrix)
            scale = transform.scale(om.MSpace.kTransform)
            shear = transform.shear(om.MSpace.kTransform)
            if min(scale) <= 0 or max(scale) - min(scale) > 1.0e-5 or any(abs(value) > 1.0e-5 for value in shear):
                raise ValueError("Simple Cloth: コライダーには正の均等スケール・シアーなしを使用してください")
            sizes = []
            for name in ("colliderRadius", "colliderHeight"):
                plug = function.findPlug(name, False).elementByLogicalIndex(index)
                sizes.append((plug.source() if plug.isDestination else plug).asDouble(context))
            colliders.append((matrix, kind, *sizes))
        key = (tuple(tuple(point) for point in points), tuple(tuple(normal) for normal in normals),
               tuple((tuple(matrix), kind, radius, height) for matrix, kind, radius, height in colliders))
        return points, normals, colliders, key

    def compute(self, plug, data):
        """過去入力の編集を照合し、固定刻み+端数ステップで指定時刻を評価する。"""
        attrs = self.attributes
        if plug.attribute() not in tuple(attrs[name] for name in OUTPUTS):
            return None
        mesh_object = data.inputValue(attrs["inputMesh"]).asMesh()
        reference_text = data.inputValue(attrs["referenceData"]).asString()
        reference = json.loads(reference_text)
        if mesh_object.isNull() or not reference:
            return None
        settings = {name: data.inputValue(attrs[name]).asDouble() for name in SCALARS}
        settings.update({name: data.inputValue(attrs[name]).asInt() for name in INTEGERS})
        settings["selfCollision"] = data.inputValue(attrs["selfCollision"]).asBool()
        for name in ("gravity", "wind"):
            settings[name] = tuple(data.inputValue(attrs[name]).asFloat3())
        # 係数はショット全体で一定。時変係数を現在値で過去へ適用する曖昧さを拒否する。
        function = om.MFnDependencyNode(self.thisMObject())
        for name in tuple(SCALARS) + tuple(INTEGERS) + ("selfCollision", "gravity", "wind", "startFrame", "maxDistanceMap"):
            setting_plug = function.findPlug(name, False)
            children = [setting_plug.child(index) for index in range(setting_plug.numChildren())] if setting_plug.isCompound else []
            if setting_plug.isDestination or any(child.isDestination for child in children):
                raise ValueError(f"Simple Cloth: {name}は固定設定です。入力メッシュまたはコライダーをアニメーションしてください")
        if any(not math.isfinite(value) for name in SCALARS for value in (settings[name],)) or any(
                not math.isfinite(value) for name in ("gravity", "wind") for value in settings[name]):
            raise ValueError("Simple Cloth: 設定には有限値を指定してください")
        array = data.inputValue(attrs["maxDistanceMap"]).data()
        weights = list(om.MFnDoubleArrayData(array).array()) if not array.isNull() else []
        if len(weights) != len(reference["points"]) or any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
            raise ValueError("Simple Cloth: Max Distance Mapは各頂点に0〜1を指定してください")
        kinds = json.loads(data.inputValue(attrs["colliderTypes"]).asString())
        if any(kind not in (0, 1, 2) for kind in kinds):
            raise ValueError("Simple Cloth: 未対応のコライダー種別です")
        start = data.inputValue(attrs["startFrame"]).asTime().asUnits(om.MTime.kSeconds)
        time = data.inputValue(attrs["time"]).asTime().asUnits(om.MTime.kSeconds)
        signature = repr((reference_text, weights, settings, kinds, start))
        if self._signature != signature:
            self._cache = []
            self._signature = signature
        rest = [om.MVector(point) for point in reference["points"]]
        constraints = solver.build_constraints(rest, reference["triangles"])
        dt = 1.0 / settings["solverRate"]
        elapsed = max(0.0, time - start)
        steps = int(math.floor(elapsed / dt + 1.0e-7))
        if steps > settings["maxSteps"]:
            raise ValueError("Simple Cloth: Max Stepsを超えました。開始フレームと範囲を見直してください")
        state = None
        for index in range(steps + 1):
            sample_time = min(time, start) if index == 0 else start + index * dt
            targets, normals, colliders, key = self._sample(sample_time, reference, kinds)
            if index < len(self._cache) and self._cache[index][0] == key:
                state = self._cache[index][1]
            else:
                del self._cache[index:]
                state = (targets, [om.MVector() for _ in targets]) if index == 0 else solver.step(
                    state, targets, normals, weights, constraints, colliders, settings, dt)
                self._cache.append((key, state))
        remainder = elapsed - steps * dt
        if remainder > 1.0e-7:
            targets, normals, colliders, _ = self._sample(time, reference, kinds)
            state = solver.step(state, targets, normals, weights, constraints, colliders, settings, remainder)
        points = [target + (point - target) * settings["blend"] for target, point in zip(targets, state[0])]
        output = om.MFnMeshData().create()
        copied = om.MFnMesh().copy(mesh_object, output)
        om.MFnMesh(copied).setPoints(om.MPointArray([om.MPoint(point) for point in points]))
        data.outputValue(attrs["outputMesh"]).setMObject(output)
        errors = solver.diagnostics(points, targets, weights, constraints, colliders, settings)
        for name, value in zip(OUTPUTS[1:], errors):
            data.outputValue(attrs[name]).setDouble(value)
        for name in OUTPUTS:
            data.setClean(attrs[name])
        return self
