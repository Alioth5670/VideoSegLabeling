import { useProjectStore } from "../store/projectStore";
import { useAnnotationStore } from "../store/annotationStore";
import type { TrackedObject } from "../types/annotation";

interface RawVideo {
  video_id?: string; name?: string; relative_path?: string;
  fps?: number; width?: number; height?: number; frame_count?: number; duration?: number;
}
interface RawProject extends RawVideo {
  project_id: string; videos?: RawVideo[]; active_video_id?: string; paths?: Record<string, string>;
}
interface RawObject {
  object_id: number; track_id: number; category: string; color: TrackedObject["color"];
  visible: boolean; locked: boolean; created_frame: number;
}
interface ProjectPayload {
  project: RawProject;
  annotations?: { objects?: Record<string, RawObject>; annotated_frames?: number[]; frames?: Record<string, unknown> };
}

export function normalizeProject(data: RawProject) {
  const videos = (data.videos ?? []).map((video: RawVideo) => ({
    videoId: video.video_id,
    name: video.name ?? "video",
    relativePath: video.relative_path,
    fps: video.fps ?? 0,
    width: video.width ?? 0,
    height: video.height ?? 0,
    frameCount: video.frame_count ?? 0,
    duration: video.duration ?? 0
  }));
  return {
    projectId: data.project_id,
    name: data.name ?? "Untitled",
    videos,
    activeVideoId: data.active_video_id ?? videos[0]?.videoId,
    paths: data.paths ?? {},
    fps: data.fps ?? 0,
    width: data.width ?? 0,
    height: data.height ?? 0,
    frameCount: data.frame_count ?? 0,
    duration: data.duration ?? 0
  };
}


export function applyProjectPayload(data: ProjectPayload) {
  const store = useProjectStore.getState();
  store.setProject(normalizeProject(data.project));
  store.setObjects(Object.values(data.annotations?.objects ?? {}).map(obj => ({
    objectId: obj.object_id, trackId: obj.track_id, category: obj.category, color: obj.color,
    visible: obj.visible, locked: obj.locked, createdFrame: obj.created_frame
  })));
  useAnnotationStore.setState({ frameIndex: 0, playing: false, box: undefined, points: [], textPrompt: "",
    promptsByFrame: {}, promptQueue: [], selectedPrompt: null,
    annotatedFrames: data.annotations?.annotated_frames ?? Object.keys(data.annotations?.frames ?? {}).map(Number) });
}

export function clearWorkspace() {
  useProjectStore.setState({ project: undefined, objects: [], selectedObjectId: undefined });
  useAnnotationStore.setState({ frameIndex: 0, playing: false, annotatedFrames: [], box: undefined,
    points: [], textPrompt: "", promptsByFrame: {}, promptQueue: [], selectedPrompt: null });
}

export function defaultProjectName(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const suffix = Math.floor(Math.random() * 36 ** 4).toString(36).padStart(4, "0");
  return `project_${date}_${time}_${suffix}`;
}

export function isCurrentProject(projectId: string, videoId?: string): boolean {
  const current = useProjectStore.getState().project;
  return current?.projectId === projectId && current?.activeVideoId === videoId;
}
