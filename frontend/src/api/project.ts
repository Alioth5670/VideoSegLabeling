import { api } from "./client";

export async function createProject(name: string, projectDir?: string) {
  const { data } = await api.post("/projects", { name, project_dir: projectDir || undefined });
  return data as { project_id: string; name: string };
}

export async function getProject(projectId: string, videoId?: string) {
  const { data } = await api.get(`/projects/${projectId}`, { params: videoId ? { video_id: videoId } : undefined });
  return data;
}

export async function listProjects() {
  const { data } = await api.get("/projects");
  return data as { projects: any[] };
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
  const { data } = await api.post(`/projects/${projectId}/videos/${videoId}/activate`, {});
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
