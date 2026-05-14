import { api } from "./client";

export async function exportProject(projectId: string, format: string) {
  const { data } = await api.post(`/projects/${projectId}/export`, { format });
  return data as { download_url: string };
}
