import os
import glob
import random
import pandas as pd
from grading_system.grading_utils import get_grading_system

def list_files_with_pattern(directory, pattern):
    """Lists files in a directory matching a given pattern.

    Args:
        directory: The path to the directory.
        pattern: The file pattern to match (e.g., "*.txt", "image*.png").

    Returns:
        A list of file paths that match the pattern.
    """
    search_pattern = os.path.join(directory, pattern)
    return glob.glob(search_pattern)

def main():
    #methods = ["test-chat-low", "test-chat-mid", "test-chat-high"]
    methods = ["deepseek-r1", "gpt-4.1-nano", "o4-mini", "o3", "gpt-4.1"]
    random.shuffle(methods)
    mapping = "../samples/results/mapping.txt"
    if os.path.exists(mapping):
        with open(mapping, "r") as f:
            methods = [line.strip().split(": ")[1] for line in f.readlines()]
    else:
        with open(mapping, "w") as f:
            for i, m in enumerate(methods):
                f.write(f"Model {i+1}: {m}\n")

    rubrics = list_files_with_pattern("../samples", "*rubric*.docx")
    assignments = list_files_with_pattern("../samples", "*sample_*.docx")
    for rubric_path in rubrics:
        path = os.path.join("../samples/results/", os.path.basename(rubric_path).split('.')[0] + ".xlsx")
        if not os.path.exists(path):
            data = []
            for final_assignment_path in assignments:
                assignment_data = [os.path.basename(final_assignment_path)]
                results = []
                columns = [("", "", "Name")]
                for method in methods:
                    grading_system = get_grading_system(method)
                    results.append(grading_system.grade_assignment(final_assignment_path, rubric_path))
                
                result = results[0]
                criteria = []
                sub_criteria = []
                for criterion, details in result['criteria_scores'].items():
                    criteria.append(criterion)
                    if len(details['sub_scores']) > 0:
                        sub_criteria.append(list(details['sub_scores'].keys()))
                    else:
                        sub_criteria.append([])
                assignment_data.append(result["assignment_text"])
                columns.append(("", "", "Assignment Text"))
                
                for criterion, sub_criterion in zip(criteria, sub_criteria):
                    if len(sub_criterion) > 0:
                        for sub in sub_criterion:
                            for i, r in enumerate(results):
                                columns.append((criterion, sub, f"Model {i+1} explanation"))
                                assignment_data.append(r['criteria_scores'][criterion]['sub_scores'][sub]['justification'])
                                columns.append((criterion, sub, f"Model {i+1} score"))
                                assignment_data.append(r['criteria_scores'][criterion]['sub_scores'][sub]['score'])
                    else:
                        for i, r in enumerate(results):
                            columns.append((criterion, "", f"Model {i+1} explanation"))
                            assignment_data.append(r['criteria_scores'][criterion]['justification'])
                            columns.append((criterion, "", f"Model {i+1} score"))
                            assignment_data.append(r['criteria_scores'][criterion]['score'])
                data.append(assignment_data)
                
            multi_index = pd.MultiIndex.from_tuples(columns, names=["Criteria", "Sub-criteria", "Model"])
            df = pd.DataFrame(data=data, columns=multi_index)
            df.to_excel(path)

if __name__ == "__main__":
    main()