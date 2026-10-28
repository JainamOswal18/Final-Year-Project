import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import compare  # noqa: E402


def test_mcnemar_known_values():
    assert compare.mcnemar_exact(0, 0) == 1.0
    assert compare.mcnemar_exact(5, 5) == 1.0
    assert abs(compare.mcnemar_exact(0, 10) - 2 / 1024) < 1e-12          # 10 vs 0: very unlikely by chance
    assert compare.mcnemar_exact(1, 9) < 0.03 and compare.mcnemar_exact(4, 6) > 0.5


def test_compare_counts_only_the_disagreements():
    a = [{"q": str(i), "ok": i < 6, "tags": ["x"]} for i in range(10)]
    b = [{"q": str(i), "ok": i >= 4, "tags": ["x"]} for i in range(10)]
    r = compare.compare(a, b)
    assert (r["only_a"], r["only_b"]) == (4, 4) and r["p"] == 1.0 and r["tags"]["x"] == (10, 6, 6)
