import re

# Suffixes to strip, tried in order (longest match first, case-insensitive)
_SUFFIXES = [
    r"_Singles_Shadowless_\d+x\d+$",
    r"_SIngles_Shadowless_\d+x\d+$",  # asset pack typo
    r"_Singles_\d+x\d+$",
    r"_Shadowless_\d+x\d+$",
    r"_\d+x\d+$",
]

# Known typos in asset pack directory names
_NORMALIZATIONS: dict[str, str] = {
    "MIlitary_Base": "Military_Base",
}


def strip_theme_name(folder: str) -> str:
    """Derive a clean theme name from an asset pack directory name.

    Example: '5_Classroom_and_Library_Singles_Shadowless_48x48' -> 'Classroom_and_Library'
    """
    # 1. Strip leading numeric prefix (e.g. "5_" or "23_")
    name = re.sub(r"^\d+_", "", folder)

    # 2. Strip recognized suffix (case-insensitive, longest match first)
    for pattern in _SUFFIXES:
        stripped = re.sub(pattern, "", name, flags=re.IGNORECASE)
        if stripped != name:
            name = stripped
            break

    # 3. Apply normalization table
    return _NORMALIZATIONS.get(name, name)
