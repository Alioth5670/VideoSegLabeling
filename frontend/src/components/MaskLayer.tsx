import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, RefObject } from "react";
import { getFrameAnnotations, savePolygonAnnotation } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";
import type { FrameAnnotation, MaskPolygon } from "../types/annotation";
import { rgb } from "../utils/color";

interface DragState {
  objectId: number;
  polygonIndex: number;
  pointIndex: number;
  previousPolygons: MaskPolygon[];
}

interface InsertPreview {
  objectId: number;
  polygonIndex: number;
  pointIndex: number;
  x: number;
  y: number;
}

interface UndoEdit {
  objectId: number;
  polygons: MaskPolygon[];
}

interface PointerLike {
  button?: number;
  buttons: number;
  clientX: number;
  clientY: number;
  altKey?: boolean;
  pointerId?: number;
  stopPropagation: () => void;
}

const VERTEX_HIT_RADIUS_PX = 8;

export default function MaskLayer({ containerRef }: { containerRef: RefObject<HTMLDivElement> }) {
  const { project, objects, selectedObjectId, setSelectedObjectId } = useProjectStore();
  const { frameIndex, overlayVersion, refreshOverlay, tool, zoom, scrubbing } = useAnnotationStore();
  const [frameAnnotation, setFrameAnnotation] = useState<FrameAnnotation>();
  const [polygonsByObject, setPolygonsByObject] = useState<Record<number, MaskPolygon[]>>({});
  const [drag, setDrag] = useState<DragState>();
  const [insertPreview, setInsertPreview] = useState<InsertPreview>();
  const [undoEdit, setUndoEdit] = useState<UndoEdit>();
  const [, setMessage] = useState("");
  const polygonsRef = useRef<Record<number, MaskPolygon[]>>({});
  const overlayVersionRef = useRef(overlayVersion);
  const pendingFrameRef = useRef<number>();
  const insertClearTimerRef = useRef<number>();

  const objectById = useMemo(() => new Map(objects.map((object) => [object.objectId, object])), [objects]);

  useEffect(() => {
    let cancelled = false;
    if (!project) {
      setFrameAnnotation(undefined);
      setPolygonsByObject({});
      return;
    }
    if (scrubbing) {
      setFrameAnnotation(undefined);
      setPolygonsByObject({});
      polygonsRef.current = {};
      return;
    }
    const forceRefresh = overlayVersion !== overlayVersionRef.current;
    getFrameAnnotations(project.projectId, frameIndex, project.activeVideoId, { force: forceRefresh })
      .then((annotation) => {
        if (cancelled) return;
        overlayVersionRef.current = overlayVersion;
        setFrameAnnotation(annotation);
        const next: Record<number, MaskPolygon[]> = {};
        for (const annotationObject of Object.values(annotation.objects)) {
          next[annotationObject.objectId] = annotationObject.polygons ?? [];
        }
        polygonsRef.current = next;
        setPolygonsByObject(next);
      })
      .catch((error) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Failed to load frame masks.");
      });
    return () => {
      cancelled = true;
    };
  }, [project?.projectId, project?.activeVideoId, frameIndex, overlayVersion, scrubbing]);

  useEffect(() => {
    if (tool !== "view") {
      setDrag(undefined);
      setInsertPreview(undefined);
    }
  }, [tool]);

  useEffect(() => {
    return () => {
      if (pendingFrameRef.current !== undefined) {
        window.cancelAnimationFrame(pendingFrameRef.current);
      }
      if (insertClearTimerRef.current !== undefined) {
        window.clearTimeout(insertClearTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) return;
      if (tool !== "view" || !undoEdit || !project) return;
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z") return;
      event.preventDefault();
      event.stopPropagation();
      restoreLastEdit();
    }
    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, [tool, undoEdit, project?.projectId, project?.activeVideoId, frameIndex]);

  useEffect(() => {
    if (!drag) return;
    function onPointerMove(event: globalThis.PointerEvent) {
      movePoint(event);
    }
    function onPointerUp(event: globalThis.PointerEvent) {
      void finishDrag(event);
    }
    window.addEventListener("pointermove", onPointerMove, { capture: true });
    window.addEventListener("pointerup", onPointerUp, { capture: true });
    window.addEventListener("pointercancel", onPointerUp, { capture: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove, { capture: true });
      window.removeEventListener("pointerup", onPointerUp, { capture: true });
      window.removeEventListener("pointercancel", onPointerUp, { capture: true });
    };
  }, [drag, project?.width, project?.height]);

  if (!project || !frameAnnotation) return null;
  const canEditMasks = tool === "view";
  const vertexRadius = 2 / zoom;
  const insertRadius = 2 / zoom;

  function pointerToImage(event: PointerLike) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || !project) return [0, 0] as [number, number];
    const x = Math.max(0, Math.min(project.width, ((event.clientX - rect.left) / rect.width) * project.width));
    const y = Math.max(0, Math.min(project.height, ((event.clientY - rect.top) / rect.height) * project.height));
    return [x, y] as [number, number];
  }

  function imageDistanceToScreenPixels(distance: number) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || !project) return distance;
    return distance * (rect.width / project.width);
  }

  function startDrag(event: ReactPointerEvent, nextDrag: DragState) {
    if (!canEditMasks || event.altKey || event.button !== 0) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const target = nearestVertex(pointerToImage(event), nextDrag.objectId) ?? nextDrag;
    setSelectedObjectId(target.objectId);
    setDrag(target);
    setUndoEdit(undefined);
    moveVertexToPointer(event, target);
  }

  function movePoint(event: PointerLike) {
    if (!drag) return;
    if ((event.buttons & 1) !== 1) {
      void finishDrag(event);
      return;
    }
    event.stopPropagation();
    const point = pointerToImage(event);
    const objectPolygons = cloneObjectPolygons(drag.objectId);
    if (!objectPolygons[drag.polygonIndex]?.[drag.pointIndex]) return;
    objectPolygons[drag.polygonIndex][drag.pointIndex] = point;
    setObjectPolygons(drag.objectId, objectPolygons);
  }

  function moveVertexToPointer(event: PointerLike, target: DragState) {
    event.stopPropagation();
    const point = pointerToImage(event);
    const objectPolygons = cloneObjectPolygons(target.objectId);
    if (!objectPolygons[target.polygonIndex]?.[target.pointIndex]) return;
    objectPolygons[target.polygonIndex][target.pointIndex] = point;
    setObjectPolygons(target.objectId, objectPolygons);
  }

  function updateInsertPreview(event: ReactPointerEvent, objectId: number, polygonIndex: number, polygon: MaskPolygon) {
    if (!canEditMasks || !project || drag || selectedObjectId !== objectId) return;
    cancelInsertClear();
    const point = pointerToImage(event);
    const match = nearestPolygonEdge(point, polygon, project.width, project.height);
    if (!match) {
      setInsertPreview((current) => current?.objectId === objectId && current.polygonIndex === polygonIndex ? undefined : current);
      return;
    }
    setInsertPreview({ objectId, polygonIndex, pointIndex: match.insertIndex, x: match.x, y: match.y });
  }

  function clearInsertPreview(objectId: number, polygonIndex: number) {
    cancelInsertClear();
    insertClearTimerRef.current = window.setTimeout(() => {
      setInsertPreview((current) => current?.objectId === objectId && current.polygonIndex === polygonIndex ? undefined : current);
      insertClearTimerRef.current = undefined;
    }, 120);
  }

  function cancelInsertClear() {
    if (insertClearTimerRef.current === undefined) return;
    window.clearTimeout(insertClearTimerRef.current);
    insertClearTimerRef.current = undefined;
  }

  function insertPoint(event: ReactPointerEvent, nextDrag: InsertPreview) {
    if (!canEditMasks || event.altKey || event.button !== 0) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const previousPolygons = cloneObjectPolygons(nextDrag.objectId);
    const objectPolygons = cloneObjectPolygons(nextDrag.objectId);
    const polygon = objectPolygons[nextDrag.polygonIndex];
    if (!polygon) return;
    polygon.splice(nextDrag.pointIndex, 0, [nextDrag.x, nextDrag.y]);
    setObjectPolygons(nextDrag.objectId, objectPolygons);
    setSelectedObjectId(nextDrag.objectId);
    setInsertPreview(undefined);
    setUndoEdit(undefined);
    setDrag({ ...nextDrag, previousPolygons });
  }

  function insertPointOnEdge(event: ReactPointerEvent, objectId: number, polygonIndex: number, insertIndex: number, start: [number, number], end: [number, number]) {
    if (!canEditMasks || event.altKey || event.button !== 0) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointerToImage(event);
    const projected = projectPointToSegment(point, start, end);
    const previousPolygons = cloneObjectPolygons(objectId);
    const nextDrag = { objectId, polygonIndex, pointIndex: insertIndex, x: projected.x, y: projected.y, previousPolygons };
    const objectPolygons = cloneObjectPolygons(objectId);
    const polygon = objectPolygons[polygonIndex];
    if (!polygon) return;
    polygon.splice(insertIndex, 0, [projected.x, projected.y]);
    setObjectPolygons(objectId, objectPolygons);
    setSelectedObjectId(objectId);
    setInsertPreview(undefined);
    setUndoEdit(undefined);
    setDrag(nextDrag);
  }

  async function finishDrag(event: PointerLike) {
    if (!drag || !project) return;
    event.stopPropagation();
    const completed = drag;
    setDrag(undefined);
    const polygons = polygonsRef.current[completed.objectId] ?? [];
    if (polygonsEqual(polygons, completed.previousPolygons)) return;
    setMessage("Saving polygon...");
    try {
      await savePolygonAnnotation(project.projectId, frameIndex, completed.objectId, polygons, project.activeVideoId, { allowOverwrite: true });
      refreshOverlay();
      setUndoEdit({ objectId: completed.objectId, polygons: completed.previousPolygons });
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save polygon.");
    }
  }

  async function restoreLastEdit() {
    if (!project || !undoEdit) return;
    const previous = undoEdit;
    setUndoEdit(undefined);
    setDrag(undefined);
    setObjectPolygons(previous.objectId, previous.polygons);
    setMessage("Restoring polygon...");
    try {
      await savePolygonAnnotation(project.projectId, frameIndex, previous.objectId, previous.polygons, project.activeVideoId, { allowOverwrite: true });
      refreshOverlay();
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to restore polygon.");
    }
  }

  function setObjectPolygons(objectId: number, objectPolygons: MaskPolygon[]) {
    polygonsRef.current = { ...polygonsRef.current, [objectId]: objectPolygons };
    if (pendingFrameRef.current !== undefined) return;
    pendingFrameRef.current = window.requestAnimationFrame(() => {
      pendingFrameRef.current = undefined;
      setPolygonsByObject(polygonsRef.current);
    });
  }

  function cloneObjectPolygons(objectId: number) {
    return (polygonsRef.current[objectId] ?? []).map((polygon) => polygon.map((item) => [...item] as [number, number]));
  }

  function nearestPolygonEdge(point: [number, number], polygon: MaskPolygon, imageWidth: number, imageHeight: number) {
    let best: { insertIndex: number; x: number; y: number; distance: number } | undefined;
    for (let index = 0; index < polygon.length; index += 1) {
      const start = polygon[index];
      const end = polygon[(index + 1) % polygon.length];
      const projection = projectPointToSegment(point, start, end);
      const endpointDistance = Math.min(
        imageDistanceToScreenPixels(Math.hypot(projection.x - start[0], projection.y - start[1])),
        imageDistanceToScreenPixels(Math.hypot(projection.x - end[0], projection.y - end[1]))
      );
      if (endpointDistance < VERTEX_HIT_RADIUS_PX * 1.5) {
        continue;
      }
      if (!best || projection.distance < best.distance) {
        best = { insertIndex: index + 1, ...projection };
      }
    }
    const threshold = Math.max(imageWidth, imageHeight) * 0.012;
    return best && best.distance <= threshold ? best : undefined;
  }

  function projectPointToSegment(point: [number, number], start: [number, number], end: [number, number]) {
    const vx = end[0] - start[0];
    const vy = end[1] - start[1];
    const lengthSquared = vx * vx + vy * vy || 1;
    const t = Math.max(0, Math.min(1, ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / lengthSquared));
    const x = start[0] + vx * t;
    const y = start[1] + vy * t;
    return { x, y, distance: Math.hypot(point[0] - x, point[1] - y) };
  }

  function nearestVertex(point: [number, number], objectId: number): DragState | undefined {
    const objectPolygons = polygonsRef.current[objectId] ?? [];
    let best: { polygonIndex: number; pointIndex: number; distance: number } | undefined;
    for (let polygonIndex = 0; polygonIndex < objectPolygons.length; polygonIndex += 1) {
      const polygon = objectPolygons[polygonIndex];
      for (let pointIndex = 0; pointIndex < polygon.length; pointIndex += 1) {
        const vertex = polygon[pointIndex];
        const distance = Math.hypot(point[0] - vertex[0], point[1] - vertex[1]);
        if (!best || distance < best.distance) {
          best = { polygonIndex, pointIndex, distance };
        }
      }
    }
    if (!best || imageDistanceToScreenPixels(best.distance) > VERTEX_HIT_RADIUS_PX) {
      return undefined;
    }
    return {
      objectId,
      polygonIndex: best.polygonIndex,
      pointIndex: best.pointIndex,
      previousPolygons: cloneObjectPolygons(objectId),
    };
  }

  return (
    <>
	      <svg
	        className="mask-layer"
	        viewBox={`0 0 ${project.width} ${project.height}`}
	        preserveAspectRatio="none"
	        onPointerMove={movePoint}
	        onPointerUp={finishDrag}
	        onPointerCancel={finishDrag}
	      >
	        {Object.values(frameAnnotation.objects).map((annotationObject) => {
	          const object = objectById.get(annotationObject.objectId);
	          if (object && !object.visible) return null;
	          const color = object?.color ?? [255, 0, 0];
	          const selected = selectedObjectId === annotationObject.objectId;
	          const locked = Boolean(annotationObject.locked);
	          const polygons = polygonsByObject[annotationObject.objectId] ?? [];
	          const showMaskFallback = polygons.length === 0 && Boolean(annotationObject.maskUrl);
	          const maskId = `mask-image-${frameAnnotation.frameIndex}-${annotationObject.objectId}`;
	          return (
	            <g key={annotationObject.objectId} className={`mask-object ${selected ? "selected" : ""}`} style={{ color: rgb(color) }}>
	              {showMaskFallback && (
	                <>
	                  <defs>
	                    <mask id={maskId} maskUnits="userSpaceOnUse" x={0} y={0} width={project.width} height={project.height}>
	                      <image href={maskUrl(annotationObject.maskUrl, overlayVersion)} x={0} y={0} width={project.width} height={project.height} preserveAspectRatio="none" />
	                    </mask>
	                  </defs>
	                  <rect
	                    className="mask-image-fill"
	                    x={0}
	                    y={0}
	                    width={project.width}
	                    height={project.height}
	                    fill={rgb(color)}
	                    mask={`url(#${maskId})`}
	                    onPointerDown={(event) => {
	                      if (!canEditMasks || event.altKey) return;
	                      event.stopPropagation();
	                      setSelectedObjectId(annotationObject.objectId);
	                    }}
	                  />
	                  {annotationObject.bbox && annotationObject.bbox[2] > annotationObject.bbox[0] && annotationObject.bbox[3] > annotationObject.bbox[1] && (
	                    <rect
	                      className="mask-image-bbox"
	                      x={annotationObject.bbox[0]}
	                      y={annotationObject.bbox[1]}
	                      width={annotationObject.bbox[2] - annotationObject.bbox[0]}
	                      height={annotationObject.bbox[3] - annotationObject.bbox[1]}
	                      fill="none"
	                      stroke={rgb(color)}
	                    />
	                  )}
	                </>
	              )}
	              {polygons.map((polygon, polygonIndex) => (
	                <g key={`${annotationObject.objectId}-${polygonIndex}`}>
                  <polygon
                    points={polygon.map((point) => point.join(",")).join(" ")}
                    fill={rgb(color)}
                    stroke={rgb(color)}
                    style={{ pointerEvents: canEditMasks ? "auto" : "none" }}
                    onPointerDown={(event) => {
                      if (!canEditMasks || event.altKey) return;
                      event.stopPropagation();
                      setSelectedObjectId(annotationObject.objectId);
                    }}
                    onPointerMove={(event) => canEditMasks && !locked && updateInsertPreview(event, annotationObject.objectId, polygonIndex, polygon)}
                    onPointerLeave={() => clearInsertPreview(annotationObject.objectId, polygonIndex)}
                  />
                  {canEditMasks && selected && !locked && polygon.length >= 3 && polygon.map((point, pointIndex) => {
                    const nextPoint = polygon[(pointIndex + 1) % polygon.length];
                    return (
                      <line
                        className="mask-insert-edge"
                        key={`edge-${annotationObject.objectId}-${polygonIndex}-${pointIndex}`}
                        x1={point[0]}
                        y1={point[1]}
                        x2={nextPoint[0]}
                        y2={nextPoint[1]}
                        onPointerMove={(event) => updateInsertPreview(event, annotationObject.objectId, polygonIndex, polygon)}
                        onPointerLeave={() => clearInsertPreview(annotationObject.objectId, polygonIndex)}
                      />
                    );
                  })}
                  {canEditMasks && selected && !locked && insertPreview?.objectId === annotationObject.objectId && insertPreview.polygonIndex === polygonIndex && (
                    <circle
                      className="insert-point"
                      cx={insertPreview.x}
                      cy={insertPreview.y}
                      r={insertRadius}
                      onPointerEnter={cancelInsertClear}
                      onPointerDown={(event) => insertPoint(event, insertPreview)}
                      onPointerMove={movePoint}
                      onPointerUp={finishDrag}
                      onPointerCancel={finishDrag}
                    />
                  )}
                  {canEditMasks && selected && !locked && polygon.map((point, pointIndex) => (
                    <circle
                      className="vertex-point"
                      key={`vertex-${annotationObject.objectId}-${polygonIndex}-${pointIndex}`}
                      cx={point[0]}
                      cy={point[1]}
                      r={vertexRadius}
                      onPointerDown={(event) => startDrag(event, { objectId: annotationObject.objectId, polygonIndex, pointIndex, previousPolygons: cloneObjectPolygons(annotationObject.objectId) })}
                      onPointerMove={movePoint}
                      onPointerUp={finishDrag}
                      onPointerCancel={finishDrag}
                    />
                  ))}
                </g>
              ))}
            </g>
          );
        })}
      </svg>
    </>
  );
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
}

function maskUrl(url: string | undefined, version: number) {
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${version}`;
}

function polygonsEqual(left: MaskPolygon[], right: MaskPolygon[]) {
  if (left.length !== right.length) return false;
  return left.every((polygon, polygonIndex) => {
    const other = right[polygonIndex];
    return polygon.length === other?.length && polygon.every((point, pointIndex) => {
      const otherPoint = other[pointIndex];
      return otherPoint && point[0] === otherPoint[0] && point[1] === otherPoint[1];
    });
  });
}
