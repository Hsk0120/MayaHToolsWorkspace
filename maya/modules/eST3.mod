# eST3: module definition written for this workspace.
# Registers the maya/external/eST3 submodule (a private repository; the
# files are not redistributable and are not part of this repository) for
# Maya 2022-2027 on Windows. The module root is the distribution's own
# core/maya folder, so Maya adds its scripts/ and icons/ by itself; the
# plug-in folders are per Maya version and are listed here the same way
# as the distribution's own core/maya/eST3.mod.
# The eST3Startup sections put maya/inhouse/eST3Startup (this workspace's
# own userSetup.py) on PYTHONPATH; it runs the MEL command eST3menuBar
# when the Maya GUI starts. Remove those sections to stop the automatic
# start (eST3menuBar and eST3start can still be run by hand).
# Maya stops reading a section at a '#' line, so keep comments above the
# first '+' line.

+ MAYAVERSION:2022 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2022/nt64

+ MAYAVERSION:2023 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2023/nt64

+ MAYAVERSION:2024 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2024/nt64

+ MAYAVERSION:2025 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2025/nt64

+ MAYAVERSION:2026 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2026/nt64

+ MAYAVERSION:2027 PLATFORM:win64 eST3 1.145.0 ../external/eST3/core/maya
MAYA_PLUG_IN_PATH +:= plug-ins/2027/nt64

+ MAYAVERSION:2022 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .

+ MAYAVERSION:2023 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .

+ MAYAVERSION:2024 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .

+ MAYAVERSION:2025 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .

+ MAYAVERSION:2026 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .

+ MAYAVERSION:2027 PLATFORM:win64 eST3Startup 1.0.0 ../inhouse/eST3Startup
PYTHONPATH +:= .
