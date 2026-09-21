"""PlateGauge's dependency-light public Python API.

Training and ONNX dependencies are intentionally imported only by the modules that
need them. Importing :mod:`plategauge` requires only the declared core dependencies.
"""

from .folds import FROZEN_CATEGORY_FOLDS, fold_for_category
from .schema import ManifestRecord, read_manifest, write_manifest

__all__ = [
    "FROZEN_CATEGORY_FOLDS",
    "ManifestRecord",
    "fold_for_category",
    "read_manifest",
    "write_manifest",
]

__version__ = "1.0.1"
