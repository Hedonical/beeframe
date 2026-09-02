import random
import re
import uuid

LETTERS = "ABCDEFGHIJKLMNPQRSTUVWXYZ"
PLANTS = (
    "Aster", "Basswood", "Blackberry", "Blueberry", "Buckwheat", "Clover", "Dandelion",
    "Elderberry", "Fireweed", "Goldenrod", "Hawthorn", "Heather", "Holly", "Lavender",
    "Maple", "Mint", "Sage", "Sunflower", "Thistle", "Willow", "Yarrow",
)
PATTERNS = {"box": re.compile(r"^[A-NP-Z]{2}$"), "frame": re.compile(r"^[A-NP-Z][1-9][A-NP-Z]$"), "equipment": re.compile(r"^[A-NP-Z]{4}$")}


def new_id() -> str:
    return str(uuid.uuid4())


def _unique(factory, used: set[str], attempts: int = 500) -> str:
    folded = {value.casefold() for value in used}
    for _ in range(attempts):
        value = factory()
        if value.casefold() not in folded:
            return value
    raise ValueError("Could not generate a unique name or code; archive an old item or choose a name manually.")


def plant_name(used: set[str], rng=random) -> str:
    return _unique(lambda: rng.choice(PLANTS), used)


def box_code(used: set[str], rng=random) -> str:
    return _unique(lambda: "".join(rng.choice(LETTERS) for _ in range(2)), used)


def frame_code(used: set[str], rng=random) -> str:
    return _unique(lambda: f"{rng.choice(LETTERS)}{rng.randint(1, 9)}{rng.choice(LETTERS)}", used)


def equipment_code(used: set[str], rng=random) -> str:
    return _unique(lambda: "".join(rng.choice(LETTERS) for _ in range(4)), used)
