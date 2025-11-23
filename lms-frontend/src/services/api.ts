export const BASE_URL = import.meta.env.VITE_API_URL as string;

export async function uploadAssignment(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE_URL}/upload-assignment/`, { method: "POST", body: fd });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

export async function getAssignment(assignmentId: string) {
  const res = await fetch(`${BASE_URL}/assignments/${assignmentId}`);
  if (!res.ok) throw new Error("Fetch assignment failed");
  return res.json();
}

export async function submitResponses(payload: any) {
  const res = await fetch(`${BASE_URL}/submissions/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Submit failed");
  return res.json();
}
