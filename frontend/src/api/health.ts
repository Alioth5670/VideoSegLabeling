import { api } from "./client";

export async function getHealth() {
  const { data } = await api.get("/health");
  return data as {
    status: string;
    sam_backend: string;
    sam_device: string;
    sam_devices: SamDevice[];
    sam_fallback_error?: string | null;
  };
}

export interface SamDevice {
  id: string;
  index?: number;
  label: string;
  total_memory_mb?: number;
  available: boolean;
}
