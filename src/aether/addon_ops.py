"""Compat shim — implementation lives in exo_control.addon_ops."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.addon_ops")
