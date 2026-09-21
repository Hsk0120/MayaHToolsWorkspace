"""Attribute plug wrappers for Hlib."""

from ..core.discovery import discover_plug_package
from .plug import Plug
from .array_plug import ArrayPlug
from .compound_plug import CompoundPlug

for _export_name in globals().get("_discovered_exports", {}):
    globals().pop(_export_name, None)
_discovered_wrappers, _discovered_exports = discover_plug_package(__name__)
globals().update(_discovered_exports)

__all__ = [
    "Plug",
    "ArrayPlug",
    "CompoundPlug",
    *sorted(_discovered_exports),
]
