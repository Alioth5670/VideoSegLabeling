import { api } from "./client";
import type { FrameAnnotation, MaskPolygon } from "../types/annotation";

const MAX_CACHED_FRAME_ANNOTATIONS = 240;
const frameAnnotationCache = new Map<string, { annotation: FrameAnnotation; lastUsed: number }>();
const frameAnnotationRequests = new Map<string, Promise<FrameAnnotation>>();

export async function getAnnotations(projectId: string, videoId?: string) {
  const { data } = await api.get(`/projects/${projectId}/annotations`, { params: videoId ? { video_id: videoId } : undefined });
  return data;
}

export async function getFrameAnnotations(projectId: string, frameIndex: number, videoId?: string, options?: { force?: boolean }) {
  const key = frameAnnotationKey(projectId, frameIndex, videoId);
  const cached = frameAnnotationCache.get(key);
  if (cached && !options?.force) {
    cached.lastUsed = Date.now();
    return cached.annotation;
  }
  const existing = frameAnnotationRequests.get(key);
  if (existing && !options?.force) return existing;

  const request = fetchFrameAnnotations(projectId, frameIndex, videoId, key);
  frameAnnotationRequests.set(key, request);
  return request;
}

export function preloadFrameAnnotations(projectId: string, frameIndex: number, videoId?: string) {
  return getFrameAnnotations(projectId, frameIndex, videoId).catch(() => undefined);
}

export function invalidateFrameAnnotations(projectId: string, frameIndex: number, videoId?: string) {
  const key = frameAnnotationKey(projectId, frameIndex, videoId);
  frameAnnotationCache.delete(key);
  frameAnnotationRequests.delete(key);
}

async function fetchFrameAnnotations(projectId: string, frameIndex: number, videoId: string | undefined, key: string) {
  const { data } = await api.get(`/projects/${projectId}/annotations/${frameIndex}`, { params: videoId ? { video_id: videoId } : undefined });
  const annotation = normalizeFrameAnnotation(data);
  frameAnnotationCache.set(key, { annotation, lastUsed: Date.now() });
  frameAnnotationRequests.delete(key);
  trimFrameAnnotationCache();
  return annotation;
}

interface SaveAnnotationOptions {
  allowOverwrite?: boolean;
}

export async function savePolygonAnnotation(projectId: string, frameIndex: number, objectId: number | undefined, polygons: MaskPolygon[], videoId?: string, options?: SaveAnnotationOptions) {
  const { data } = await api.post(`/projects/${projectId}/annotations/polygon`, {
    frame_index: frameIndex,
    ...(objectId !== undefined ? { object_id: objectId } : {}),
    polygons,
    is_keyframe: true,
    allow_overwrite: Boolean(options?.allowOverwrite)
  }, { params: videoId ? { video_id: videoId } : undefined });
  invalidateFrameAnnotations(projectId, frameIndex, videoId);
  return data;
}

export async function saveBBoxAnnotation(projectId: string, frameIndex: number, objectId: number | undefined, bbox: [number, number, number, number], videoId?: string, options?: SaveAnnotationOptions) {
  const { data } = await api.post(`/projects/${projectId}/annotations/bbox`, {
    frame_index: frameIndex,
    ...(objectId !== undefined ? { object_id: objectId } : {}),
    bbox,
    is_keyframe: true,
    allow_overwrite: Boolean(options?.allowOverwrite)
  }, { params: videoId ? { video_id: videoId } : undefined });
  invalidateFrameAnnotations(projectId, frameIndex, videoId);
  return data;
}

export async function deleteFrameAnnotation(projectId: string, frameIndex: number, objectId: number, videoId?: string) {
  const { data } = await api.delete(`/projects/${projectId}/annotations/${frameIndex}/objects/${objectId}`, { params: videoId ? { video_id: videoId } : undefined });
  invalidateFrameAnnotations(projectId, frameIndex, videoId);
  return data as { deleted: boolean; object_deleted?: boolean; frame_index: number; object_id: number };
}

export async function updateFrameAnnotation(projectId: string, frameIndex: number, objectId: number, patch: { locked?: boolean }, videoId?: string) {
  const { data } = await api.patch(`/projects/${projectId}/annotations/${frameIndex}/objects/${objectId}`, patch, { params: videoId ? { video_id: videoId } : undefined });
  invalidateFrameAnnotations(projectId, frameIndex, videoId);
  return data;
}

export async function batchDeleteAnnotations(
  projectId: string,
  payload: {
    startFrame: number;
    endFrame: number;
    objectIds?: number[];
    deleteAnnotations: boolean;
    deletePrompts: boolean;
  },
  videoId?: string
) {
  const { data } = await api.post(`/projects/${projectId}/annotations/batch-delete`, {
    start_frame: payload.startFrame,
    end_frame: payload.endFrame,
    object_ids: payload.objectIds?.length ? payload.objectIds : undefined,
    delete_annotations: payload.deleteAnnotations,
    delete_prompts: payload.deletePrompts
  }, { params: videoId ? { video_id: videoId } : undefined });
  for (const frameIndex of data.affected_frames ?? []) {
    invalidateFrameAnnotations(projectId, Number(frameIndex), videoId);
  }
  return data as {
    deleted_annotations: number;
    deleted_prompts: number;
    deleted_object_ids: number[];
    affected_frames: number[];
  };
}

function normalizeFrameAnnotation(data: any): FrameAnnotation {
  const objects: FrameAnnotation["objects"] = {};
  for (const [objectKey, ann] of Object.entries<any>(data.objects ?? {})) {
    const objectId = Number(objectKey);
    objects[objectId] = {
      objectId: Number(ann.object_id ?? objectId),
      trackId: Number(ann.track_id ?? objectId),
      frameIndex: Number(ann.frame_index ?? data.frame_index ?? 0),
      maskUrl: ann.mask_url,
      polygons: ann.polygons ?? [],
      bbox: ann.bbox ?? [0, 0, 0, 0],
      area: Number(ann.area ?? 0),
      score: ann.score,
      source: ann.source ?? "manual",
      isKeyframe: Boolean(ann.is_keyframe ?? ann.isKeyframe),
      locked: Boolean(ann.locked)
    };
  }
  return { frameIndex: Number(data.frame_index ?? 0), objects };
}

function frameAnnotationKey(projectId: string, frameIndex: number, videoId?: string) {
  return `${projectId}:${videoId ?? ""}:${frameIndex}`;
}

function trimFrameAnnotationCache() {
  if (frameAnnotationCache.size <= MAX_CACHED_FRAME_ANNOTATIONS) return;
  const entries = [...frameAnnotationCache.entries()].sort((a, b) => a[1].lastUsed - b[1].lastUsed);
  for (const [key] of entries.slice(0, frameAnnotationCache.size - MAX_CACHED_FRAME_ANNOTATIONS)) {
    frameAnnotationCache.delete(key);
  }
}
