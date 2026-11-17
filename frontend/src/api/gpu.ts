import { api } from "./client";

export interface GPUSettings {
  sam_backend: "mock" | "sam3_video" | "sam3_multiplex_video";
  sam_gpu_pool: boolean;
  sam_gpu_devices: string;
  sam_gpu_min_free_mb: number;
  sam_gpu_max_used_mb: number;
  sam_gpu_max_utilization: number;
  sam_session_idle_seconds: number;
  sam_worker_timeout_seconds: number;
}
export interface GPUDevice {
  id: string; index: number; label: string; total_memory_mb: number; free_memory_mb: number;
  used_memory_mb: number; utilization: number; available: boolean; allowed: boolean; reserved: boolean;
}
export interface GPUSession {
  session_id: string; owner_id: string; username: string; project_id: string; project_name: string;
  gpu_id: string; device: string; backend: string; busy: boolean; ready: boolean; idle_seconds: number;
}
export interface GPUSnapshot {
  settings: GPUSettings; devices: GPUDevice[]; sessions: GPUSession[]; discovery_error: string | null;
}
export async function getGPUAdmin() {
  return (await api.get<GPUSnapshot>("/sam/admin")).data;
}
export async function saveGPUSettings(settings: GPUSettings) {
  return (await api.put<{ settings: GPUSettings }>("/sam/admin/settings", settings)).data.settings;
}
export async function releaseGPUSession(sessionId: string, force: boolean) {
  await api.post(`/sam/admin/sessions/${encodeURIComponent(sessionId)}/release`, { force });
}
