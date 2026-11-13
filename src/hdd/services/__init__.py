"""Application layer: what the Studio can do, independent of any user interface.

Modules here import only ``libs`` and the standard library. They return plain,
JSON-shaped data and raise ``ServiceError`` subclasses. The web routes and the
desktop application are both thin callers of this layer.
"""
