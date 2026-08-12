"""Compat shim — implementation lives in exo_control.browser."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.browser")
