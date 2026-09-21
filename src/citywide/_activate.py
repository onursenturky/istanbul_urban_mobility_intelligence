"""Activates the citywide config overlay.

Must be imported FIRST, before any src.data / src.features module, in every
citywide orchestrator script — Python binds `from src.utils import config as
cfg` to whatever object is in sys.modules["src.utils.config"] at the time
each module is first imported, so this patch has to land before those
imports happen.
"""

import sys

import src.utils as _src_utils
from src.utils import config_citywide

# Both of these are required: sys.modules covers `import src.utils.config`
# and fresh `from src.utils import config` statements; the attribute on the
# already-imported `src.utils` package object covers `from src.utils import
# config` when Python's import machinery short-circuits via getattr(package,
# name) instead of re-consulting sys.modules (it does, once src.utils.config
# has already been imported once — as it was here, transitively, while
# config_citywide.py itself did `from src.utils import config as _base`).
sys.modules["src.utils.config"] = config_citywide
_src_utils.config = config_citywide
