"""Compat shim — implementation lives in exo_control.backends_win."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.backends_win")
