"""Compat shim — implementation lives in exo_control.open_data_ops."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.open_data_ops")
