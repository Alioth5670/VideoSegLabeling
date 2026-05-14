export interface TrackedObject {
  objectId: number;
  trackId: number;
  category: string;
  color: [number, number, number];
  visible: boolean;
  locked: boolean;
  createdFrame: number;
}

export interface PointPrompt {
  x: number;
  y: number;
  label: 0 | 1;
}

export type BoxPrompt = [number, number, number, number];
export type PolygonPoint = [number, number];
export type MaskPolygon = PolygonPoint[];

export interface FrameObjectAnnotation {
  objectId: number;
  trackId: number;
  frameIndex: number;
  maskUrl?: string;
  polygons?: MaskPolygon[];
  bbox: BoxPrompt;
  area: number;
  score?: number;
  source: "sam3" | "sam3_video" | "sam3_multiplex" | "manual" | "mock";
  isKeyframe: boolean;
  locked: boolean;
}

export interface FrameAnnotation {
  frameIndex: number;
  objects: Record<number, FrameObjectAnnotation>;
}
