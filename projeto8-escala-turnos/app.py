"""Shift scheduler web app (Streamlit). Run:  streamlit run app.py"""
import pandas as pd
import streamlit as st

from escala import DAYS, SHIFTS, Employee, exemplo, resolver

st.set_page_config(page_title="Shift Scheduler", layout="wide")
st.title("Weekly shift scheduler")
st.caption("Set who is needed and who can work when. The solver builds a fair schedule or tells you why it can't.")

team, base_need = exemplo()
slots = [f"{DAYS[d]} {SHIFTS[s]}" for d in range(7) for s in range(3)]
slot_key = {label: (i // 3, i % 3) for i, label in enumerate(slots)}

with st.sidebar:
    st.header("Coverage needed")
    c1, c2 = st.columns(2)
    wk = [c1.number_input(f"Weekday {s}", 0, 8, base_need[(0, i)], key=f"wk{i}") for i, s in enumerate(SHIFTS)]
    we = [c2.number_input(f"Weekend {s}", 0, 8, base_need[(5, i)], key=f"we{i}") for i, s in enumerate(SHIFTS)]
    st.header("Team")
    employees = []
    for e in team:
        with st.expander(e.name):
            mx = st.slider("Max shifts / week", 0, 7, e.max_shifts, key=f"mx{e.name}")
            un = st.multiselect("Cannot work", slots, [slots[d * 3 + s] for d, s in sorted(e.unavailable)], key=f"un{e.name}")
            off = st.multiselect("Prefers day off", DAYS, [DAYS[d] for d in sorted(e.preferred_off)], key=f"off{e.name}")
        employees.append(Employee(e.name, mx, {slot_key[u] for u in un}, {DAYS.index(o) for o in off}))

need = {(d, s): int((we if d >= 5 else wk)[s]) for d in range(7) for s in range(3) if (we if d >= 5 else wk)[s] > 0}

if st.button("Build schedule", type="primary") or "first" not in st.session_state:
    st.session_state["first"] = True
    st.session_state["result"] = resolver(employees, need)

r = st.session_state["result"]
if r.status == "infeasible":
    st.error(f"No valid schedule: {r.explanation}")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Status", r.status.capitalize())
m2.metric("Preferred days off missed", r.preference_misses)
counts = list(r.shifts_per_person.values())
m3.metric("Busiest vs lightest", f"{max(counts)} vs {min(counts)} shifts")

grid = pd.DataFrame({SHIFTS[s]: [", ".join(r.schedule.get((d, s), [])) or "-" for d in range(7)] for s in range(3)}, index=DAYS)
st.subheader("Schedule")
st.dataframe(grid, use_container_width=True)
st.subheader("Shifts per person")
st.bar_chart(pd.Series(r.shifts_per_person, name="shifts"))
st.download_button("Download schedule (CSV)", grid.to_csv().encode(), "schedule.csv", "text/csv")
