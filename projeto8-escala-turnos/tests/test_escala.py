"""Tests check the finished schedule against the rules directly, not through the solver's own variables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from escala import DAYS, Employee, exemplo, resolver


@pytest.fixture(scope="module")
def sample():
    emp, need = exemplo()
    return emp, need, resolver(emp, need)


def worked(result):
    """name -> set of (day, shift) they work, rebuilt from the schedule."""
    out = {}
    for (d, s), names in result.schedule.items():
        for n in names:
            out.setdefault(n, set()).add((d, s))
    return out


def test_sample_is_solved(sample):
    _, _, r = sample
    assert r.status in ("optimal", "feasible")


def test_every_shift_has_exactly_the_people_needed(sample):
    _, need, r = sample
    for key, n in need.items():
        assert len(r.schedule[key]) == n, f"{DAYS[key[0]]} shift {key[1]}"


def test_nobody_works_a_shift_they_cannot(sample):
    emp, _, r = sample
    w = worked(r)
    for e in emp:
        assert not (w.get(e.name, set()) & e.unavailable), e.name


def test_at_most_one_shift_per_day(sample):
    _, _, r = sample
    for name, shifts in worked(r).items():
        days = [d for d, _ in shifts]
        assert len(days) == len(set(days)), name


def test_no_evening_followed_by_morning(sample):
    _, _, r = sample
    for name, shifts in worked(r).items():
        for d, s in shifts:
            if s == 2:
                assert (d + 1, 0) not in shifts, f"{name} closes {DAYS[d]} and opens next day"


def test_weekly_limit_respected(sample):
    emp, _, r = sample
    for e in emp:
        assert r.shifts_per_person[e.name] <= e.max_shifts


def test_work_is_spread_evenly(sample):
    _, _, r = sample
    counts = list(r.shifts_per_person.values())
    assert max(counts) - min(counts) <= 1


def test_preferred_days_off_honoured_when_possible(sample):
    emp, _, r = sample
    assert r.preference_misses == 0
    w = worked(r)
    for e in emp:
        for d, _ in w.get(e.name, set()):
            assert d not in e.preferred_off, e.name


def test_impossible_week_is_reported_not_faked():
    emp = [Employee("Solo", 5)]
    need = {(0, 0): 2}  # needs two people, only one exists
    r = resolver(emp, need)
    assert r.status == "infeasible"
    assert "needs 2 people" in r.explanation


def test_not_enough_total_capacity_is_explained():
    emp = [Employee("A", 1), Employee("B", 1)]
    need = {(0, 0): 1, (1, 0): 1, (2, 0): 1}  # 3 shifts, team can do 2
    r = resolver(emp, need)
    assert r.status == "infeasible"
    assert "can only work 2" in r.explanation


def test_unavailability_forces_the_right_person():
    emp = [Employee("A", 5, unavailable={(0, 0)}), Employee("B", 5)]
    r = resolver(emp, {(0, 0): 1})
    assert r.schedule[(0, 0)] == ["B"]
