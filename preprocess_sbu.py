import os
import pandas as pd
from docx import Document

cycles = 3
problem = 1
for cycle in range(1, cycles+1):
    for set_type in ["Practice", "Quiz"]:
        for i in range(2):
            os.makedirs(f"../samples/SBU MEC 260/Problem {problem+i}", exist_ok=True)
        
        df = pd.read_excel(f"../Updated Report and Collected Dataset_SBU/Assigned Questions and Collected Response/Cycle {cycle}/MEC 260 Online {set_type} Set {cycle} (Responses).xlsx")
        df = df.rename(columns={"Answer:": "Answer:.0", "Rationale:": "Rationale:.0"})
        for _, row in df.iterrows():
            student_id = row["Your SBU ID"]
            for i in range(2):
                document = Document()
                document.add_paragraph(str(row[f"Rationale:.{i}"]))
                document.save(f"../samples/SBU MEC 260/Problem {problem+i}/{student_id}.docx")

        problem += 2
        