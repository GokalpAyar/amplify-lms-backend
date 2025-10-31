import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getAssignment, submitResponses } from "../services/api";

type MCQ = { id: string; type: "mcq"; stem: string; options: string[]; answer?: string | null };
type Open = { id: string; type: "open"; prompt: string };
type Question = MCQ | Open;

export default function StudentSubmit() {
  const { assignmentId } = useParams();
  const [assignment, setAssignment] = useState<any>(null);
  const [responses, setResponses] = useState<Record<string, any>>({});
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!assignmentId) return;
    (async () => {
      try {
        const data = await getAssignment(assignmentId);
        if ((data as any).error) setErr("Assignment not found");
        else setAssignment(data);
      } catch {
        setErr("Failed to load assignment");
      }
    })();
  }, [assignmentId]);

  const onChange = (qid: string, val: any) =>
    setResponses((r) => ({ ...r, [qid]: val }));

  const onSubmit = async () => {
    if (!assignmentId) return;
    try {
      const res = await submitResponses({
        assignmentId,
        studentId: "demo-student",
        responses,
      });
      setResult(res);
    } catch {
      setErr("Submit failed");
    }
  };

  if (err) return <div style={{ padding: 20 }}>{err}</div>;
  if (!assignment) return <div style={{ padding: 20 }}>Loading…</div>;

  return (
    <div style={{ padding: 20, maxWidth: 800, margin: "0 auto" }}>
      <h1>Student: Assignment</h1>
      <h3>{assignment.title}</h3>

      {(assignment.questions as Question[]).map((q) => (
        <div key={q.id} style={{ border: "1px solid #eee", padding: 12, marginTop: 12 }}>
          {q.type === "mcq" ? (
            <>
              <div><b>{q.id}.</b> {q.stem}</div>
              {q.options.map((opt, idx) => (
                <label key={idx} style={{ display: "block", marginTop: 6 }}>
                  <input
                    type="radio"
                    name={q.id}
                    value={opt}
                    onChange={(e) => onChange(q.id, e.target.value)}
                  />{" "}
                  {opt}
                </label>
              ))}
            </>
          ) : (
            <>
              <div><b>{q.id}.</b> {q.prompt}</div>
              <textarea
                style={{ width: "100%", marginTop: 6 }}
                rows={3}
                onChange={(e) => onChange(q.id, e.target.value)}
              />
            </>
          )}
        </div>
      ))}

      <button onClick={onSubmit} style={{ marginTop: 16 }}>Submit</button>

      {result && (
        <div style={{ marginTop: 16 }}>
          <h3>Result</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
