import AnnotationPanel from "./components/AnnotationPanel";
import { useEffect } from "react";
import ObjectPanel from "./components/ObjectPanel";
import ProjectPanel from "./components/ProjectPanel";
import PromptPanel from "./components/PromptPanel";
import Timeline from "./components/Timeline";
import ToolPanel from "./components/ToolPanel";
import TopControls from "./components/TopControls";
import VideoCanvas from "./components/VideoCanvas";
import { useAnnotationStore } from "./store/annotationStore";
import { useProjectStore } from "./store/projectStore";

export default function App() {
  const project = useProjectStore((state) => state.project);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      const state = useAnnotationStore.getState();
      if (key === "a") {
        event.preventDefault();
        state.setFrameIndex(Math.max(0, state.frameIndex - 1));
      } else if (key === "d") {
        event.preventDefault();
        state.setFrameIndex(Math.min((project?.frameCount ?? 1) - 1, state.frameIndex + 1));
      } else if (event.code === "Space") {
        event.preventDefault();
        state.togglePlaying();
      } else if (key === "q") {
        event.preventDefault();
        state.setTool("box");
      } else if (key === "w") {
        event.preventDefault();
        state.setTool("point-positive");
      } else if (key === "e") {
        event.preventDefault();
        state.setTool("point-negative");
      } else if (key === "v") {
        event.preventDefault();
        state.setTool("view");
      } else if (key === "r") {
        event.preventDefault();
        state.setTool("manual-bbox");
      } else if (key === "p") {
        event.preventDefault();
        state.setTool("manual-polygon");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [project?.frameCount]);

  return (
    <div className="app-shell">
      <TopControls />
      <aside className="sidebar left">
        <ProjectPanel />
        <ObjectPanel />
      </aside>
      <VideoCanvas />
      <aside className="sidebar right">
        <AnnotationPanel />
        <ToolPanel />
        <PromptPanel />
      </aside>
      <Timeline />
    </div>
  );
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
}
