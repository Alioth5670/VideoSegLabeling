import type { BoxPrompt, PointPrompt } from "./annotation";

export interface SegmentPayload {
  session_id?: string;
  frame_index: number;
  object_id?: number;
  category?: string;
  text?: string;
  box?: BoxPrompt;
  points?: PointPrompt[];
}
