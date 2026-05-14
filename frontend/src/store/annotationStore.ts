import { create } from "zustand";
import type { BoxPrompt, PointPrompt } from "../types/annotation";

export type ToolMode = "view" | "box" | "point-positive" | "point-negative" | "manual-bbox" | "manual-polygon";
export type SelectedPrompt = { type: "box" } | { type: "point"; index: number } | null;
type FramePromptState = { box?: BoxPrompt; points: PointPrompt[]; textPrompt: string };
export type PromptQueueItem = FramePromptState & {
  id: string;
  frameIndex: number;
  objectId?: number;
  category?: string;
};

interface AnnotationState {
  frameIndex: number;
  sessionId?: string;
  sessionObjectIds: number[];
  backend: string;
  samDevice: string;
  tool: ToolMode;
  box?: BoxPrompt;
  points: PointPrompt[];
  textPrompt: string;
  promptsByFrame: Record<number, FramePromptState>;
  promptQueue: PromptQueueItem[];
  overlayVersion: number;
  annotatedFrames: number[];
  selectedPrompt: SelectedPrompt;
  zoom: number;
  playing: boolean;
  scrubbing: boolean;
  manualMessage: string;
  setFrameIndex: (frameIndex: number) => void;
  setSession: (sessionId: string, backend: string) => void;
  clearSession: () => void;
  resetSessionObjects: () => void;
  addSessionObjectIds: (ids: number[]) => void;
  removeSessionObjectId: (id: number) => void;
  setBackend: (backend: string) => void;
  setSamDevice: (samDevice: string) => void;
  setTool: (tool: ToolMode) => void;
  setBox: (box?: BoxPrompt) => void;
  clearBox: () => void;
  addPoint: (point: PointPrompt) => void;
  updatePoint: (index: number, point: PointPrompt) => void;
  removePoint: (index: number) => void;
  selectPrompt: (prompt: SelectedPrompt) => void;
  setZoom: (zoom: number) => void;
  setPlaying: (playing: boolean) => void;
  setScrubbing: (scrubbing: boolean) => void;
  togglePlaying: () => void;
  setManualMessage: (message: string) => void;
  enqueueCurrentPrompt: (objectId?: number, category?: string) => void;
  removeQueuedPrompt: (id: string) => void;
  clearPromptQueueForFrame: (frameIndex?: number) => void;
  clearPrompts: () => void;
  setTextPrompt: (textPrompt: string) => void;
  refreshOverlay: () => void;
  setAnnotatedFrames: (frames: number[]) => void;
  addAnnotatedFrame: (frameIndex: number) => void;
}

export const useAnnotationStore = create<AnnotationState>((set) => ({
  frameIndex: 0,
  sessionObjectIds: [],
  backend: "mock",
  samDevice: "cuda:0",
  tool: "view",
  points: [],
  textPrompt: "",
  promptsByFrame: {},
  promptQueue: [],
  overlayVersion: 0,
  annotatedFrames: [],
  selectedPrompt: null,
  zoom: 1,
  playing: false,
  scrubbing: false,
  manualMessage: "",
  setFrameIndex: (frameIndex) => set((state) => {
    const prompt = state.promptsByFrame[frameIndex] ?? { points: [], textPrompt: "" };
    return {
      frameIndex,
      box: prompt.box,
      points: prompt.points,
      textPrompt: prompt.textPrompt,
      selectedPrompt: null
    };
  }),
  setSession: (sessionId, backend) => set({ sessionId, backend, sessionObjectIds: [] }),
  clearSession: () => set({ sessionId: undefined, sessionObjectIds: [] }),
  resetSessionObjects: () => set({ sessionObjectIds: [] }),
  addSessionObjectIds: (ids) => set((state) => ({
    sessionObjectIds: [...new Set([...state.sessionObjectIds, ...ids])]
  })),
  removeSessionObjectId: (id) => set((state) => ({
    sessionObjectIds: state.sessionObjectIds.filter((objectId) => objectId !== id)
  })),
  setBackend: (backend) => set({ backend }),
  setSamDevice: (samDevice) => set({ samDevice }),
  setTool: (tool) => set({ tool }),
  setBox: (box) => set((state) => ({
    box,
    selectedPrompt: box ? { type: "box" } : null,
    promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { box, points: state.points, textPrompt: state.textPrompt })
  })),
  clearBox: () => set((state) => ({
    box: undefined,
    selectedPrompt: state.selectedPrompt?.type === "box" ? null : state.selectedPrompt,
    promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { points: state.points, textPrompt: state.textPrompt })
  })),
  addPoint: (point) => set((state) => {
    const points = [...state.points, point];
    return {
      points,
      selectedPrompt: { type: "point", index: state.points.length },
      promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { box: state.box, points, textPrompt: state.textPrompt })
    };
  }),
  updatePoint: (index, point) => set((state) => {
    if (!state.points[index]) return state;
    const points = state.points.map((item, itemIndex) => itemIndex === index ? point : item);
    return {
      points,
      selectedPrompt: { type: "point", index },
      promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { box: state.box, points, textPrompt: state.textPrompt })
    };
  }),
  removePoint: (index) => set((state) => {
    const points = state.points.filter((_, i) => i !== index);
    return {
      points,
      selectedPrompt: state.selectedPrompt?.type === "point" && state.selectedPrompt.index === index ? null : state.selectedPrompt,
      promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { box: state.box, points, textPrompt: state.textPrompt })
    };
  }),
  selectPrompt: (prompt) => set({ selectedPrompt: prompt }),
  setZoom: (zoom) => set({ zoom: Math.min(4, Math.max(0.5, zoom)) }),
  setPlaying: (playing) => set({ playing }),
  setScrubbing: (scrubbing) => set({ scrubbing }),
  togglePlaying: () => set((state) => ({ playing: !state.playing })),
  setManualMessage: (manualMessage) => set({ manualMessage }),
  enqueueCurrentPrompt: (objectId, category) => set((state) => {
    if (!state.box && state.points.length === 0 && !state.textPrompt.trim()) return state;
    const promptsByFrame = { ...state.promptsByFrame };
    delete promptsByFrame[state.frameIndex];
    return {
      box: undefined,
      points: [],
      textPrompt: "",
      selectedPrompt: null,
      promptsByFrame,
      promptQueue: [
        ...state.promptQueue,
        {
          id: `${state.frameIndex}-${objectId ?? "auto"}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          frameIndex: state.frameIndex,
          objectId,
          category,
          box: state.box,
          points: state.points,
          textPrompt: state.textPrompt
        }
      ]
    };
  }),
  removeQueuedPrompt: (id) => set((state) => ({ promptQueue: state.promptQueue.filter((item) => item.id !== id) })),
  clearPromptQueueForFrame: (frameIndex) => set((state) => ({
    promptQueue: state.promptQueue.filter((item) => item.frameIndex !== (frameIndex ?? state.frameIndex))
  })),
  clearPrompts: () => set((state) => {
    const promptsByFrame = { ...state.promptsByFrame };
    delete promptsByFrame[state.frameIndex];
    return { box: undefined, points: [], textPrompt: "", selectedPrompt: null, promptsByFrame };
  }),
  setTextPrompt: (textPrompt) => set((state) => ({
    textPrompt,
    promptsByFrame: setFramePrompt(state.promptsByFrame, state.frameIndex, { box: state.box, points: state.points, textPrompt })
  })),
  refreshOverlay: () => set((state) => ({ overlayVersion: state.overlayVersion + 1 })),
  setAnnotatedFrames: (frames) => set({ annotatedFrames: frames }),
  addAnnotatedFrame: (frameIndex) => set((state) => ({
    annotatedFrames: state.annotatedFrames.includes(frameIndex)
      ? state.annotatedFrames
      : [...state.annotatedFrames, frameIndex].sort((left, right) => left - right)
  }))
}));

function setFramePrompt(promptsByFrame: Record<number, FramePromptState>, frameIndex: number, prompt: FramePromptState) {
  if (!prompt.box && prompt.points.length === 0 && !prompt.textPrompt) {
    const next = { ...promptsByFrame };
    delete next[frameIndex];
    return next;
  }
  return {
    ...promptsByFrame,
    [frameIndex]: {
      box: prompt.box,
      points: prompt.points,
      textPrompt: prompt.textPrompt
    }
  };
}
