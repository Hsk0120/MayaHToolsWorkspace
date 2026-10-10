# pip packages

Each `<name>.txt` here is one pip package group, installed with the mayapy of each
Maya version into `../site-packages/<version>/<name>` (not tracked by Git).

`pip_<name>.mod` puts only that folder on PYTHONPATH. Put the .mod in `../modules`
to use the package, or keep it in `../modules_disabled`. The launchers install the
enabled groups that are missing or whose `.txt` has changed.

To add a group, create `<name>.txt` (pip requirement lines) and run
`install_packages.bat <version> <name>`; a disabled `pip_<name>.mod` is created.
