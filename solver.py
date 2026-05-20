"""
Parallel Machine Scheduling - Simulated Annealing Metaheuristic
Minimises: sum of tardiness + makespan
"""
import json
import math
import random
import sys
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "PSSAI_Topic_A_PMS_Instances"
RESULTS_DIR = BASE_DIR / "results"


# ─── Instance helpers ─────────────────────────────────────────────────────────

def load_instance(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def save_solution(solution: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(solution, f, indent=2)


# ─── Pre-processing ────────────────────────────────────────────────────────────

class InstanceData:
    """Pre-processed instance for fast repeated evaluation."""

    def __init__(self, raw: dict):
        self.jobs = {j["Id"]: j for j in raw["Jobs"]}
        self.job_ids = [j["Id"] for j in raw["Jobs"]]
        self.machines = [m["Id"] for m in raw["Machines"]]
        self.n = len(self.jobs)

        # topological order (fixed regardless of assignment)
        self.topo_order = self._topo_sort()

        # resource periods: {rid: sorted list of {"Start","End","Capacity"}}
        # last period extended to infinity with cap=0
        self.res_periods: dict[int, list] = {}
        for r in raw.get("Resources", []):
            periods = sorted(r["AvailabilityPeriods"], key=lambda p: p["Start"])
            if periods:
                periods.append({"Start": periods[-1]["End"], "End": 10**9, "Capacity": 0})
            self.res_periods[r["Id"]] = periods

    def _topo_sort(self):
        in_deg = {jid: 0 for jid in self.jobs}
        succ = {jid: [] for jid in self.jobs}
        for jid, j in self.jobs.items():
            for p in j["PrecedenceJobIds"]:
                in_deg[jid] += 1
                succ[p].append(jid)
        ready = [jid for jid, d in in_deg.items() if d == 0]
        order = []
        while ready:
            cur = ready.pop(0)
            order.append(cur)
            for s in succ[cur]:
                in_deg[s] -= 1
                if in_deg[s] == 0:
                    ready.append(s)
        return order if len(order) == self.n else None

    def res_cap_at(self, rid: int, t: int) -> int:
        for p in self.res_periods.get(rid, []):
            if p["Start"] <= t < p["End"]:
                return p["Capacity"]
        return 0


# ─── Resource slot finder ──────────────────────────────────────────────────────

def earliest_feasible_start(inst: InstanceData,
                             required_resources: list,
                             t_earliest: int,
                             pt: int,
                             res_usage: dict) -> int | None:
    """
    Find the earliest start >= t_earliest such that a job with the given
    resource requirements can run for `pt` time units.

    Returns the start time, or None if no feasible slot exists within the
    resource availability windows.
    """
    if not required_resources:
        return t_earliest

    # Collect all time-point boundaries: resource period starts/ends + scheduled job starts/ends
    change_points = set()
    for rr in required_resources:
        rid = rr["ResourceId"]
        for p in inst.res_periods.get(rid, []):
            change_points.add(p["Start"])
            change_points.add(p["End"])
        for s, e, _ in res_usage.get(rid, []):
            change_points.add(s)
            change_points.add(e)
    change_points.add(t_earliest)

    # Convert to sorted list; only consider times >= t_earliest
    sorted_cps = sorted(cp for cp in change_points if cp >= t_earliest)

    # Maximum useful horizon: end of last non-zero resource period
    max_horizon = t_earliest
    for rr in required_resources:
        rid = rr["ResourceId"]
        for p in inst.res_periods.get(rid, []):
            if p["Capacity"] > 0:
                max_horizon = max(max_horizon, p["End"])

    if max_horizon == t_earliest:
        # No non-zero capacity period exists at or after t_earliest
        return None

    # Walk through candidate start times: each change point is a candidate
    # We try each interval [cp, next_cp) as a start, then verify feasibility
    # of the window [start, start+pt)
    candidate_starts = []
    for cp in sorted_cps:
        if cp < max_horizon:
            candidate_starts.append(cp)
    # Also add points one past each non-zero-to-zero transition
    # (already covered by change_points)

    t = t_earliest
    while t < max_horizon:
        feasible = True
        advance_to = None

        for rr in required_resources:
            rid = rr["ResourceId"]
            needed = rr["Capacity"]
            if needed == 0:
                continue

            # Check every sub-interval within [t, t+pt) where the combined
            # capacity function is constant (i.e., between change points)
            cp_in_window = sorted(
                cp for cp in change_points if t < cp < t + pt
            )
            check_times = [t] + cp_in_window

            for tick in check_times:
                avail = inst.res_cap_at(rid, tick)
                used = sum(cap for s, e, cap in res_usage.get(rid, [])
                           if s <= tick < e)
                if avail - used < needed:
                    feasible = False
                    # Find best advance: end of conflicting jobs or next period
                    block_end = tick + 1
                    for s, e, _ in res_usage.get(rid, []):
                        if s <= tick < e:
                            block_end = max(block_end, e)
                    # Jump to next period start > tick
                    for p in inst.res_periods.get(rid, []):
                        if p["Start"] > tick and p["Capacity"] >= needed:
                            block_end = min(block_end, p["Start"])
                            break
                    advance_to = block_end if advance_to is None else max(advance_to, block_end)
                    break  # stop checking ticks for this resource
            if not feasible:
                break

        if feasible:
            return t

        if advance_to is None or advance_to <= t:
            advance_to = t + 1

        # Jump directly to next change point >= advance_to to avoid 1-by-1 iteration
        t = advance_to
        # snap to the nearest useful change point >= t
        idx = 0
        for cp in sorted_cps:
            if cp >= t:
                t = cp
                break

        # If t hasn't moved forward, step by 1 to avoid infinite loop
        if t == advance_to and t not in sorted_cps:
            pass  # t is already set to advance_to

    return None  # no feasible slot found


# ─── Schedule evaluation ───────────────────────────────────────────────────────

def compute_start_times(inst: InstanceData, assignment: dict) -> dict | None:
    """
    Compute earliest feasible start times for all jobs given machine assignment.
    Returns {job_id: start_time} or None if no feasible schedule exists.
    """
    if inst.topo_order is None:
        return None

    jobs = inst.jobs
    start = {}
    res_usage: dict[int, list] = {rid: [] for rid in inst.res_periods}

    for jid in inst.topo_order:
        j = jobs[jid]
        machine = assignment[jid]
        pt = j["ProcessingTime"]

        # ── earliest start from machine sequencing ────────────────────────
        machine_jobs = [(start[oid], oid)
                        for oid in start if assignment[oid] == machine]
        if not machine_jobs:
            t_machine = j["InitialSetupTime"]
        else:
            last_s, last_id = max(machine_jobs, key=lambda x: x[0])
            last_end = last_s + jobs[last_id]["ProcessingTime"]
            setup = j["JobSetupTimes"][last_id - 1]
            t_machine = last_end + setup

        # ── earliest start from precedences ──────────────────────────────
        t_prec = max(
            (start[p] + jobs[p]["ProcessingTime"] for p in j["PrecedenceJobIds"]),
            default=0
        )

        t_earliest = max(t_machine, t_prec)

        # ── push past resource conflicts ──────────────────────────────────
        t = earliest_feasible_start(inst, j["RequiredResources"], t_earliest, pt, res_usage)
        if t is None:
            return None  # truly infeasible assignment

        start[jid] = t
        for rr in j["RequiredResources"]:
            rid = rr["ResourceId"]
            if rid in res_usage:
                res_usage[rid].append((t, t + pt, rr["Capacity"]))

    return start


def evaluate(inst: InstanceData, assignment: dict) -> tuple:
    """Returns (cost, start_times) or (inf, None)."""
    start_times = compute_start_times(inst, assignment)
    if start_times is None:
        return float("inf"), None

    jobs = inst.jobs
    tardiness = sum(
        max(0, start_times[jid] + j["ProcessingTime"] - j["DueTime"])
        for jid, j in jobs.items()
    )
    makespan = max(start_times[jid] + jobs[jid]["ProcessingTime"] for jid in jobs)
    return tardiness + makespan, start_times


# ─── Initial solution ──────────────────────────────────────────────────────────

def greedy_initial(inst: InstanceData) -> dict:
    """Assign each job to its first eligible machine, ordering by due time."""
    jobs = sorted(inst.jobs.values(), key=lambda j: j["DueTime"])
    assignment = {}
    machine_load: dict[int, int] = {m: 0 for m in inst.machines}

    for j in jobs:
        eligible = j["EligibleMachineIds"]
        best_m = min(eligible, key=lambda m: machine_load.get(m, 0))
        assignment[j["Id"]] = best_m
        machine_load[best_m] = machine_load.get(best_m, 0) + j["ProcessingTime"]

    return assignment


def random_initial(inst: InstanceData, rng: random.Random) -> dict:
    """Random assignment respecting machine eligibility."""
    return {j["Id"]: rng.choice(j["EligibleMachineIds"])
            for j in inst.jobs.values()}


# ─── Neighbourhood moves ───────────────────────────────────────────────────────

def neighbour(inst: InstanceData, assignment: dict) -> dict:
    jobs = list(inst.jobs.values())
    move = random.randint(0, 2)
    new_asgn = dict(assignment)

    if move == 0:
        # Reassign one job to a different eligible machine
        j = random.choice(jobs)
        eligible = j["EligibleMachineIds"]
        if len(eligible) > 1:
            current = new_asgn[j["Id"]]
            options = [m for m in eligible if m != current]
            new_asgn[j["Id"]] = random.choice(options)

    elif move == 1:
        # Swap machines of two jobs (if eligibility allows)
        if len(jobs) >= 2:
            j1, j2 = random.sample(jobs, 2)
            m1, m2 = new_asgn[j1["Id"]], new_asgn[j2["Id"]]
            if (m1 != m2
                    and m2 in j1["EligibleMachineIds"]
                    and m1 in j2["EligibleMachineIds"]):
                new_asgn[j1["Id"]] = m2
                new_asgn[j2["Id"]] = m1

    else:
        # Move a random job to the least-loaded eligible machine
        j = random.choice(jobs)
        eligible = j["EligibleMachineIds"]
        if len(eligible) > 1:
            load: dict[int, int] = {}
            for jid, mid in new_asgn.items():
                load[mid] = load.get(mid, 0) + 1
            best = min(eligible, key=lambda m: load.get(m, 0))
            new_asgn[j["Id"]] = best

    return new_asgn


# ─── Simulated Annealing ───────────────────────────────────────────────────────

def simulated_annealing(
    inst: InstanceData,
    max_time: float = 60.0,
    t_init: float = 500.0,
    t_min: float = 0.1,
    alpha: float = 0.995,
    iterations_per_temp: int = 100,
    seed: int = 42,
) -> tuple:
    """Returns (best_assignment, best_cost, best_start_times)."""
    rng = random.Random(seed)
    random.seed(seed)

    # Try greedy first; fall back to random if infeasible
    current_asgn = greedy_initial(inst)
    current_cost, current_starts = evaluate(inst, current_asgn)

    if current_starts is None:
        # greedy is infeasible; try a few random starts
        for _ in range(50):
            asgn = random_initial(inst, rng)
            cost, starts = evaluate(inst, asgn)
            if starts is not None:
                current_asgn, current_cost, current_starts = asgn, cost, starts
                break
        if current_starts is None:
            return current_asgn, float("inf"), None

    best_asgn = dict(current_asgn)
    best_cost = current_cost
    best_starts = current_starts

    T = t_init
    start_wall = time.time()
    iteration = 0
    total_evals = 0

    while T > t_min and (time.time() - start_wall) < max_time:
        for _ in range(iterations_per_temp):
            new_asgn = neighbour(inst, current_asgn)
            new_cost, new_starts = evaluate(inst, new_asgn)
            total_evals += 1

            if new_starts is None:
                continue  # skip infeasible neighbours

            delta = new_cost - current_cost
            if delta < 0 or random.random() < math.exp(-delta / T):
                current_asgn = new_asgn
                current_cost = new_cost
                current_starts = new_starts

                if new_cost < best_cost:
                    best_asgn = dict(new_asgn)
                    best_cost = new_cost
                    best_starts = new_starts

        T *= alpha
        iteration += 1

    elapsed = time.time() - start_wall
    print(f"  SA: {iteration} temp steps, {total_evals} evals, {elapsed:.1f}s, best cost={best_cost}")
    return best_asgn, best_cost, best_starts


# ─── Solution builder ──────────────────────────────────────────────────────────

def build_solution(assignment: dict, start_times: dict) -> dict:
    jobs = []
    for jid, mid in assignment.items():
        jobs.append({
            "JobId": jid,
            "StartTime": start_times[jid],
            "MachineId": mid
        })
    return {"Jobs": sorted(jobs, key=lambda x: x["JobId"])}


# ─── Main ──────────────────────────────────────────────────────────────────────

def solve_instance(instance_path: str, result_path: str, max_time: float = 60.0):
    print(f"\nSolving: {Path(instance_path).name}")
    raw = load_instance(instance_path)
    inst = InstanceData(raw)
    print(f"  Jobs={inst.n}, Machines={len(inst.machines)}, Resources={len(inst.res_periods)}")

    asgn, cost, starts = simulated_annealing(inst, max_time=max_time)

    if starts is None:
        print("  WARNING: no feasible solution found")
        return None

    sol = build_solution(asgn, starts)
    save_solution(sol, result_path)
    print(f"  Saved: {Path(result_path).name}  (cost={cost})")
    return cost


if __name__ == "__main__":
    RESULTS_DIR.mkdir(exist_ok=True)

    if len(sys.argv) == 3:
        solve_instance(sys.argv[1], sys.argv[2])
        sys.exit(0)

    if len(sys.argv) == 4:
        solve_instance(sys.argv[1], sys.argv[2], float(sys.argv[3]))
        sys.exit(0)

    # Run on all instances in the instances directory
    instance_files = sorted([
        f for f in INSTANCE_DIR.glob("*.json")
        if not f.name.endswith(".solution.json")
    ])

    if not instance_files:
        print("No instance files found. Add .json files to PSSAI_Topic_A_PMS_Instances/")
        sys.exit(1)

    for inst_file in instance_files:
        result_file = RESULTS_DIR / (inst_file.stem + ".solution.json")
        solve_instance(str(inst_file), str(result_file), max_time=60.0)
