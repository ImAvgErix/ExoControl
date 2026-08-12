"""Compat shim — implementation lives in exo_control.cli."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.cli")
