import sys

import json_converter

# Kompakte interne Repräsentation einer Lösung


data = {}

def total_cost(solution, jobs) -> int:
    tardiness = sum(max(0, s["end"] - jobs[jid]["DueTime"])
                    for jid, s in solution.items())
    makespan  = max(s["end"] for s in solution.values())
    return tardiness + makespan



def basic_sort(data):
    jobs_sorted = sorted(data["Jobs"], key=lambda job: job["DueTime"])
    print("Jobs sorted in dueTime")
    for i in range(len(jobs_sorted)):
        print(jobs_sorted[i]["Id"])

    # Press the green button in the gutter to run the script.
if __name__ == '__main__':
    #print_hi('PyCharm')
    data = json_converter.load_instance(sys.argv[1])
    basic_sort(data)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
