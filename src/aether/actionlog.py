"""Compat shim — implementation lives in exo_control.actionlog."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.actionlog")
