"""Compat shim — implementation lives in exo_control.rag_ops."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("exo_control.rag_ops")
