import { api } from "./client";

export async function createProject(name: string, projectDir?: string, ownerId?: string) {
  const { data } = await api.post("/projects", { name, project_dir: projectDir || undefined, owner_id: ownerId });
  return data as { project_id: string; name: string };
}

export async function getProject(projectId: string, videoId?: string) {
  const { data } = await api.get(`/projects/${projectId}`, { params: { summary: true, ...(videoId ? { video_id: videoId } : {}) } });
  return data;
}

export async function listProjects(q = "", offset = 0, limit = 50, options?: { owner_id?: string; all_accounts?: boolean; deleted?: boolean }) {
  const { data } = await api.get("/projects", { params: { q, offset, limit, ...options } });
  return data as { projects: ProjectSummary[]; total: number };
}

export async function uploadVideo(projectId: string, file: File, relativePath?: string) {
  const form = new FormData();
  form.append("video", file);
  if (relativePath) form.append("relative_path", relativePath);
  const { data } = await api.post(`/projects/${projectId}/video`, form);
  return data;
}

export async function uploadVideoFolder(projectId: string, files: File[], options?: { onProgress?: (completed: number, total: number) => void }) {
  let completed = 0;
  let latest: any;
  options?.onProgress?.(completed, files.length);
  for (const file of files) {
    const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    try {
      latest = await uploadVideo(projectId, file, relativePath);
    } catch (error) {
      throw new Error(`Failed to upload ${relativePath}: ${error instanceof Error ? error.message : "request failed"}`);
    } finally {
      completed += 1;
      options?.onProgress?.(completed, files.length);
    }
  }
  return latest;
}

export async function activateVideo(projectId: string, videoId: string) {
  const { data } = await api.post(`/projects/${projectId}/videos/${videoId}/activate`, {}, { params: { summary: true } });
  return data;
}

export async function createObject(projectId: string, category: string, frameIndex: number, videoId?: string) {
  const { data } = await api.post(`/projects/${projectId}/objects`, { category, frame_index: frameIndex }, { params: videoId ? { video_id: videoId } : undefined });
  return data;
}

export async function updateObject(projectId: string, objectId: number, patch: Record<string, unknown>, videoId?: string) {
  const { data } = await api.patch(`/projects/${projectId}/objects/${objectId}`, patch, { params: videoId ? { video_id: videoId } : undefined });
  return data;
}

export async function removeObjectFromSession(projectId: string, objectId: number, sessionId: string, videoId?: string) {
  const { data } = await api.post(
    `/projects/${projectId}/objects/${objectId}/session/remove`,
    {},
    { params: { session_id: sessionId, ...(videoId ? { video_id: videoId } : {}) } }
  );
  return data as { ok: boolean; object_id: number; session_id: string };
}

export async function deleteObject(projectId: string, objectId: number, videoId?: string, sessionId?: string) {
  const params = {
    ...(videoId ? { video_id: videoId } : {}),
    ...(sessionId ? { session_id: sessionId } : {})
  };
  const { data } = await api.delete(`/projects/${projectId}/objects/${objectId}`, { params });
  return data;
}


export interface ProjectSummary {
  project_id: string;
  name: string;
  owner_id: string;
  owner_username: string;
  updated_at: string;
  deleted_at?: string | null;
  data_status?: "available" | "missing";
  missing_reason?: string | null;
}

export async function renameProject(projectId: string, name: string) {
  const { data } = await api.patch(`/projects/${projectId}`, { name });
  return data as ProjectSummary;
}

export async function recycleProject(projectId: string) {
  await api.delete(`/projects/${projectId}`);
}

export async function restoreProject(projectId: string) {
  await api.post(`/projects/${projectId}/restore`);
}

export async function transferProject(projectId: string, ownerId: string) {
  await api.post(`/projects/${projectId}/transfer`, { owner_id: ownerId });
}


export async function permanentlyDeleteProject(projectId: string, confirmationName: string) {
  await api.delete(`/projects/${projectId}/permanent`, { data: { confirmation_name: confirmationName } });
}
