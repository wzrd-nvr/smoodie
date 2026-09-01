"""The measurement vocabulary a recipe may use.

Curated rather than free text. An open unit field produces "1 glug", "2 tins"
and "3 handfuls", which reads fine to a human and is useless to the phase-2
recipe builder that has to scale and substitute ingredients. Anything genuinely
unmeasurable is expressed with to_taste instead.
"""

from typing import Final

# Grouped by system so the composer can present them sensibly. The canonical
# form is the key; the aliases are what people actually type.
VOLUME: Final[dict[str, tuple[str, ...]]] = {
    "tsp": ("teaspoon", "teaspoons", "t"),
    "tbsp": ("tablespoon", "tablespoons", "T"),
    "cup": ("cups", "c"),
    "ml": ("milliliter", "milliliters", "millilitre", "millilitres"),
    "l": ("liter", "liters", "litre", "litres"),
    "fl oz": ("fluid ounce", "fluid ounces"),
    "pint": ("pints", "pt"),
    "quart": ("quarts", "qt"),
    "gallon": ("gallons", "gal"),
}

WEIGHT: Final[dict[str, tuple[str, ...]]] = {
    "g": ("gram", "grams", "gramme", "grammes"),
    "kg": ("kilogram", "kilograms", "kilo", "kilos"),
    "oz": ("ounce", "ounces"),
    "lb": ("pound", "pounds", "lbs"),
}

COUNT: Final[dict[str, tuple[str, ...]]] = {
    # For things counted rather than measured: 2 eggs, 1 onion.
    "count": ("whole", "each"),
    "clove": ("cloves",),
    "slice": ("slices",),
    "sprig": ("sprigs",),
    "bunch": ("bunches",),
    "can": ("cans", "tin", "tins"),
    "package": ("packages", "pkg", "packet", "packets"),
    "pinch": ("pinches",),
    "dash": ("dashes",),
}

_ALL: Final[dict[str, tuple[str, ...]]] = {**VOLUME, **WEIGHT, **COUNT}

CANONICAL_UNITS: Final[frozenset[str]] = frozenset(_ALL)

_ALIAS_TO_CANONICAL: Final[dict[str, str]] = {
    alias.lower(): canonical for canonical, aliases in _ALL.items() for alias in aliases
} | {canonical.lower(): canonical for canonical in _ALL}


class UnknownUnit(ValueError):
    """Raised with the closest guidance we can give."""


def normalize_unit(raw: str) -> str:
    """Map what someone typed onto a canonical unit, or explain the rejection."""
    candidate = raw.strip().lower().rstrip(".")
    if not candidate:
        raise UnknownUnit("Pick a unit, or mark the ingredient as to taste.")

    canonical = _ALIAS_TO_CANONICAL.get(candidate)
    if canonical is None:
        raise UnknownUnit(
            f"'{raw.strip()}' isn't a unit we recognize. "
            "Use a standard measure, or mark the ingredient as to taste."
        )
    return canonical
