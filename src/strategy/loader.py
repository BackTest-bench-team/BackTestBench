"""Strategy plugin loading and discovery (issue #45).

Strategies register themselves with the ``@register_strategy`` decorator at
import time, so "loading" a strategy just means importing its module. This
loader discovers and imports those modules automatically:

  * ``discover_builtin_strategies()`` imports every module in the built-in
    ``strategies`` package, so dropping a new file in there is picked up with
    no edit to any core file.
  * ``load_plugins_from_dir(path)`` imports external ``.py`` plugins from an
    arbitrary directory, so strategies can live outside the package entirely.

Either way, no core logic changes when a strategy is added.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Iterable

from .registry import available_strategies


def import_submodules(package_name: str, package_path: Iterable[str]) -> list[str]:
    """Import every non-private submodule of a package. Returns module names."""
    imported: list[str] = []
    for info in pkgutil.iter_modules(list(package_path)):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"{package_name}.{info.name}")
        imported.append(info.name)
    return imported


def discover_builtin_strategies() -> list[str]:
    """Import all modules in the built-in strategies package and return the
    list of registered strategy IDs afterwards."""
    from . import strategies  # the built-in package

    import_submodules(strategies.__name__, strategies.__path__)
    return available_strategies()


def load_plugin_file(path: str | Path) -> ModuleType:
    """Import a single external strategy plugin from a .py file path.

    Importing it runs its ``@register_strategy`` decorators, adding the
    strategy to the registry without touching any core file.
    """
    path = Path(path)
    if not path.is_file() or path.suffix != ".py":
        raise FileNotFoundError(f"not a Python plugin file: {path}")
    module_name = f"_strategy_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"could not load plugin spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plugins_from_dir(directory: str | Path) -> list[str]:
    """Import every ``.py`` plugin in a directory. Returns registered IDs."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"plugin directory not found: {directory}")
    for file in sorted(directory.glob("*.py")):
        if not file.name.startswith("_"):
            load_plugin_file(file)
    return available_strategies()
