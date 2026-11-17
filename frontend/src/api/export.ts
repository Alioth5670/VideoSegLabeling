import { api } from "./client";

export interface ExportJob {
  job_id: string;
  project_id: string;
  video_id?: string | null;
  format: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  stage: string;
  download_url?: string | null;
  error?: string | null;
}

export async function exportProject(projectId: string, format: string, videoId?: string) {
  const { data } = await api.post<ExportJob>(`/projects/${projectId}/export`, { format, video_id: videoId });
  return data;
}

export async function getExportJob(projectId: string, jobId: string, signal?: AbortSignal) {
  const { data } = await api.get<ExportJob>(`/projects/${projectId}/export/${jobId}`, { signal });
  return data;
}
