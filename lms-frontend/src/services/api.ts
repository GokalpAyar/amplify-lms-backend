export const BASE_URL = import.meta.env.VITE_API_URL as string;

export type AssignmentUploadResponse = {
  assignmentId: string;
  questionsCount: number;
  [key: string]: unknown;
};

type AssignmentUploadPayload = {
  file: File;
  owner_id: string;
};

type UploadAssignmentAuth = {
  clerkToken: string;
};

export async function uploadAssignment(
  payload: AssignmentUploadPayload,
  auth: UploadAssignmentAuth,
): Promise<AssignmentUploadResponse> {
  const fd = new FormData();
  fd.append("file", payload.file);
  fd.append("owner_id", payload.owner_id);
  const res = await fetch(`${BASE_URL}/upload-assignment/`, {
    method: "POST",
    body: fd,
    headers: {
      "X-Clerk-Session-Token": auth.clerkToken,
      "X-Clerk-User-Id": payload.owner_id,
    },
  });
  if (!res.ok) throw new Error("Upload failed");
  const data = (await res.json()) as AssignmentUploadResponse;
  return data;
}

export async function getAssignment(assignmentId: string) {
  const res = await fetch(`${BASE_URL}/assignments/${assignmentId}`);
  if (!res.ok) throw new Error("Fetch assignment failed");
  return res.json();
}

export async function submitResponses(payload: unknown) {
  const res = await fetch(`${BASE_URL}/submissions/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Submit failed");
  return res.json();
}
