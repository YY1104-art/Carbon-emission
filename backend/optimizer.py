
"""optimizer.py - multi-period (time-expanded) MILP prototype with greedy fallback.
Features:
- Supports multi-period duration_hours broken into integer hourly slots (T periods)
- If PuLP available, formulates a small MILP to place instances per (task,dc,period) and assign demand per (task,source,dest,period)
- If PuLP missing or solver fails, falls back to greedy per-period allocation
Notes: This is a demonstration-scale model. For large networks increase solver time limit or use specialized solvers.
"""
from typing import Dict, Any, Tuple, List
import math, traceback

def _build_example(cfg: Dict[str, Any]):
    # Build small example if not provided
    cities = cfg.get("cities")
    tasks = cfg.get("tasks")
    tsd = cfg.get("tsd")
    rav = cfg.get("rav")
    duration_hours = int(cfg.get("duration_hours", 24))
    if cities and tasks and tsd and rav:
        return cities, tasks, tsd, rav, duration_hours
    cities = [
        {"name":"Zurich","Iv":0.013,"Hv":900,"lat":47.3769,"lon":8.5417},
        {"name":"Paris","Iv":0.054,"Hv":3000,"lat":48.8566,"lon":2.3522},
        {"name":"London","Iv":0.165,"Hv":2560,"lat":51.5074,"lon":-0.1278},
    ]
    tasks = [
        {"name":"LLM_NLP","Ta":500,"tap":40,"Ca":1,"Ua":500,"Pa":0.8},
        {"name":"LLM_IR","Ta":700,"tap":80,"Ca":2,"Ua":150,"Pa":1.2},
    ]
    V = [c["name"] for c in cities]
    tsd2 = {v: {} for v in V}
    for i,s in enumerate(V):
        for j,d in enumerate(V):
            tsd2[s][d] = 5 + 10*abs(i-j)
    # rav: T x V x A, for demo replicate same per hour
    rav_hour = {v: {t["name"]: 100.0 for t in tasks} for v in V}
    rav_full = {str(h): rav_hour for h in range(duration_hours)}
    return cities, tasks, tsd2, rav_full, duration_hours

def optimize_from_dict(cfg: Dict[str, Any]):
    try:
        from pulp import LpProblem
        HAS_PULP = True
    except Exception:
        HAS_PULP = False
    cities, tasks, tsd, rav_full, duration_hours = _build_example(cfg)
    if HAS_PULP:
        try:
            res = _optimize_milp(cities, tasks, tsd, rav_full, duration_hours)
            return {"status":"ok","method":"MILP","result":res}
        except Exception as e:
            tb = traceback.format_exc()
            # fallback
            res = _greedy_time_expanded(cities, tasks, tsd, rav_full, duration_hours)
            return {"status":"ok","method":"greedy-fallback","error":str(e),"trace":tb,"result":res}
    else:
        res = _greedy_time_expanded(cities, tasks, tsd, rav_full, duration_hours)
        return {"status":"ok","method":"greedy","result":res}

def _greedy_time_expanded(cities, tasks, tsd, rav_full, T):
    V = [c["name"] for c in cities]
    A = [t["name"] for t in tasks]
    # For each period, run simple greedy (place enough instances locally, else send to greenest)
    placements = {str(h): {v: {a:0 for a in A} for v in V} for h in range(T)}
    assignments = {str(h): [] for h in range(T)}
    for h in range(T):
        rav = rav_full[str(h)]
        # place
        for v in V:
            for a in A:
                Ua = next(t for t in tasks if t["name"]==a)["Ua"]
                demand = rav.get(v,{}).get(a,0.0)
                inst = math.ceil(demand / max(Ua,1e-9))
                placements[str(h)][v][a] = inst
        # assign
        for s in V:
            for a in A:
                remaining = rav.get(s,{}).get(a,0.0)
                # local first
                d = s
                cap = placements[str(h)][d][a] * next(t for t in tasks if t["name"]==a)["Ua"]
                take = min(remaining, cap)
                if take>0:
                    assignments[str(h)].append({"period":h,"task":a,"src":s,"dst":d,"load":take})
                remaining -= take
                if remaining<=1e-9: continue
                # else to greenest with capacity
                others = sorted(V, key=lambda x: next(c for c in cities if c["name"]==x)["Iv"])
                for d in others:
                    if d==s: continue
                    cap = max(placements[str(h)][d][a]*next(t for t in tasks if t["name"]==a)["Ua"] - sum(it["load"] for it in assignments[str(h)] if it["dst"]==d and it["task"]==a),0)
                    take = min(remaining, cap)
                    if take>0:
                        assignments[str(h)].append({"period":h,"task":a,"src":s,"dst":d,"load":take})
                        remaining -= take
                    if remaining<=1e-9: break
    return {"placements":placements,"assignments":assignments}

def _optimize_milp(cities, tasks, tsd, rav_full, T):
    # Simple MILP: for each period h, decide n_{a,v,h} integer >=0 (instances placed)
    # and b_{a,s,d,h} continuous assigned load. Objective: min sum_h sum_v,a n*Ca*Pa*Iv
    # Constraints per period: hw capacity, flow conservation, capacity consistency Ua*m >= b and b <= (Ua - 1/slack)*m if slack>0
    from pulp import LpProblem, LpMinimize, LpVariable, lpSum, PULP_CBC_CMD, LpInteger, LpStatus
    V = [c["name"] for c in cities]
    A = [t["name"] for t in tasks]
    city_map = {c["name"]:c for c in cities}
    task_map = {t["name"]:t for t in tasks}
    prob = LpProblem("time_expanded", LpMinimize)
    n = {}
    b = {}
    m = {}
    for h in range(T):
        for a in A:
            for v in V:
                n[(a,v,h)] = LpVariable(f"n_{a}_{v}_{h}", lowBound=0, cat=LpInteger)
        for a in A:
            for s in V:
                for d in V:
                    b[(a,s,d,h)] = LpVariable(f"b_{a}_{s}_{d}_{h}", lowBound=0)
                    m[(a,s,d,h)] = LpVariable(f"m_{a}_{s}_{d}_{h}", lowBound=0, cat=LpInteger)
    # Objective
    prob += lpSum([ n[(a,v,h)] * task_map[a]["Ca"] * task_map[a]["Pa"] * city_map[v]["Iv"] for h in range(T) for v in V for a in A ])
    # Per-period constraints
    for h in range(T):
        rav = rav_full[str(h)]
        # hw cap
        for v in V:
            prob += lpSum([ n[(a,v,h)] * task_map[a]["Ca"] for a in A ]) <= city_map[v]["Hv"]
        # flow conservation
        for s in V:
            for a in A:
                prob += lpSum([ b[(a,s,d,h)] for d in V ]) == rav.get(s,{}).get(a,0.0)
        # capacity consistency & latency bounds
        for s in V:
            for d in V:
                tsd_ms = tsd.get(s,{}).get(d,0.0)
                for a in A:
                    Ua = task_map[a]["Ua"]
                    Ta = task_map[a]["Ta"]
                    tap = task_map[a]["tap"]
                    slack = Ta - tsd_ms - tap
                    if slack <= 0:
                        prob += b[(a,s,d,h)] <= 0
                    else:
                        rhs_per_instance = Ua - 1.0/max(slack,1e-6)
                        if rhs_per_instance < 0:
                            prob += b[(a,s,d,h)] <= 0
                        else:
                            prob += b[(a,s,d,h)] <= rhs_per_instance * m[(a,s,d,h)]
                    prob += Ua * m[(a,s,d,h)] - b[(a,s,d,h)] >= 0
            # consistency: sum_s Ua*m_{a,s,d,h} == Ua * n_{a,d,h}
        for d in V:
            for a in A:
                prob += lpSum([ task_map[a]["Ua"] * m[(a,s,d,h)] for s in V ]) == task_map[a]["Ua"] * n[(a,d,h)]
    # Solve with time limit
    solver = PULP_CBC_CMD(msg=False, timeLimit=30)
    status = prob.solve(solver)
    status_str = LpStatus[status]
    # Extract solution
    placements = {str(h): {v:{a:0 for a in A} for v in V} for h in range(T)}
    assignments = {str(h):[] for h in range(T)}
    if status_str not in ("Optimal","Feasible"):
        raise RuntimeError("Solver status: "+status_str)
    for h in range(T):
        for v in V:
            for a in A:
                placements[str(h)][v][a] = int(round(n[(a,v,h)].value() or 0))
        for s in V:
            for d in V:
                for a in A:
                    val = float(b[(a,s,d,h)].value() or 0.0)
                    if val>1e-9:
                        assignments[str(h)].append({"period":h,"task":a,"src":s,"dst":d,"load":val,"m":int(round(m[(a,s,d,h)].value() or 0))})
    return {"placements":placements,"assignments":assignments,"status":status_str}
