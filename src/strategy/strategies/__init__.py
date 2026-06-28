"""Built-in strategy plugins.

Importing this package auto-discovers and imports every strategy module beside
this file, registering each one. Adding a new built-in strategy is therefore
just dropping a new ``*.py`` file here — no edit to this file or any core file
is needed (issue #45).
"""

from __future__ import annotations

from ..loader import import_submodules

import_submodules(__name__, __path__)
