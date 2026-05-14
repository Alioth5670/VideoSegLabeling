import { create } from "zustand";
import type { ProjectInfo } from "../types/project";
import type { TrackedObject } from "../types/annotation";

interface ProjectState {
  project?: ProjectInfo;
  objects: TrackedObject[];
  selectedObjectId?: number;
  setProject: (project: ProjectInfo) => void;
  setObjects: (objects: TrackedObject[]) => void;
  setSelectedObjectId: (id?: number) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  objects: [],
  setProject: (project) => set({ project }),
  setObjects: (objects) => set((state) => ({
    objects,
    selectedObjectId: objects.some((obj) => obj.objectId === state.selectedObjectId) ? state.selectedObjectId : objects[0]?.objectId
  })),
  setSelectedObjectId: (id) => set({ selectedObjectId: id })
}));
