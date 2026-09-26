# MetaHuman for Maya: module definition written for this workspace.
# Registers the maya/external/MetaHumanForMaya submodule (module name
# MetaHumanForMaya) for Maya 2024-2027 on Windows only. Linux and other
# Maya versions are not registered.
# Paths are relative to the submodule root. Except for plugin/, every list
# below is the matching list of the release's own manifest
# env/win64-<year>.json with lib/ added in front, kept in the same order
# because that order is the search order. Rebuild the lists from those
# manifests whenever the submodule is updated.
# Maya stops reading a section at a '#' line, so keep comments above the
# first '+' line.

+ MAYAVERSION:2024 PLATFORM:win64 MetaHumanForMaya 1.3.1 ../external/MetaHumanForMaya
MAYA_PLUG_IN_PATH +:= plugin
MAYA_PLUG_IN_PATH +:= lib/riglogic4_maya/2.13.2.3/platform-windows/maya-2024/lib
MAYA_PLUG_IN_PATH +:= lib/DNACalibMayaPlugin/3.1.0/platform-windows/maya-2024/lib
MAYA_PLUG_IN_PATH +:= lib/MayaUERBFPlugin/2.0.5/platform-windows/maya-2024/lib
MAYA_PLUG_IN_PATH +:= lib/PreviewRigLogic/3.1.1/platform-windows/maya-2024/lib
MAYA_PLUG_IN_PATH +:= lib/cbsnode_maya/1.7.7/platform-windows/maya-2024/lib
MAYA_PLUG_IN_PATH +:= lib/SwingTwistEvaluatorPlugin/1.3.3/platform-windows/maya-2024/lib
PYTHONPATH +:= lib/QtPy/2.4.3/python-3/python
PYTHONPATH +:= lib/packaging/26.2/python-3/python
PYTHONPATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.10/lib
PYTHONPATH +:= lib/mh_assemble_lib/2.11.0/0c7b6cc4094b6ad14e70fc5dd12d1024a3f644e5
PYTHONPATH +:= lib/qstyle/1.9.1
PYTHONPATH +:= lib/mh_character_assembler/1.13.2
PYTHONPATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.10/lib
PYTHONPATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.10/lib
PYTHONPATH +:= lib/nls/8.1.0.3/platform-windows/python-3.10
PYTHONPATH +:= lib/rdf_model/0.31.2
PYTHONPATH +:= lib/frt_api/3.5.1
PYTHONPATH +:= lib/mh_expression_editor/2.11.10
PYTHONPATH +:= lib/mh_groom_exporter/1.5.1
PYTHONPATH +:= lib/mh_pose_editor/1.12.2
PATH +:= lib/QtPy/2.4.3/python-3/bin
PATH +:= lib/packaging/26.2/python-3/bin
PATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.10/lib
PATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.10/lib
PATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.10/lib
ML_MODEL_ROOT +:= lib/ml_jm_model/1.2.2
LOD_GENERATION_ROOT +:= lib/lod_generation_model/1.0.0

+ MAYAVERSION:2025 PLATFORM:win64 MetaHumanForMaya 1.3.1 ../external/MetaHumanForMaya
MAYA_PLUG_IN_PATH +:= plugin
MAYA_PLUG_IN_PATH +:= lib/riglogic4_maya/2.13.2.3/platform-windows/maya-2025/lib
MAYA_PLUG_IN_PATH +:= lib/DNACalibMayaPlugin/3.1.0/platform-windows/maya-2025/lib
MAYA_PLUG_IN_PATH +:= lib/MayaUERBFPlugin/2.0.5/platform-windows/maya-2025/lib
MAYA_PLUG_IN_PATH +:= lib/PreviewRigLogic/3.1.1/platform-windows/maya-2025/lib
MAYA_PLUG_IN_PATH +:= lib/cbsnode_maya/1.7.7/platform-windows/maya-2025/lib
MAYA_PLUG_IN_PATH +:= lib/SwingTwistEvaluatorPlugin/1.3.3/platform-windows/maya-2025/lib
PYTHONPATH +:= lib/QtPy/2.4.3/python-3/python
PYTHONPATH +:= lib/packaging/26.2/python-3/python
PYTHONPATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.11/lib
PYTHONPATH +:= lib/mh_assemble_lib/2.11.0/0c7b6cc4094b6ad14e70fc5dd12d1024a3f644e5
PYTHONPATH +:= lib/qstyle/1.9.1
PYTHONPATH +:= lib/mh_character_assembler/1.13.2
PYTHONPATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.11/lib
PYTHONPATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.11/lib
PYTHONPATH +:= lib/nls/8.1.0.3/platform-windows/python-3.11
PYTHONPATH +:= lib/rdf_model/0.31.2
PYTHONPATH +:= lib/frt_api/3.5.1
PYTHONPATH +:= lib/mh_expression_editor/2.11.10
PYTHONPATH +:= lib/mh_groom_exporter/1.5.1
PYTHONPATH +:= lib/mh_pose_editor/1.12.2
PATH +:= lib/QtPy/2.4.3/python-3/bin
PATH +:= lib/packaging/26.2/python-3/bin
PATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.11/lib
PATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.11/lib
PATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.11/lib
ML_MODEL_ROOT +:= lib/ml_jm_model/1.2.2
LOD_GENERATION_ROOT +:= lib/lod_generation_model/1.0.0

+ MAYAVERSION:2026 PLATFORM:win64 MetaHumanForMaya 1.3.1 ../external/MetaHumanForMaya
MAYA_PLUG_IN_PATH +:= plugin
MAYA_PLUG_IN_PATH +:= lib/riglogic4_maya/2.13.2.3/platform-windows/maya-2026/lib
MAYA_PLUG_IN_PATH +:= lib/DNACalibMayaPlugin/3.1.0/platform-windows/maya-2026/lib
MAYA_PLUG_IN_PATH +:= lib/MayaUERBFPlugin/2.0.5/platform-windows/maya-2026/lib
MAYA_PLUG_IN_PATH +:= lib/PreviewRigLogic/3.1.1/platform-windows/maya-2026/lib
MAYA_PLUG_IN_PATH +:= lib/cbsnode_maya/1.7.7/platform-windows/maya-2026/lib
MAYA_PLUG_IN_PATH +:= lib/SwingTwistEvaluatorPlugin/1.3.3/platform-windows/maya-2026/lib
PYTHONPATH +:= lib/QtPy/2.4.3/python-3/python
PYTHONPATH +:= lib/packaging/26.2/python-3/python
PYTHONPATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.11/lib
PYTHONPATH +:= lib/mh_assemble_lib/2.11.0/0c7b6cc4094b6ad14e70fc5dd12d1024a3f644e5
PYTHONPATH +:= lib/qstyle/1.9.1
PYTHONPATH +:= lib/mh_character_assembler/1.13.2
PYTHONPATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.11/lib
PYTHONPATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.11/lib
PYTHONPATH +:= lib/nls/8.1.0.3/platform-windows/python-3.11
PYTHONPATH +:= lib/rdf_model/0.31.2
PYTHONPATH +:= lib/frt_api/3.5.1
PYTHONPATH +:= lib/mh_expression_editor/2.11.10
PYTHONPATH +:= lib/mh_groom_exporter/1.5.1
PYTHONPATH +:= lib/mh_pose_editor/1.12.2
PATH +:= lib/QtPy/2.4.3/python-3/bin
PATH +:= lib/packaging/26.2/python-3/bin
PATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.11/lib
PATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.11/lib
PATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.11/lib
ML_MODEL_ROOT +:= lib/ml_jm_model/1.2.2
LOD_GENERATION_ROOT +:= lib/lod_generation_model/1.0.0

+ MAYAVERSION:2027 PLATFORM:win64 MetaHumanForMaya 1.3.1 ../external/MetaHumanForMaya
MAYA_PLUG_IN_PATH +:= plugin
MAYA_PLUG_IN_PATH +:= lib/riglogic4_maya/2.13.2.3/platform-windows/maya-2027/lib
MAYA_PLUG_IN_PATH +:= lib/DNACalibMayaPlugin/3.1.0/platform-windows/maya-2027/lib
MAYA_PLUG_IN_PATH +:= lib/MayaUERBFPlugin/2.0.5/platform-windows/maya-2027/lib
MAYA_PLUG_IN_PATH +:= lib/PreviewRigLogic/3.1.1/platform-windows/maya-2027/lib
MAYA_PLUG_IN_PATH +:= lib/cbsnode_maya/1.7.7/platform-windows/maya-2027/lib
MAYA_PLUG_IN_PATH +:= lib/SwingTwistEvaluatorPlugin/1.3.3/platform-windows/maya-2027/lib
PYTHONPATH +:= lib/QtPy/2.4.3/python-3/python
PYTHONPATH +:= lib/packaging/26.2/python-3/python
PYTHONPATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PYTHONPATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.13/lib
PYTHONPATH +:= lib/mh_assemble_lib/2.11.0/0c7b6cc4094b6ad14e70fc5dd12d1024a3f644e5
PYTHONPATH +:= lib/qstyle/1.9.1
PYTHONPATH +:= lib/mh_character_assembler/1.13.2
PYTHONPATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.13/lib
PYTHONPATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.13/lib
PYTHONPATH +:= lib/nls/8.1.0.3/platform-windows/python-3.13
PYTHONPATH +:= lib/rdf_model/0.31.2
PYTHONPATH +:= lib/frt_api/3.5.1
PYTHONPATH +:= lib/mh_expression_editor/2.11.10
PYTHONPATH +:= lib/mh_groom_exporter/1.5.1
PYTHONPATH +:= lib/mh_pose_editor/1.12.2
PATH +:= lib/QtPy/2.4.3/python-3/bin
PATH +:= lib/packaging/26.2/python-3/bin
PATH +:= lib/PolyAlloc/1.3.18/platform-windows/.sanitizers-off/lib
PATH +:= lib/StatusCode/1.2.12/platform-windows/.sanitizers-off/lib
PATH +:= lib/TRiO/4.0.21/platform-windows/.sanitizers-off/lib
PATH +:= lib/DNA/10.1.5/platform-windows/.sanitizers-off/.json-0/python-3.13/lib
PATH +:= lib/RDF/6.5.8/platform-windows/.sanitizers-off/python-3.13/lib
PATH +:= lib/DNACalib2/5.1.5/platform-windows/.sanitizers-off/python-3.13/lib
ML_MODEL_ROOT +:= lib/ml_jm_model/1.2.2
LOD_GENERATION_ROOT +:= lib/lod_generation_model/1.0.0
