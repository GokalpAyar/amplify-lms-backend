import { useState } from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import { uploadAssignment, type AssignmentUploadResponse } from "../services/api";

export default function TeacherUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<AssignmentUploadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { isLoaded: isAuthLoaded, isSignedIn, getToken } = useAuth();
  const { isLoaded: isUserLoaded, user: currentUser } = useUser();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!file) return;
    if (!isAuthLoaded || !isUserLoaded) {
      setErr("Authentication is still loading. Please try again.");
      return;
    }
    if (!isSignedIn || !currentUser) {
      setErr("You must be signed in to upload assignments.");
      return;
    }
    setLoading(true);
    try {
      const clerkToken = await getToken();
      if (!clerkToken) {
        throw new Error("Unable to retrieve authentication token.");
      }
      const data = await uploadAssignment(
        {
          file,
          owner_id: currentUser.id,
        },
        {
          clerkToken,
        },
      );
      setResult(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed";
      setErr(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 20, maxWidth: 720, margin: "0 auto" }}>
      <h1>Teacher: Upload Assignment (.docx or .txt)</h1>
      <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
        <input type="file" accept=".docx,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button
          type="submit"
          disabled={!file || loading || !isAuthLoaded || !isUserLoaded || !isSignedIn}
          style={{ marginLeft: 10 }}
        >
          {loading ? "Uploading..." : "Upload"}
        </button>
      </form>

      {err && <p style={{ color: "red" }}>{err}</p>}

      {result && (
        <div style={{ marginTop: 16, border: "1px solid #ddd", padding: 12 }}>
          <p>
            <b>Assignment ID:</b> {result.assignmentId}
          </p>
          <p>
            <b>Questions:</b> {result.questionsCount}
          </p>
          <p>
            <b>Student Link:</b>{" "}
            <a href={`/student/${result.assignmentId}`}>/student/{result.assignmentId}</a>
          </p>
        </div>
      )}
    </div>
  );
}
