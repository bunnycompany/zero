# zero/__init__.py
"""
Zero - Native MLX-driven Autonomous Agent

Core state plumbing lives in zero.ns / zero.nspath. Import those directly;
this package init stays empty on purpose — importing `zero` must never pull
in MLX or the eval stack.
"""
