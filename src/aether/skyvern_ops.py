"""Compat shim — implementation lives in exo_control.skyvern_ops."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.skyvern_ops")
