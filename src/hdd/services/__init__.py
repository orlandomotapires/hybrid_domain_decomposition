"""Application layer: what the Studio can do, independent of any user interface.

Modules here import only ``libs`` and the standard library. They return plain,
JSON-shaped data and raise ``ServiceError`` subclasses. The desktop app is a thin
caller of this layer.
"""
