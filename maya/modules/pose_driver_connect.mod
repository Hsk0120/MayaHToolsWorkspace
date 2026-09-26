# PoseDriverConnect: module definition written for this workspace.
# Registers the maya/external/PoseDriverConnect submodule (module name
# PoseDriverConnect) on Windows for Maya 2022, 2024, 2026 and 2027.
# Maya 2025 is not registered. The submodule has plug-in builds up to 2024
# only, so 2026/2027 get the Python package (python/) without a plug-in.
# macOS, Linux, Maya 2023 and versions before 2022 are not registered either.
# Maya stops reading a section at a '#' line, so keep comments above the
# first '+' line.

+ MAYAVERSION:2022 PLATFORM:win64 PoseDriverConnect 1.0 ../external/PoseDriverConnect
MAYA_PLUG_IN_PATH +:= plug-ins/windows/2022
PYTHONPATH +:= python

+ MAYAVERSION:2024 PLATFORM:win64 PoseDriverConnect 1.0 ../external/PoseDriverConnect
MAYA_PLUG_IN_PATH +:= plug-ins/windows/2024
PYTHONPATH +:= python

+ MAYAVERSION:2026 PLATFORM:win64 PoseDriverConnect 1.0 ../external/PoseDriverConnect
MAYA_PLUG_IN_PATH +:= plug-ins/windows/2026
PYTHONPATH +:= python

+ MAYAVERSION:2027 PLATFORM:win64 PoseDriverConnect 1.0 ../external/PoseDriverConnect
MAYA_PLUG_IN_PATH +:= plug-ins/windows/2027
PYTHONPATH +:= python
