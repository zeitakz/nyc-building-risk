"""The split rule must be deterministic, format-independent and close to 35/65."""
import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))
from splits import split_for, normalize_bbl  # noqa: E402

def test_same_bbl_any_format_same_split():
    assert split_for(3018340039) == split_for("3018340039") == split_for("3018340039.00000000")

def test_normalize():
    assert normalize_bbl(1000010010) == "1000010010"
    assert normalize_bbl("1000010010.00000000") == "1000010010"

def test_share_close_to_35_percent():
    rng = random.Random(0)
    bbls = [rng.randint(1, 5) * 10**9 + rng.randint(1, 99999) * 10**4 + rng.randint(1, 9999) for _ in range(20000)]
    share = sum(split_for(b) == "confirmation" for b in bbls) / len(bbls)
    assert 0.33 < share < 0.37
