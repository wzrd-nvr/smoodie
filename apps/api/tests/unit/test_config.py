from smoodie_api.config import Settings


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.env == "local"
    assert s.tier1_scoring_floor == 0.35
    assert s.tier2_offer_floor == 0.65


def test_env_prefix_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SMOODIE_ENV", "test")
    monkeypatch.setenv("SMOODIE_TIER1_SCORING_FLOOR", "0.4")
    s = Settings(_env_file=None)
    assert s.env == "test"
    assert s.tier1_scoring_floor == 0.4


def test_gate_thresholds_are_ordered() -> None:
    # audit ceiling < scoring floor < tier2 offer floor, per the review-system spec
    s = Settings(_env_file=None)
    assert s.audit_flag_ceiling < s.tier1_scoring_floor < s.tier2_offer_floor
