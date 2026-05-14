export interface VideoInfo {
  videoId?: string;
  name: string;
  relativePath?: string;
  fps: number;
  width: number;
  height: number;
  frameCount: number;
  duration: number;
}

export interface ProjectInfo {
  projectId: string;
  name: string;
  videos: VideoInfo[];
  activeVideoId?: string;
  paths: Record<string, string>;
  fps: number;
  width: number;
  height: number;
  frameCount: number;
  duration: number;
}
