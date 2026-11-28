"""Maya DGとSimple Physics計算を接続する。

入力階層をMDGContextでサンプルし、変更された最初のステップ以降だけ再計算する。
過去サンプルも毎回照合するため、アニメーション編集・逆方向の時刻指定を検出できる。
キャッシュはノードインスタンスが所有し、明示的に読み込んだ再開状態はシーンにも保存する。
"""

import json
import math

from maya.api import OpenMaya as om

from . import solver


DEFAULTS = {
    "damping": 0.1, "stiffness": 0.05,
    "worldDampingLocation": 0.8, "worldDampingRotation": 0.8,
    "radius": 3.0, "limitAngle": 0.0,
    "blend": 1.0, "targetFramerate": 60.0, "teleportDistance": 100.0,
}
INTEGERS = {"iterationsBefore": 1, "iterationsAfter": 1, "collisionIterations": 4,
            "warmupSteps": 0, "maxSteps": 20000, "resetSerial": 0}


class SimplePhysicsNode(om.MPxNode):
    """入力アニメーションとは独立した出力階層用マトリクスを生成する。"""

    TYPE_NAME = "simplePhysicsSolver"
    # 開発用ID。商用配布前にAutodeskから割当てを取得する。
    TYPE_ID = om.MTypeId(0x0007F7A0)
    attributes = {}

    def __init__(self):
        """このノードだけが所有する再生キャッシュを初期化する。"""
        super().__init__()
        self._signature = None
        self._cache = []
        self._cache_origin = None

    @classmethod
    def creator(cls):
        """Mayaが所有するノードインスタンスを生成する。"""
        return cls()

    @classmethod
    def _register(cls, name, attribute):
        """アトリビュートをクラスに保持してMayaへ登録する。"""
        cls.attributes[name] = attribute
        cls.addAttribute(attribute)

    @classmethod
    def initialize(cls):
        """シーン保存可能な入力と計算出力を定義する。"""
        inputs = []
        for name, default in DEFAULTS.items():
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.kDouble, default)
            function.setMin(1.0 if name == "targetFramerate" else 0.0)
            if name in ("damping", "stiffness", "worldDampingLocation", "worldDampingRotation", "blend"):
                function.setMax(1.0)
            if name == "targetFramerate":
                function.setMax(480.0)
            if name == "limitAngle":
                function.setMax(180.0)
            cls._register(name, attribute)
            inputs.append(attribute)
        for name, default in INTEGERS.items():
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.kInt, default)
            function.setMin(1 if name in ("maxSteps", "collisionIterations") else 0)
            cls._register(name, attribute)
            inputs.append(attribute)
        for name in ("time", "startFrame"):
            function = om.MFnUnitAttribute()
            attribute = function.create(name, name, om.MFnUnitAttribute.kTime, 0.0)
            cls._register(name, attribute)
            inputs.append(attribute)
        for name, default in (("gravity", (0, -980, 0)), ("wind", (0, 0, 0))):
            function = om.MFnNumericAttribute()
            attribute = function.createPoint(name, name)
            function.default = default
            cls._register(name, attribute)
            inputs.append(attribute)
        for name, default in (("topology", "[]"), ("boneConstraints", "[]"), ("colliderTypes", "[]"), ("resumeState", ""), ("settledOffsets", ""), ("hingeLimits", "{}")):
            function = om.MFnTypedAttribute()
            attribute = function.create(name, name, om.MFnData.kString, om.MFnStringData().create(default))
            cls._register(name, attribute)
            inputs.append(attribute)
        function = om.MFnEnumAttribute()
        attribute = function.create("planarConstraint", "planarConstraint", 0)
        for index, name in enumerate(("None", "X", "Y", "Z")):
            function.addField(name, index)
        cls._register("planarConstraint", attribute)
        inputs.append(attribute)
        field_attr = om.MFnTypedAttribute()
        attr = field_attr.create("fieldForces", "fieldForces", om.MFnData.kVectorArray)
        field_attr.array = True
        field_attr.storable = False
        cls._register("fieldForces", attr)
        inputs.append(attr)
        for name in ("inputMatrix", "colliderMatrix", "outputMatrix"):
            function = om.MFnMatrixAttribute()
            attribute = function.create(name, name)
            function.array = True
            function.usesArrayDataBuilder = True
            function.writable = name != "outputMatrix"
            function.storable = name != "outputMatrix"
            cls._register(name, attribute)
            if name != "outputMatrix":
                inputs.append(attribute)
        for name in ("colliderRadius", "colliderHeight"):
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.kDouble, 0)
            function.array = True
            function.setMin(0)
            cls._register(name, attribute)
            inputs.append(attribute)
        for name in solver.PARAMETERS:
            attribute = om.MRampAttribute.createCurveRamp(name + "Curve", name + "Curve")
            cls._register(name + "Curve", attribute)
            inputs.append(attribute)
        for name in ("particlePosition", "velocityEndpoint"):
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, om.MFnNumericData.k3Double)
            function.array = True
            function.usesArrayDataBuilder = True
            function.writable = False
            function.storable = False
            cls._register(name, attribute)
        for name, kind in (("residualPenetration", om.MFnNumericData.kDouble), ("maxParticleSpeed", om.MFnNumericData.kDouble),
                           ("fixedRootCount", om.MFnNumericData.kInt), ("contactParticleCount", om.MFnNumericData.kInt)):
            function = om.MFnNumericAttribute()
            attribute = function.create(name, name, kind, 0)
            function.writable = False
            function.storable = False
            cls._register(name, attribute)
        for attribute in inputs:
            for output in ("particlePosition", "velocityEndpoint", "outputMatrix", "residualPenetration", "maxParticleSpeed", "fixedRootCount", "contactParticleCount"):
                cls.attributeAffects(attribute, cls.attributes[output])

    def schedulingType(self):
        """時間サンプルとインスタンスキャッシュの同時更新を避ける。"""
        return om.MPxNode.kGloballySerial

    def _sample(self, context, topology, collider_types):
        """接続元を指定時刻で読む。出力階層を入力へ接続しないこと。"""
        function = om.MFnDependencyNode(self.thisMObject())

        def matrix_at(name, index):
            """接続元の評価コンテキストにおけるマトリクスを取得する。"""
            plug = function.findPlug(name, False).elementByLogicalIndex(index)
            if not plug.isDestination:
                raise ValueError(f"Simple Physics: {name}[{index}]の接続元がありません。セットアップを確認してください")
            source = plug.source()
            return om.MFnMatrixData(source.asMObject(context)).matrix()

        def number_at(name, index):
            """接続されたコライダー寸法をサンプルする。"""
            plug = function.findPlug(name, False).elementByLogicalIndex(index)
            source = plug.source() if plug.isDestination else plug
            return source.asDouble(context)

        poses = []
        for index, bone in enumerate(topology):
            if "dummyOffset" in bone:
                parent_pose = poses[bone["parent"]]
                offset = om.MMatrix()
                transform = om.MTransformationMatrix(offset)
                transform.setTranslation(om.MVector(bone["dummyOffset"]), om.MSpace.kTransform)
                poses.append(transform.asMatrix() * parent_pose)
            else:
                poses.append(matrix_at("inputMatrix", index))
        colliders = []
        for index, kind in enumerate(collider_types):
            matrix = matrix_at("colliderMatrix", index)
            transform = om.MTransformationMatrix(matrix)
            scale = transform.scale(om.MSpace.kTransform)
            shear = transform.shear(om.MSpace.kTransform)
            if min(scale) <= 0 or max(scale) - min(scale) > 1.0e-5 or any(abs(value) > 1.0e-5 for value in shear):
                raise ValueError("Simple Physics: コライダーはシアーなし・正の均等スケールを使用してください")
            colliders.append((matrix, kind, number_at("colliderRadius", index), number_at("colliderHeight", index)))
        key = tuple(tuple(matrix) for matrix in poses) + tuple((tuple(m), k, r, h) for m, k, r, h in colliders)
        return poses, colliders, key

    def compute(self, plug, data):
        """要求時刻まで固定刻みで評価し、同じ時刻の要求で状態を進めない。"""
        if plug.attribute() not in (self.attributes["particlePosition"], self.attributes["velocityEndpoint"], self.attributes["outputMatrix"], self.attributes["residualPenetration"],
                                    self.attributes["maxParticleSpeed"], self.attributes["fixedRootCount"], self.attributes["contactParticleCount"]):
            return None
        attrs = self.attributes
        topology_text = data.inputValue(attrs["topology"]).asString()
        topology = json.loads(topology_text)
        if not topology:
            return
        parents = [bone["parent"] for bone in topology]
        if any(parent < -1 or parent >= index for index, parent in enumerate(parents)):
            raise ValueError("Simple Physics: 不正な親インデックスです")
        options = {name: data.inputValue(attrs[name]).asDouble() for name in DEFAULTS}
        options.update({name: data.inputValue(attrs[name]).asInt() for name in INTEGERS})
        options["planarConstraint"] = data.inputValue(attrs["planarConstraint"]).asShort()
        for name in ("gravity", "wind"):
            options[name] = tuple(data.inputValue(attrs[name]).asFloat3())
        constraints = json.loads(data.inputValue(attrs["boneConstraints"]).asString())
        for first, second, length, compliance in constraints:
            if not (0 <= first < len(parents) and 0 <= second < len(parents)) or first == second or length <= 0 or compliance < 0:
                raise ValueError("Simple Physics: 不正な距離拘束です")
        # 除外チェーンの点は入力に固定し、枝をまたぐ距離拘束は復帰時まで休止する。
        active = [not bone.get("excluded", False) for bone in topology]
        simulation_parents = [parent if enabled else -1 for parent, enabled in zip(parents, active)]
        constraints = [pair for pair in constraints if active[pair[0]] and active[pair[1]]]
        collider_types = json.loads(data.inputValue(attrs["colliderTypes"]).asString())
        if any(kind not in (0, 1, 2) for kind in collider_types):
            raise ValueError("Simple Physics: 未対応のコライダーです")
        settings = []
        ramps = {name: om.MRampAttribute(self.thisMObject(), attrs[name + "Curve"]) for name in solver.PARAMETERS}
        for bone in topology:
            values = {}
            for name in solver.PARAMETERS:
                multiplier = ramps[name].getValueAtPosition(bone["rate"])
                value = max(0.0, options[name] * multiplier)
                if name in ("damping", "stiffness", "worldDampingLocation", "worldDampingRotation"):
                    value = min(value, 1.0)
                if name == "limitAngle" and options[name] > 0:
                    value = max(1.0e-5, min(value, 180.0))
                values[name] = value
            settings.append(values)
        time = data.inputValue(attrs["time"]).asTime().asUnits(om.MTime.kSeconds)
        start = data.inputValue(attrs["startFrame"]).asTime().asUnits(om.MTime.kSeconds)
        settled = json.loads(data.inputValue(attrs["settledOffsets"]).asString() or "null")
        hinges = json.loads(data.inputValue(attrs["hingeLimits"]).asString() or "{}")
        for index, bone in enumerate(topology):
            if str(index) in hinges:
                settings[index]["hinge"] = hinges[str(index)]
        signature = repr((topology_text, settings, options, constraints, collider_types, start))
        if settled:
            signature += repr(settled)
        function = om.MFnDependencyNode(self.thisMObject())
        field_plug = function.findPlug("fieldForces", False)
        if any(field_plug.elementByLogicalIndex(i).isDestination for i in field_plug.getExistingArrayAttributeIndices()):
            # Static Maya field parameters and world transforms take part in replay/checkpoint validation.
            import mayaParticleFields
            options["sceneFields"], field_signature = mayaParticleFields.samplers(function)
            signature += repr(field_signature)
        if signature != self._signature:
            self._signature = signature
            self._cache = []
        dt = 1.0 / options["targetFramerate"]
        options["previousDt"] = dt
        elapsed = max(0.0, time - start)
        steps = int(math.floor(elapsed / dt + 1.0e-7))
        if steps > options["maxSteps"]:
            raise ValueError("Simple Physics: 開始時刻からのステップ数がMax Stepsを超えています")
        poses = []
        state = None
        colliders = []
        first = 0
        encoded = data.inputValue(attrs["resumeState"]).asString()
        saved = json.loads(encoded) if encoded else None
        if (saved and time >= start and 0 <= saved["step"] <= steps and saved["signature"] == signature
                and saved["solver"] == om.MFnDependencyNode(self.thisMObject()).uuid().asString()
                and saved["fps"] == 1.0 / om.MTime(1, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds)):
            sample_time = start + saved["step"] * dt
            context = om.MDGContext(om.MTime(sample_time, om.MTime.kSeconds))
            _, _, key = self._sample(context, topology, collider_types)
            if json.dumps(key) == saved["sample"]:
                first = saved["step"]
            else:
                saved = None
        else:
            saved = None
        origin = (first, encoded if saved else "")
        if origin != self._cache_origin:
            self._cache_origin = origin
            self._cache = []
        for index in range(first, steps + 1):
            slot = index - first
            sample_time = min(time, start) if index == 0 else start + index * dt
            sample_poses, sample_colliders, key = self._sample(om.MDGContext(om.MTime(sample_time, om.MTime.kSeconds)), topology, collider_types)
            if slot < len(self._cache) and self._cache[slot][0] == key:
                state = self._cache[slot][1]
            else:
                del self._cache[slot:]
                if slot == 0 and saved:
                    state = tuple([om.MVector(value) for value in array] for array in saved["state"])
                elif index == 0:
                    state = solver.initial_state(sample_poses)
                    if settled and settled["topology"] == topology_text:
                        roots = []
                        for i, parent in enumerate(simulation_parents):
                            root = i if parent < 0 else roots[parent]
                            roots.append(root)
                            if i != root:
                                point = om.MPoint(settled["points"][i]) * sample_poses[root]
                                state[0][i] = om.MVector(point)
                                state[1][i] = om.MVector(point)
                    for _ in range(0 if settled and settled["topology"] == topology_text else options["warmupSteps"]):
                        state = solver.step(state, sample_poses, sample_poses, simulation_parents, settings, sample_colliders, constraints, options, dt)
                elif options["teleportDistance"] > 0 and any((solver.position(sample_poses[i]) - solver.position(poses[i])).length() > options["teleportDistance"] for i, parent in enumerate(parents) if parent < 0 and active[i]):
                    state = solver.initial_state(sample_poses)
                else:
                    state = solver.step(state, poses, sample_poses, simulation_parents, settings, sample_colliders, constraints, options, dt)
                self._cache.append((key, state))
            poses, colliders = sample_poses, sample_colliders
        remainder = elapsed - steps * dt
        if remainder > 1.0e-7:
            final_poses, colliders, _ = self._sample(om.MDGContext(om.MTime(time, om.MTime.kSeconds)), topology, collider_types)
            state = solver.step(state, poses, final_poses, simulation_parents, settings, colliders, constraints, options, remainder)
            poses = final_poses
        matrices = solver.output_matrices(poses, state[0], parents, options["blend"])
        output = data.outputArrayValue(attrs["outputMatrix"])
        builder = output.builder()
        for index, matrix in enumerate(matrices):
            if not active[index]:
                parent = parents[index]
                matrix = poses[index] if parent < 0 else poses[index] * poses[parent].inverse()
            builder.addElement(index).setMMatrix(matrix)
        output.set(builder)
        output.setAllClean()
        residual, contacts = solver.collision_diagnostics(state[0], [value["radius"] for value in settings], colliders, simulation_parents)
        data.outputValue(attrs["residualPenetration"]).setDouble(residual)
        data.outputValue(attrs["contactParticleCount"]).setInt(contacts)
        step_seconds = remainder if remainder > 1.0e-7 else dt
        for name in ("particlePosition", "velocityEndpoint"):
            array = data.outputArrayValue(attrs[name])
            builder = array.builder()
            for index, (now, past) in enumerate(zip(*state)):
                value = now if name == "particlePosition" else now + (now - past) / step_seconds
                builder.addElement(index).set3Double(*value)
            array.set(builder)
            array.setAllClean()
        speed = max(((now - previous).length() for now, previous, enabled in zip(*state, active) if enabled), default=0.0) / step_seconds
        data.outputValue(attrs["maxParticleSpeed"]).setDouble(speed)
        data.outputValue(attrs["fixedRootCount"]).setInt(sum(parent == -1 and enabled for parent, enabled in zip(parents, active)))
        for name in ("residualPenetration", "maxParticleSpeed", "fixedRootCount", "contactParticleCount"):
            data.setClean(attrs[name])
        data.setClean(plug)
        return self
