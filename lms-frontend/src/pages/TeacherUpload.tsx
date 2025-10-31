import { useState } from "react";
import { uploadAssignment } from "../services/api";

export default function TeacherUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!file) return;
    setLoading(true);
    try {
      const data = await uploadAssignment(file);
      setResult(data);
    } catch (e: any) {
      setErr(e?.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 20, maxWidth: 720, margin: "0 auto" }}>
      <h1>Teacher: Upload Assignment (.docx or .txt)</h1>
      <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
        <input type="file" accept=".docx,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button type="submit" disabled={!file || loading} style={{ marginLeft: 10 }}>
          {loading ? "Uploading..." : "Upload"}
        </button>
      </form>

      {err && <p style={{ color: "red" }}>{err}</p>}

      {result && (
        <div style={{ marginTop: 16, border: "1px solid #ddd", padding: 12 }}>
          <p><b>Assignment ID:</b> {result.assignmentId}</p>
          <p><b>Questions:</b> {result.questionsCount}</p>
          <p>
            <b>Student Link:</b>{" "}
            <a href={`/student/${result.assignmentId}`}>/student/{result.assignmentId}</a>
          </p>
        </div>
      )}
    </div>
  );
}
