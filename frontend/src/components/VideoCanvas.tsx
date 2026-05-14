import { RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import axios from "axios";
import { useEffect, useMemo, useRef, useState } from "react";
import { getFrameAnnotations, saveBBoxAnnotation, savePolygonAnnotation } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";
import type { TrackedObject } from "../types/annotation";
import { displayBoxToImageBox, displayToImageCoord } from "../utils/coordinate";
import MaskLayer from "./MaskLayer";

const MANUAL_CLOSE_RADIUS = 12;
type BoxDragHandle = "move" | "top-left" | "top-right" | "bottom-left" | "bottom-right";
interface BoxDragState {
  handle: BoxDragHandle;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startBox: [number, number, number, number];
}

export default function VideoCanvas() {
  const shellRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [draftStart, setDraftStart] = useState<{ x: number; y: number }>();
  const [pan, setPan] = useState<{ pointerId: number; x: number; y: number }>();
  const [dragPointIndex, setDragPointIndex] = useState<number>();
  const [boxDrag, setBoxDrag] = useState<BoxDragState>();
  const [altDown, setAltDown] = useState(false);
  const [manualPolygon, setManualPolygon] = useState<Array<[number, number]>>([]);
  const { project, objects, selectedObjectId, setObjects, setSelectedObjectId } = useProjectStore();
  const { frameIndex, tool, box, points, promptQueue, selectedPrompt, zoom, setBox, addPoint, updatePoint, selectPrompt, setZoom, setManualMessage } = useAnnotationStore();
  const selectedObject = objects.find((object) => object.objectId === selectedObjectId);
  const promptColor = selectedObject ? `rgb(${selectedObject.color.join(",")})` : undefined;
  const objectColor = useMemo(() => new Map(objects.map((object) => [object.objectId, `rgb(${object.color.join(",")})`])), [objects]);
  const frameQueue = promptQueue.filter((item) => item.frameIndex === frameIndex);

  const imageUrl = useMemo(() => {
    if (!project || project.frameCount === 0) return "";
    const params = project.activeVideoId ? `?video_id=${project.activeVideoId}` : "";
    return `/api/projects/${project.projectId}/frames/${frameIndex}${params}`;
  }, [project, frameIndex]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Alt") setAltDown(true);
    }
    function onKeyUp(event: KeyboardEvent) {
      if (event.key === "Alt") setAltDown(false);
    }
    function onBlur() {
      setAltDown(false);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;
    function onNativeWheel(event: WheelEvent) {
      if (!event.altKey && !altDown) return;
      event.preventDefault();
      event.stopPropagation();
      const state = useAnnotationStore.getState();
      const step = event.deltaY > 0 ? -0.15 : 0.15;
      state.setZoom(state.zoom + step);
    }
    shell.addEventListener("wheel", onNativeWheel, { passive: false, capture: true });
    return () => shell.removeEventListener("wheel", onNativeWheel, { capture: true });
  }, [altDown]);

  useEffect(() => {
    if (tool !== "manual-polygon") {
      setManualPolygon([]);
    }
    setManualMessage("");
  }, [tool]);

  useEffect(() => {
    if (!boxDrag) return;
    const activePointerId = boxDrag.pointerId;
    function onPointerMove(event: globalThis.PointerEvent) {
      moveBox(event);
    }
    function onPointerUp(event: globalThis.PointerEvent) {
      if (event.pointerId === activePointerId) setBoxDrag(undefined);
    }
    window.addEventListener("pointermove", onPointerMove, { capture: true });
    window.addEventListener("pointerup", onPointerUp, { capture: true });
    window.addEventListener("pointercancel", onPointerUp, { capture: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove, { capture: true });
      window.removeEventListener("pointerup", onPointerUp, { capture: true });
      window.removeEventListener("pointercancel", onPointerUp, { capture: true });
    };
  }, [boxDrag, project?.width, project?.height, zoom]);

  useEffect(() => {
    function onFocusPrompt(event: Event) {
      const detail = (event as CustomEvent<{ x: number; y: number }>).detail;
      if (!detail || !Number.isFinite(detail.x) || !Number.isFinite(detail.y)) return;
      window.requestAnimationFrame(() => scrollImagePointIntoView(detail.x, detail.y));
    }
    window.addEventListener("focus-video-prompt", onFocusPrompt);
    return () => window.removeEventListener("focus-video-prompt", onFocusPrompt);
  }, [project?.width, project?.height, zoom]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) return;
      if (tool !== "manual-polygon" && tool !== "manual-bbox") return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        if (tool === "manual-polygon" && manualPolygon.length > 0) {
          event.preventDefault();
          undoManualPolygonPoint();
        }
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        clearManualDraft();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tool, manualPolygon.length]);

  function localPoint(event: React.PointerEvent) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0, width: 1, height: 1 };
    return { x: event.clientX - rect.left, y: event.clientY - rect.top, width: rect.width, height: rect.height };
  }

  function scrollImagePointIntoView(imageX: number, imageY: number) {
    const shell = shellRef.current;
    const stage = stageRef.current;
    if (!shell || !stage || !project) return;
    const targetX = stage.offsetLeft + (imageX / project.width) * stage.offsetWidth;
    const targetY = stage.offsetTop + (imageY / project.height) * stage.offsetHeight;
    shell.scrollTo({
      left: Math.max(0, targetX - shell.clientWidth / 2),
      top: Math.max(0, targetY - shell.clientHeight / 2),
      behavior: "smooth"
    });
  }

  function clientDeltaToImageDelta(clientDx: number, clientDy: number) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || !project) return { dx: 0, dy: 0 };
    return {
      dx: (clientDx / rect.width) * project.width,
      dy: (clientDy / rect.height) * project.height
    };
  }

  function moveBox(event: globalThis.PointerEvent) {
    if (!boxDrag || !project) return;
    event.preventDefault();
    event.stopPropagation();
    const { dx, dy } = clientDeltaToImageDelta(event.clientX - boxDrag.startClientX, event.clientY - boxDrag.startClientY);
    setBox(nextBoxFromDrag(boxDrag.startBox, boxDrag.handle, dx, dy, project.width, project.height));
  }

  async function pointerDown(event: React.PointerEvent) {
    if (!project) return;
    if (event.altKey && event.button === 0) {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setPan({ pointerId: event.pointerId, x: event.clientX, y: event.clientY });
      setDraftStart(undefined);
      return;
    }
    const p = localPoint(event);
    if (tool === "box") {
      setDraftStart({ x: p.x, y: p.y });
      setBox(undefined);
    } else if (tool === "point-positive" || tool === "point-negative") {
      const existingPointIndex = findPointAtDisplayPosition(p.x, p.y, p.width, p.height);
      if (existingPointIndex !== undefined) {
        selectPrompt({ type: "point", index: existingPointIndex });
        return;
      }
      const image = displayToImageCoord(p.x, p.y, p.width, p.height, project.width, project.height);
      addPoint({ x: image.x, y: image.y, label: tool === "point-positive" ? 1 : 0 });
    } else if (tool === "manual-bbox") {
      setDraftStart({ x: p.x, y: p.y });
      setBox(undefined);
    } else if (tool === "manual-polygon") {
      if (manualPolygon.length >= 3 && isClosingManualPolygon(p.x, p.y, p.width, p.height)) {
        saveManualPolygon(manualPolygon);
        return;
      }
      const image = displayToImageCoord(p.x, p.y, p.width, p.height, project.width, project.height);
      setManualPolygon((current) => [...current, [image.x, image.y]]);
      setManualMessage("");
    }
  }

  function isClosingManualPolygon(x: number, y: number, displayWidth: number, displayHeight: number) {
    if (!project || manualPolygon.length < 3) return false;
    const [firstX, firstY] = manualPolygon[0];
    const displayX = (firstX / project.width) * displayWidth;
    const displayY = (firstY / project.height) * displayHeight;
    return Math.hypot(displayX - x, displayY - y) <= MANUAL_CLOSE_RADIUS;
  }

  function findPointAtDisplayPosition(x: number, y: number, displayWidth: number, displayHeight: number): number | undefined {
    if (!project) return undefined;
    const hitRadius = 12;
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const point = points[index];
      const px = (point.x / project.width) * displayWidth;
      const py = (point.y / project.height) * displayHeight;
      if (Math.hypot(px - x, py - y) <= hitRadius) {
        return index;
      }
    }
    return undefined;
  }

  function pointerMove(event: React.PointerEvent) {
    if (boxDrag) return;
    if (pan) {
      const dx = event.clientX - pan.x;
      const dy = event.clientY - pan.y;
      if (shellRef.current) {
        shellRef.current.scrollLeft -= dx;
        shellRef.current.scrollTop -= dy;
      }
      setPan({ pointerId: pan.pointerId, x: event.clientX, y: event.clientY });
      return;
    }
    if (dragPointIndex !== undefined && project) {
      event.stopPropagation();
      const p = localPoint(event);
      const image = displayToImageCoord(p.x, p.y, p.width, p.height, project.width, project.height);
      const previous = useAnnotationStore.getState().points[dragPointIndex];
      if (previous) updatePoint(dragPointIndex, { ...image, label: previous.label });
      return;
    }
    if (!project || !draftStart || (tool !== "box" && tool !== "manual-bbox")) return;
    const p = localPoint(event);
    setBox(displayBoxToImageBox([draftStart.x, draftStart.y, p.x, p.y], p.width, p.height, project.width, project.height));
  }

  function pointerUp(event: React.PointerEvent) {
    if (pan?.pointerId === event.pointerId) {
      setPan(undefined);
    }
    const shouldSaveManualBBox = tool === "manual-bbox" && draftStart && project;
    setDragPointIndex(undefined);
    setBoxDrag(undefined);
    setDraftStart(undefined);
    if (shouldSaveManualBBox) {
      saveManualBBox();
    }
  }

  function startPointDrag(event: React.PointerEvent, index: number) {
    if (event.altKey) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragPointIndex(index);
    selectPrompt({ type: "point", index });
    focusPromptRow({ type: "point", index });
  }

  function startBoxDrag(event: React.PointerEvent, handle: BoxDragHandle) {
    if (event.altKey || !box) return;
    event.stopPropagation();
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    selectPrompt({ type: "box" });
    focusPromptRow({ type: "box" });
    setDraftStart(undefined);
    setBoxDrag({
      handle,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startBox: box
    });
  }

  async function saveManualBBox() {
    if (!project || !box) return;
    const [x1, y1, x2, y2] = box;
    if (Math.abs(x2 - x1) < 2 || Math.abs(y2 - y1) < 2) {
      setBox(undefined);
      return;
    }
    setManualMessage("Saving manual bbox...");
    try {
      const saved = await saveBBoxAnnotation(project.projectId, frameIndex, selectedObjectId, box, project.activeVideoId, { allowOverwrite: selectedObjectId !== undefined });
      applyManualObject(saved.object);
      useAnnotationStore.getState().refreshOverlay();
      setBox(undefined);
      setManualMessage("");
    } catch (error) {
      setManualMessage(errorMessage(error, "Failed to save manual bbox."));
    }
  }

  async function saveManualPolygon(polygon = manualPolygon) {
    if (!project || polygon.length < 3) return;
    setManualMessage("Saving manual polygon...");
    try {
      const existing = selectedObjectId !== undefined
        ? await getFrameAnnotations(project.projectId, frameIndex, project.activeVideoId, { force: true }).catch(() => undefined)
        : undefined;
      const existingObject = selectedObjectId !== undefined ? existing?.objects[selectedObjectId] : undefined;
      const objectId = selectedObjectId;
      const polygons = existingObject ? [...(existingObject.polygons ?? []), polygon] : [polygon];
      const saved = await savePolygonAnnotation(project.projectId, frameIndex, objectId, polygons, project.activeVideoId, { allowOverwrite: Boolean(objectId) });
      applyManualObject(saved.object);
      useAnnotationStore.getState().refreshOverlay();
      setManualPolygon([]);
      setManualMessage("");
    } catch (error) {
      setManualMessage(errorMessage(error, "Failed to save manual polygon."));
    }
  }

  function undoManualPolygonPoint() {
    setManualPolygon((current) => current.slice(0, -1));
    setManualMessage("");
  }

  function clearManualDraft() {
    setDraftStart(undefined);
    setManualPolygon([]);
    setManualMessage("");
    if (tool === "manual-bbox") {
      setBox(undefined);
    }
  }

  function applyManualObject(rawObject: any) {
    if (!rawObject) return;
    const nextObject = normalizeObject(rawObject);
    const nextObjects = objects.some((object) => object.objectId === nextObject.objectId)
      ? objects.map((object) => object.objectId === nextObject.objectId ? nextObject : object)
      : [...objects, nextObject];
    setObjects(nextObjects);
    setSelectedObjectId(nextObject.objectId);
  }

  if (!project || project.frameCount === 0) {
    return <main className="canvas-empty">Create a project and upload a video.</main>;
  }

  return (
    <main ref={shellRef} className="canvas-shell">
      <div className="zoom-controls">
        <button title="Zoom out" onClick={() => setZoom(zoom - 0.25)}><ZoomOut size={17} /></button>
        <input
          aria-label="Zoom"
          min="0.5"
          max="4"
          step="0.25"
          type="range"
          value={zoom}
          onChange={(event) => setZoom(Number(event.target.value))}
        />
        <button title="Zoom in" onClick={() => setZoom(zoom + 0.25)}><ZoomIn size={17} /></button>
        <button title="Reset zoom" onClick={() => setZoom(1)}><RotateCcw size={17} /></button>
        <span>{Math.round(zoom * 100)}%</span>
      </div>
      <div
        ref={stageRef}
        className="canvas-stage"
        style={{
          width: project.width * zoom,
          height: project.height * zoom
        }}
      >
        <div
          ref={containerRef}
          className={`video-canvas ${pan ? "panning" : ""}`}
          style={{
            aspectRatio: `${project.width} / ${project.height}`,
            width: project.width,
            transform: `scale(${zoom})`
          }}
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerCancel={pointerUp}
        >
          <img draggable={false} src={imageUrl} />
          <MaskLayer containerRef={containerRef} />
        {frameQueue.map((item) => {
          const color = item.objectId ? objectColor.get(item.objectId) : undefined;
          return (
            <div className="queued-prompt-layer" key={item.id}>
              {item.box && <BoxOverlay box={item.box} selected={false} color={color} onSelect={() => undefined} />}
              {item.points.map((point, index) => (
                <span
                  key={`${item.id}-${index}`}
                  className={`point queued ${point.label === 1 ? "positive" : "negative"}`}
                  style={{
                    left: `${(point.x / project.width) * 100}%`,
                    top: `${(point.y / project.height) * 100}%`,
                    borderColor: color,
                    transform: `scale(${1 / zoom})`
                  }}
                >
                  {point.label === 1 ? "+" : "-"}
                </span>
              ))}
            </div>
          );
        })}
        {box && <BoxOverlay box={box} selected={selectedPrompt?.type === "box"} color={promptColor} onSelect={() => {
          selectPrompt({ type: "box" });
          focusPromptRow({ type: "box" });
        }} onDragStart={startBoxDrag} />}
        {points.map((point, index) => (
          <span
            key={index}
            className={`point ${point.label === 1 ? "positive" : "negative"} ${selectedPrompt?.type === "point" && selectedPrompt.index === index ? "selected" : ""}`}
            style={{
              left: `${(point.x / project.width) * 100}%`,
              top: `${(point.y / project.height) * 100}%`,
              borderColor: promptColor,
              transform: `scale(${1 / zoom})`
            }}
            onPointerDown={(event) => startPointDrag(event, index)}
          >
            {point.label === 1 ? "+" : "-"}
          </span>
        ))}
        {manualPolygon.length > 0 && project && (
          <svg className="manual-draft-layer" viewBox={`0 0 ${project.width} ${project.height}`} preserveAspectRatio="none">
            {manualPolygon.length > 1 && <polyline points={manualPolygon.map((point) => point.join(",")).join(" ")} />}
            {manualPolygon.length > 2 && <polygon points={manualPolygon.map((point) => point.join(",")).join(" ")} />}
            {manualPolygon.map((point, index) => (
              <circle
                key={`${point[0]}-${point[1]}-${index}`}
                className={index === 0 && manualPolygon.length >= 3 ? "close-point" : ""}
                cx={point[0]}
                cy={point[1]}
                r={(index === 0 && manualPolygon.length >= 3 ? 6 : 4) / zoom}
              />
            ))}
          </svg>
        )}
        </div>
      </div>
    </main>
  );
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
}

function errorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === "string" ? detail : error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

function normalizeObject(obj: any): TrackedObject {
  return {
    objectId: obj.object_id,
    trackId: obj.track_id,
    category: obj.category,
    color: obj.color,
    visible: obj.visible,
    locked: obj.locked,
    createdFrame: obj.created_frame
  };
}

function focusPromptRow(detail: { type: "box" } | { type: "point"; index: number }) {
  window.dispatchEvent(new CustomEvent("focus-prompt-row", { detail }));
}

function nextBoxFromDrag(box: [number, number, number, number], handle: BoxDragHandle, dx: number, dy: number, imageWidth: number, imageHeight: number): [number, number, number, number] {
  let [x1, y1, x2, y2] = box;
  if (handle === "move") {
    const width = x2 - x1;
    const height = y2 - y1;
    const nextX1 = clamp(x1 + dx, 0, imageWidth - width);
    const nextY1 = clamp(y1 + dy, 0, imageHeight - height);
    return [nextX1, nextY1, nextX1 + width, nextY1 + height];
  }
  if (handle.includes("left")) x1 = clamp(x1 + dx, 0, x2 - 1);
  if (handle.includes("right")) x2 = clamp(x2 + dx, x1 + 1, imageWidth);
  if (handle.includes("top")) y1 = clamp(y1 + dy, 0, y2 - 1);
  if (handle.includes("bottom")) y2 = clamp(y2 + dy, y1 + 1, imageHeight);
  return [x1, y1, x2, y2];
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function BoxOverlay({ box, selected, color, onSelect, onDragStart }: {
  box: [number, number, number, number];
  selected: boolean;
  color?: string;
  onSelect: () => void;
  onDragStart?: (event: React.PointerEvent, handle: BoxDragHandle) => void;
}) {
  const project = useProjectStore((s) => s.project);
  if (!project) return null;
  const left = (box[0] / project.width) * 100;
  const top = (box[1] / project.height) * 100;
  const width = ((box[2] - box[0]) / project.width) * 100;
  const height = ((box[3] - box[1]) / project.height) * 100;
  return (
    <button
      className={`box-overlay ${selected ? "selected" : ""}`}
      style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`, color }}
      title="Select box prompt"
      onPointerDown={(event) => {
        if (!event.altKey) event.stopPropagation();
        onDragStart?.(event, "move");
      }}
      onClick={(event) => {
        if (event.altKey) return;
        event.stopPropagation();
        onSelect();
      }}
    >
      <span className="box-handle top-left" onPointerDown={(event) => onDragStart?.(event, "top-left")} />
      <span className="box-handle top-right" onPointerDown={(event) => onDragStart?.(event, "top-right")} />
      <span className="box-handle bottom-left" onPointerDown={(event) => onDragStart?.(event, "bottom-left")} />
      <span className="box-handle bottom-right" onPointerDown={(event) => onDragStart?.(event, "bottom-right")} />
    </button>
  );
}
