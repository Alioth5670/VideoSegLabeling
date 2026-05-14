import axios from "axios";
import type { SegmentPayload } from "../types/sam";
import { api } from "./client";

export async function startSession(projectId: string, videoId?: string) {
  const { data } = await api.post(`/projects/${projectId}/sam/session`, {}, { params: videoId ? { video_id: videoId } : undefined });
  return data as { session_id: string; backend: string; device: string; video_supported: boolean; multiplex_supported: boolean; fallback_error?: string | null };
}

export async function resetSession(projectId: string, sessionId: string, videoId?: string) {
  const { data } = await api.post(
    `/projects/${projectId}/sam/session/reset`,
    { session_id: sessionId },
    { params: videoId ? { video_id: videoId } : undefined }
  );
  return data as { ok: boolean; session_id: string };
}

export async function switchBackend(backend: string) {
  const { data } = await api.post("/sam/backend", { backend });
  return data as BackendSwitchResult;
}

export async function switchDevice(device: string) {
  const { data } = await api.post("/sam/device", { device });
  return data as DeviceSwitchResult;
}

export async function switchProjectBackend(projectId: string, backend: string) {
  try {
    return await switchBackend(backend);
  } catch (error) {
    if (!axios.isAxiosError(error) || error.response?.status !== 404) {
      throw error;
    }
    const { data } = await api.post(`/projects/${projectId}/sam/backend`, { backend });
    return data as BackendSwitchResult;
  }
}

export async function segmentFrame(projectId: string, payload: SegmentPayload, videoId?: string) {
  const { data } = await api.post(`/projects/${projectId}/sam/segment`, payload, { params: videoId ? { video_id: videoId } : undefined });
  return data;
}

export async function propagate(
  projectId: string,
  payload: Record<string, unknown>,
  videoId?: string,
  options?: { onFrame?: (frame: PropagatedFrame) => void; signal?: AbortSignal }
) {
  const params = videoId ? `?video_id=${encodeURIComponent(videoId)}` : "";
  const response = await fetch(`/api/projects/${projectId}/sam/propagate${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options?.signal
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || response.statusText);
  }
  if (!response.body) {
    return response.json();
  }

  const frames: PropagatedFrame[] = [];
  let backend = "";
  let buffer = "";
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as PropagateEvent;
      if (event.type === "frame") {
        frames.push(event.frame);
        options?.onFrame?.(event.frame);
      } else if (event.type === "done") {
        backend = event.backend;
        frames.splice(0, frames.length, ...event.frames);
      } else if (event.type === "cancelled") {
        backend = event.backend;
        frames.splice(0, frames.length, ...event.frames);
        return { backend, frames, cancelled: true };
      } else if (event.type === "error") {
        throw new Error(event.detail);
      }
    }
  }
  if (buffer.trim()) {
    const event = JSON.parse(buffer) as PropagateEvent;
    if (event.type === "frame") {
      frames.push(event.frame);
      options?.onFrame?.(event.frame);
    } else if (event.type === "done") {
      backend = event.backend;
      frames.splice(0, frames.length, ...event.frames);
    } else if (event.type === "cancelled") {
      backend = event.backend;
      frames.splice(0, frames.length, ...event.frames);
      return { backend, frames, cancelled: true };
    } else if (event.type === "error") {
      throw new Error(event.detail);
    }
  }
  return { backend, frames, cancelled: false };
}

export async function cancelPropagation(projectId: string, sessionId: string, videoId?: string) {
  const { data } = await api.post(
    `/projects/${projectId}/sam/propagate/cancel`,
    { session_id: sessionId },
    { params: videoId ? { video_id: videoId } : undefined }
  );
  return data as { cancelled: boolean };
}

export interface PropagatedFrame {
  frame_index: number;
  objects: Record<string, unknown>;
}

type PropagateEvent =
  | { type: "frame"; frame: PropagatedFrame }
  | { type: "done"; backend: string; frames: PropagatedFrame[] }
  | { type: "cancelled"; backend: string; frames: PropagatedFrame[] }
  | { type: "error"; detail: string };

interface BackendSwitchResult {
  backend: string;
  video_supported: boolean;
  multiplex_supported: boolean;
  fallback_error?: string | null;
}

interface DeviceSwitchResult {
  device: string;
  devices: Array<{ id: string; label: string; available: boolean; total_memory_mb?: number }>;
  backend: string;
  fallback_error?: string | null;
}
