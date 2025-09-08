import os

TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}

def env_bool(name: str) -> bool | None:
    val = os.getenv(name)
    if val is None:
        return None
    s = val.strip().lower()
    if s in TRUE_VALUES:
        return True
    if s in FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean for {name!r}: {val!r}. "
                     f"Use one of {sorted(TRUE_VALUES | FALSE_VALUES)}")
