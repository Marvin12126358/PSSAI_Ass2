# Assignment 2 – Parallel Machine Scheduling with Metaheuristics
**Problem Solving and Search in AI 2026**

---

## 1. Algorithm Description

The implemented metaheuristic is **Simulated Annealing (SA)**, a trajectory-based local search algorithm that probabilistically accepts worse solutions to escape local optima. SA is well-suited to this problem because the objective landscape is non-convex due to the interaction of precedence, setup time, and resource constraints.

### Search Space

The **search variable** is the machine assignment:

```
assignment: job_id → machine_id
```

Each assignment implicitly defines a complete schedule because, given a fixed machine assignment, the **start times are computed deterministically** by a greedy earliest-start procedure. This reduces the search space from all possible (assignment × start-time) combinations to just the space of machine assignments.

### Start Time Computation

Jobs are processed in **topological order** (respecting all precedence constraints). For each job, the earliest feasible start time is the maximum of three lower bounds:

| Constraint | Lower bound |
|---|---|
| Machine sequencing | end of last job on same machine + setup time |
| Precedence | end of latest predecessor job |
| Resource capacity | first slot `[t, t+pt)` where all required resource capacities are available |

For the resource constraint, a **change-point scan** is used: instead of checking every time tick individually, only the boundary points of resource availability periods and scheduled job intervals are checked. This reduces the inner loop from O(horizon) to O(n + r) per job, where n is the number of already-scheduled jobs and r is the number of resource periods.

If no feasible slot exists for a job (e.g. the required resource window closes before the precedence constraint allows the job to start), the entire assignment is declared **infeasible** and discarded.

### Objective Function

```
cost = tardiness + makespan
     = Σ_j max(0, end_j − due_j)  +  max_j(end_j)
```

### Neighbourhood Moves

Three move types are applied uniformly at random:

1. **Reassign** – move one randomly chosen job to a different eligible machine
2. **Swap** – exchange the machines of two randomly chosen jobs (only if both are eligible on each other's machine)
3. **Load-balance** – move a randomly chosen job to the least-loaded eligible machine

### Acceptance Criterion

A neighbour with cost delta worse than the current solution is accepted with probability:

```
P(accept) = exp(−delta / T)
```

where T is the current temperature. Infeasible neighbours are always rejected.

### Initial Solution

A greedy heuristic sorts jobs by due time and assigns each to the eligible machine with the lowest current total processing load.

### Cooling Schedule

Geometric cooling: `T_{k+1} = alpha * T_k`, starting at `T_init` and stopping when `T < T_min` or the time limit is reached.

---

## 2. Experiments / Parameter Selection

Parameters were selected manually based on standard SA guidelines and verified on the toy instance. The goal was to allow the algorithm to explore broadly at first (high T) and converge to a good solution within the time budget.

### Parameter Configurations Tested (toy instance, 5s time limit)

| T_init | alpha | Iterations/temp | Steps | Evals | Cost |
|--------|-------|-----------------|-------|-------|------|
| 100    | 0.990 | 50              | 688   | 34,400  | 7 |
| **500**    | **0.995** | **100**         | **1146**  | **114,600** | **7** ✓ |
| 1000   | 0.999 | 200             | 574   | 114,800 | 7 |
| 200    | 0.980 | 100             | 377   | 37,700  | 7 |

All configurations found the optimum on the toy instance. The selected configuration (T=500, α=0.995, 100 iterations/temp) was chosen because it achieves a good balance between exploration (slow cooling) and the number of evaluations performed within the time budget.

### Final Parameters

| Parameter | Value | Rationale |
|---|---|---|
| `T_init` | 500 | Allows acceptance of significantly worse solutions early on |
| `T_min` | 0.1 | Effectively only improving moves accepted at end |
| `alpha` | 0.995 | Slow cooling — ~1700 temperature steps to convergence |
| `iterations_per_temp` | 100 | Enough neighbourhood exploration per temperature level |
| Time limit | 60 s | Balances quality and runtime for larger instances |

---

## 3. Results on Benchmark Instances

### Toy Instance (`PSSAI_PMS_toy`, 6 jobs, 2 machines, 2 resources)

5 independent runs with different random seeds (10 s time limit each):

| Run | Seed | Cost | Tardiness | Makespan |
|-----|------|------|-----------|----------|
| 1   | 42   | 7    | 0         | 7        |
| 2   | 123  | 7    | 0         | 7        |
| 3   | 7    | 7    | 0         | 7        |
| 4   | 999  | 7    | 0         | 7        |
| 5   | 2024 | 7    | 0         | 7        |

| Metric | Value |
|--------|-------|
| **Best** | **7** |
| **Average** | **7.00** |
| **Std. Dev.** | **0.00** |

The algorithm consistently finds the optimal solution (tardiness = 0) on the toy instance across all seeds. Each run completes ~170,000 evaluations in approximately 7.5 seconds.

> **Note:** Results for the full set of 20 benchmark instances will be added once the instance files are available.

---

## 4. Conclusions / Lessons Learned

- **Machine assignment as search variable** is effective: delegating start time computation to a deterministic greedy procedure keeps the search space tractable and guarantees that every evaluated assignment either produces a valid schedule or is immediately identified as infeasible.

- **Infeasibility detection is critical.** A naive per-tick resource check caused infinite loops when a resource window closed permanently. The change-point scan correctly identifies permanently infeasible assignments in O(n) time.

- **The toy instance is easily solved.** All 4 tested parameter configurations found cost=7 with zero tardiness. The instance is small enough that even a fast-cooling configuration converges to the optimum.

- **For larger instances**, the bottleneck will be the `compute_start_times` function: its cost grows with the number of jobs and resource constraints. Caching partial schedules or using a more sophisticated data structure (e.g. segment tree for resource usage) would be needed for very large instances.

- **Parameter tuning** did not make a significant difference on the toy instance. For the benchmark instances, irace or a simple grid search over (T_init, alpha) would be the recommended next step.

---

## 5. Instructions to Run the Program

### Requirements

- Python 3.10 or later (uses `int | None` type hints)
- No external dependencies

### Setup

```bash
git clone https://github.com/Marvin12126358/PSSAI_Ass2.git
cd PSSAI_Ass2
git checkout claude/parallel-scheduling-metaheuristics-VFlGw
```

### Solve a single instance

```bash
python solver.py <instance.json> <output.solution.json> [time_limit_seconds]
```

Example:
```bash
python solver.py PSSAI_Topic_A_PMS_Instances/PSSAI_PMS_toy.json results/PSSAI_PMS_toy.solution.json 60
```

### Solve all instances at once

Place all instance `.json` files into `PSSAI_Topic_A_PMS_Instances/`, then:

```bash
python solver.py
```

Solutions are written to `results/<instance_name>.solution.json`.

### Validate a solution

```bash
python PSSAI_Topic_A_PMS_Instances/solution_validator.py \
  PSSAI_Topic_A_PMS_Instances/PSSAI_PMS_toy.json \
  results/PSSAI_PMS_toy.solution.json
```

Expected output:
```
Solution is feasible
Tardiness: 0
Makespan: 7
Total solution cost: 7
```

### Validate all solutions at once (bash)

```bash
for sol in results/*.solution.json; do
  name=$(basename "$sol" .solution.json)
  echo "=== $name ==="
  python PSSAI_Topic_A_PMS_Instances/solution_validator.py \
    "PSSAI_Topic_A_PMS_Instances/${name}.json" "$sol"
done
```
