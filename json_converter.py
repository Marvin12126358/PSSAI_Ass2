import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "PSSAI_Topic_A_PMS_Instances"

def load_instance(instance_name: str) -> dict:
    instance_file = INSTANCE_DIR / f"{instance_name}.json"

    if not instance_file.exists():
        raise FileNotFoundError(f"Instance not found: {instance_file}")

    with instance_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded: {instance_name}")
    print(f"  Jobs:      {len(data['Jobs'])}")
    print(f"  Machines:  {len(data['Machines'])}")
    print(f"  Resources: {len(data.get('Resources', []))}")

    return data

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python metaheuristic/load_instance.py INSTANCE_NAME")
        print("Example: python metaheuristic/load_instance.py PSSAI_PMS_j10_m3_r2_3")
        sys.exit(1)

    instance_name = sys.argv[1]
    data = load_instance(instance_name)