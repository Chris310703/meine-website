"""Tests für die Recovery-Ampel."""

from app.services.recovery import RecoveryInputs, evaluate


def good_inputs(**overrides) -> RecoveryInputs:
    values = dict(
        sleep_score=85,
        sleep_hours=7.8,
        hrv_last_night=62,
        hrv_weekly_avg=60,
        hrv_baseline_low=50,
        hrv_baseline_high=68,
        hrv_status="BALANCED",
        resting_hr=48,
        resting_hr_baseline=49,
        body_battery=88,
        training_readiness=82,
        training_readiness_level="HIGH",
        acwr=1.05,
        recovery_time_h=2,
        stress_avg=24,
    )
    values.update(overrides)
    return RecoveryInputs(**values)


def test_all_good_is_green():
    result = evaluate(good_inputs())
    assert result["color"] == "gruen"
    assert result["headline"] == "Hart trainieren"
    assert result["score"] >= 70
    assert len(result["reasons"]) == 3


def test_poor_hrv_and_high_resting_hr_is_red():
    result = evaluate(
        good_inputs(hrv_status="POOR", hrv_last_night=38, resting_hr=57, resting_hr_baseline=49)
    )
    assert result["color"] == "rot"
    assert result["headline"] == "Ruhetag"
    # Begründung nennt die kritischen Werte zuerst
    assert any("HRV" in r for r in result["reasons"][:2])
    assert any("Ruhepuls" in r for r in result["reasons"][:2])


def test_single_bad_factor_is_yellow():
    # Nur kurze Nacht, sonst alles gut → locker trainieren
    result = evaluate(good_inputs(sleep_score=45, sleep_hours=5.5))
    assert result["color"] == "gelb"
    assert any("zu kurze Nacht" in r for r in result["reasons"])


def test_high_load_ratio_and_long_recovery_is_red():
    result = evaluate(good_inputs(acwr=1.7, recovery_time_h=55, training_readiness=30, body_battery=30))
    assert result["color"] == "rot"


def test_moderate_values_are_yellow():
    result = evaluate(
        good_inputs(
            hrv_status="UNBALANCED",
            training_readiness=55,
            training_readiness_level="MODERATE",
            body_battery=55,
            sleep_score=65,
            recovery_time_h=20,
        )
    )
    assert result["color"] == "gelb"
    assert result["headline"] == "Locker trainieren"


def test_no_data_is_grey():
    result = evaluate(RecoveryInputs())
    assert result["color"] == "grau"
    assert result["score"] is None
    assert result["reasons"] == []


def test_partial_data_still_works():
    result = evaluate(RecoveryInputs(sleep_hours=8.1, body_battery=90))
    assert result["color"] == "gruen"
    assert {f["key"] for f in result["factors"]} == {"sleep", "body_battery"}


def test_hrv_without_status_uses_baseline():
    below = evaluate(RecoveryInputs(hrv_last_night=40, hrv_baseline_low=50, hrv_baseline_high=65))
    inside = evaluate(RecoveryInputs(hrv_last_night=58, hrv_baseline_low=50, hrv_baseline_high=65))
    assert below["factors"][0]["score"] < inside["factors"][0]["score"]
    assert "unter dem Normalbereich" in below["factors"][0]["text"]


def test_hrv_drop_vs_weekly_average_is_penalised():
    result = evaluate(good_inputs(hrv_last_night=45, hrv_weekly_avg=60))
    hrv = next(f for f in result["factors"] if f["key"] == "hrv")
    assert hrv["score"] <= 40
    assert "unter Wochenschnitt" in hrv["text"]
