"""Rule modules for paper_lab. Every rules/*.py that defines NAME and select() is discovered dynamically;
a module that fails to import is logged and skipped (never crashes a scan)."""
import importlib
import pkgutil

from logger import log

RULE_MODULES = []     # refreshed by load_rules()


def load_rules() -> list:
    mods, names = [], set()
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{info.name}")
            if not (isinstance(getattr(mod, "NAME", None), str) and callable(getattr(mod, "select", None))):
                continue                                  # helper module, not a rule
            if mod.NAME in names:
                log(f"rules: duplicate rule name {mod.NAME} in {info.name}; skipped", "WARN")
                continue
            names.add(mod.NAME)
            mods.append(mod)
        except Exception as ex:
            log(f"rules: could not load {info.name}: {type(ex).__name__}: {ex}", "WARN")
    RULE_MODULES[:] = [m.NAME for m in mods]
    return mods
