import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "PSSAI_Topic_A_PMS_Instances"

def load_all_instances() -> dict:
    instance_files = sorted([
        f for f in INSTANCE_DIR.glob("*.json")
        if not f.name.endswith(".solution.json")
    ])

    if not instance_files:
        raise FileNotFoundError(f"No instances found in {INSTANCE_DIR}")

    instances = {}

    for instance_file in instance_files:
        with instance_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        instances[instance_file.stem] = data
        print(f"Loaded: {instance_file.stem} "
              f"(jobs={len(data['Jobs'])}, "
              f"machines={len(data['Machines'])}, "
              f"resources={len(data.get('Resources', []))})")

    print(f"\nTotal: {len(instances)} instances loaded.")
    return instances

if __name__ == "__main__":
    instances = load_all_instances()