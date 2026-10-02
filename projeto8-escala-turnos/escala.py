"""
Shift scheduler: builds a weekly staff schedule that respects the hard rules and is as fair as possible.

Hard rules (never broken):
  - every shift gets exactly the number of people it needs
  - nobody works a shift they marked as unavailable
  - at most one shift per person per day
  - no "late shift followed by early shift the next morning" (minimum rest)
  - nobody exceeds their maximum shifts per week

Soft goals (optimised, in this order of weight):
  1. give people their preferred days off
  2. spread the work evenly (smallest gap between the busiest and the lightest person)

The solver is Google OR-Tools CP-SAT. If the rules can't all be met, `resolver` says so and
names the shift that can't be covered instead of returning a wrong schedule.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SHIFTS = ["Morning", "Afternoon", "Evening"]  # order matters: Evening -> next Morning is the rest rule


@dataclass
class Employee:
    name: str
    max_shifts: int = 5
    unavailable: set[tuple[int, int]] = field(default_factory=set)  # (day, shift) they cannot work
    preferred_off: set[int] = field(default_factory=set)  # days they would like off (soft)


@dataclass
class Result:
    status: str  # "optimal", "feasible" or "infeasible"
    schedule: dict[tuple[int, int], list[str]]  # (day, shift) -> names
    shifts_per_person: dict[str, int]
    preference_misses: int  # how many preferred days off could not be honoured
    explanation: str = ""


def _diagnose(employees, need) -> str:
    """Point at the first shift that cannot be covered even in the best case, to explain 'infeasible'."""
    for (d, s), n in sorted(need.items()):
        free = [e.name for e in employees if (d, s) not in e.unavailable]
        if len(free) < n:
            return f"{DAYS[d]} {SHIFTS[s]} needs {n} people but only {len(free)} are available."
    total_need = sum(need.values())
    total_cap = sum(e.max_shifts for e in employees)
    if total_need > total_cap:
        return f"The week needs {total_need} shifts covered but the team can only work {total_cap} in total."
    return "The rules conflict (for example, rest rules plus limited availability). Relax one of them."


def resolver(employees: list[Employee], need: dict[tuple[int, int], int], tempo_max: float = 10.0) -> Result:
    m = cp_model.CpModel()
    n_e = len(employees)
    x = {(e, d, s): m.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(n_e) for d in range(7) for s in range(3)}

    for (d, s), n in need.items():
        m.Add(sum(x[e, d, s] for e in range(n_e)) == n)
    for d in range(7):
        for s in range(3):
            if (d, s) not in need:
                for e in range(n_e):
                    m.Add(x[e, d, s] == 0)

    for e, emp in enumerate(employees):
        for (d, s) in emp.unavailable:
            m.Add(x[e, d, s] == 0)
        for d in range(7):
            m.Add(sum(x[e, d, s] for s in range(3)) <= 1)
        for d in range(6):  # Evening today -> Morning tomorrow is not allowed
            m.Add(x[e, d, 2] + x[e, d + 1, 0] <= 1)
        m.Add(sum(x[e, d, s] for d in range(7) for s in range(3)) <= emp.max_shifts)

    total = [sum(x[e, d, s] for d in range(7) for s in range(3)) for e in range(n_e)]
    top, low = m.NewIntVar(0, 21, "top"), m.NewIntVar(0, 21, "low")
    for t in total:
        m.Add(t <= top)
        m.Add(t >= low)

    misses = [x[e, d, s] for e, emp in enumerate(employees) for d in emp.preferred_off for s in range(3)]
    # preference misses weigh more than the fairness gap
    m.Minimize(10 * sum(misses) + (top - low))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_max
    solver.parameters.num_workers = 4
    code = solver.Solve(m)

    if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result("infeasible", {}, {}, 0, _diagnose(employees, need))

    schedule = {(d, s): [employees[e].name for e in range(n_e) if solver.Value(x[e, d, s])] for (d, s) in need}
    per_person = {emp.name: int(sum(solver.Value(x[e, d, s]) for d in range(7) for s in range(3)))
                  for e, emp in enumerate(employees)}
    missed = int(sum(solver.Value(v) for v in misses))
    return Result("optimal" if code == cp_model.OPTIMAL else "feasible", schedule, per_person, missed)


def exemplo():
    """Sample team of 8 and a typical week for a small shop/clinic (all data invented)."""
    emp = [
        Employee("Ana", 5, preferred_off={5, 6}),
        Employee("Bruno", 5, unavailable={(d, 0) for d in range(5)}),  # studies in the mornings
        Employee("Carla", 5, preferred_off={2}),
        Employee("Diego", 5),
        Employee("Elisa", 5, unavailable={(6, s) for s in range(3)}),  # never Sundays
        Employee("Fabio", 4, preferred_off={0, 1}),
        Employee("Gabi", 5, unavailable={(d, 2) for d in range(7)}),  # no evenings
        Employee("Hugo", 5, preferred_off={4}),
    ]
    need = {}
    for d in range(7):
        weekend = d >= 5
        need[(d, 0)] = 1 if weekend else 2
        need[(d, 1)] = 2
        need[(d, 2)] = 1 if weekend else 2
    return emp, need


if __name__ == "__main__":
    emp, need = exemplo()
    r = resolver(emp, need)
    print(r.status, "| preferred days off missed:", r.preference_misses)
    if r.status == "infeasible":
        raise SystemExit(r.explanation)
    for d in range(7):
        print(DAYS[d], *[f"{SHIFTS[s]}: {', '.join(r.schedule[(d, s)])}" for s in range(3)], sep="  ")
    print(r.shifts_per_person)
