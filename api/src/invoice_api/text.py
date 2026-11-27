"""Text normalization shared by retrieval (search_text, queries) and the eval metrics."""

import re
import unicodedata

_SEPARATORS = re.compile(r"[-'’/]")  # word separators: become spaces
_PUNCTUATION = re.compile(r"[^\w\s]")  # everything else that is not a letter, digit or space
_SPACES = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Case, accents, punctuation and spacing ignored.

    "Papeterie du Rhône S.A.S." and "PAPETERIE DU RHONE SAS" both become
    "papeterie du rhone sas".
    """
    # NFKD splits "ô" into "o" + combining accent; dropping combining marks removes accents.
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    text = _SEPARATORS.sub(" ", without_accents.casefold())
    text = _PUNCTUATION.sub("", text)
    return _SPACES.sub(" ", text).strip()
