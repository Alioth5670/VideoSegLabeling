import { Lock, Trash2, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { batchDeleteAnnotations, deleteFrameAnnotation, getAnnotations, getFrameAnnotations, saveBBoxAnnotation, savePolygonAnnotation, updateFrameAnnotation } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";
import { rgb } from "../utils/color";
import type { MaskPolygon } from "../types/annotation";

interface StoredAnnotation {
  frameIndex: number;
  objectId: number;
  category: string;
  color: [number, number, number];
  bbox: [number, number, number, number];
  area: number;
  source: string;
  isKeyframe: boolean;
  locked: boolean;
}

interface RawStoredObject {
  category?: string;
  color?: [number, number, number];
}

interface RawFrameObject {
  bbox?: [number, number, number, number];
  area?: number;
  source?: string;
  is_keyframe?: boolean;
  isKeyframe?: boolean;
  locked?: boolean;
}

interface RawFrame {
  objects?: Record<string, RawFrameObject>;
}

interface RawAnnotations {
  objects?: Record<string, RawStoredObject>;
  frames?: Record<string, RawFrame>;
}

interface UndoDelete {
  row: StoredAnnotation;
  polygons: MaskPolygon[];
}

export default function AnnotationPanel() {
  const { project, objects, selectedObjectId, setObjects, setSelectedObjectId } = useProjectStore();
  const { frameIndex, overlayVersion, setAnnotatedFrames, setFrameIndex, refreshOverlay } = useAnnotationStore();
  const [annotations, setAnnotations] = useState<StoredAnnotation[]>([]);
  const [busyKey, setBusyKey] = useState("");
  const [message, setMessage] = useState("");
  const [undoDelete, setUndoDelete] = useState<UndoDelete>();
  const [batchStartFrame, setBatchStartFrame] = useState(frameIndex);
  const [batchEndFrame, setBatchEndFrame] = useState(frameIndex);
  const [batchScope, setBatchScope] = useState<"all" | "selected">("all");
  const objectById = useMemo(() => new Map(objects.map((obj) => [obj.objectId, obj])), [objects]);
  const currentFrameAnnotations = useMemo(
    () => annotations.filter((row) => row.frameIndex === frameIndex),
    [annotations, frameIndex]
  );

  useEffect(() => {
    if (!project) {
      setAnnotations([]);
      return;
    }
    loadAnnotations();
  }, [project?.projectId, project?.activeVideoId, overlayVersion, objects]);

  useEffect(() => {
    setBatchStartFrame(frameIndex);
    setBatchEndFrame(frameIndex);
  }, [project?.projectId, project?.activeVideoId, frameIndex]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((!event.ctrlKey && !event.metaKey) || event.key.toLowerCase() !== "z" || event.shiftKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (!undoDelete || busyKey !== "") return;
      event.preventDefault();
      undoLastDelete();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undoDelete, busyKey, project?.projectId, project?.activeVideoId]);

  async function loadAnnotations() {
    if (!project) return;
    const data = await getAnnotations(project.projectId, project.activeVideoId) as RawAnnotations;
    const rows: StoredAnnotation[] = [];
    for (const [frameKey, frame] of Object.entries(data.frames ?? {})) {
      for (const [objectKey, ann] of Object.entries(frame.objects ?? {})) {
        const objectId = Number(objectKey);
        const obj = data.objects?.[objectKey] ?? objectById.get(objectId);
        rows.push({
          frameIndex: Number(frameKey),
          objectId,
          category: obj?.category ?? `object ${objectId}`,
          color: obj?.color ?? [255, 0, 0],
          bbox: ann.bbox ?? [0, 0, 0, 0],
          area: ann.area ?? 0,
          source: ann.source ?? "unknown",
          isKeyframe: Boolean(ann.is_keyframe ?? ann.isKeyframe),
          locked: Boolean(ann.locked)
        });
      }
    }
    rows.sort((a, b) => a.frameIndex - b.frameIndex || a.objectId - b.objectId);
    setAnnotations(rows);
    setAnnotatedFrames([...new Set(rows.map((row) => row.frameIndex))]);
  }

  async function jumpTo(row: StoredAnnotation) {
    setFrameIndex(row.frameIndex);
    setSelectedObjectId(row.objectId);
  }

  async function remove(row: StoredAnnotation) {
    if (!project) return;
    const confirmed = window.confirm(`Delete completed annotation for #${row.objectId} ${row.category} on frame ${row.frameIndex}?`);
    if (!confirmed) return;
    const key = `${row.frameIndex}:${row.objectId}`;
    setBusyKey(key);
    setMessage("Deleting annotation...");
    try {
      const frame = await getFrameAnnotations(project.projectId, row.frameIndex, project.activeVideoId, { force: true });
      const deletedObject = frame.objects[row.objectId];
      const response = await deleteFrameAnnotation(project.projectId, row.frameIndex, row.objectId, project.activeVideoId);
      await loadAnnotations();
      refreshOverlay();
      if (response.deleted) {
        if (response.object_deleted) {
          const nextObjects = objects.filter((object) => object.objectId !== row.objectId);
          setObjects(nextObjects);
          if (selectedObjectId === row.objectId) setSelectedObjectId(nextObjects[0]?.objectId);
        }
        setUndoDelete({ row, polygons: deletedObject?.polygons ?? [] });
        setMessage("Annotation deleted.");
      } else {
        setUndoDelete(undefined);
        setMessage("No annotation found.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to delete annotation.");
    } finally {
      setBusyKey("");
    }
  }

  async function toggleLock(row: StoredAnnotation) {
    if (!project) return;
    const key = `${row.frameIndex}:${row.objectId}`;
    setBusyKey(key);
    try {
      await updateFrameAnnotation(project.projectId, row.frameIndex, row.objectId, { locked: !row.locked }, project.activeVideoId);
      await loadAnnotations();
      refreshOverlay();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to update annotation lock.");
    } finally {
      setBusyKey("");
    }
  }

  async function undoLastDelete() {
    if (!project || !undoDelete) return;
    setBusyKey(`${undoDelete.row.frameIndex}:${undoDelete.row.objectId}`);
    setMessage("Restoring annotation...");
    try {
      if (undoDelete.polygons.length > 0) {
        const saved = await savePolygonAnnotation(project.projectId, undoDelete.row.frameIndex, undoDelete.row.objectId, undoDelete.polygons, project.activeVideoId);
        if (saved.object) upsertObject(saved.object);
      } else {
        const saved = await saveBBoxAnnotation(project.projectId, undoDelete.row.frameIndex, undoDelete.row.objectId, undoDelete.row.bbox, project.activeVideoId);
        if (saved.object) upsertObject(saved.object);
      }
      setFrameIndex(undoDelete.row.frameIndex);
      setSelectedObjectId(undoDelete.row.objectId);
      setUndoDelete(undefined);
      await loadAnnotations();
      refreshOverlay();
      setMessage("Annotation restored.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to restore annotation.");
    } finally {
      setBusyKey("");
    }
  }

  async function removeBatch(deleteAnnotations: boolean, deletePrompts: boolean) {
    if (!project) return;
    const maxFrame = Math.max(0, project.frameCount - 1);
    const start = clampFrame(batchStartFrame, maxFrame);
    const end = clampFrame(batchEndFrame, maxFrame);
    const lower = Math.min(start, end);
    const upper = Math.max(start, end);
    const objectIds = batchScope === "selected" && selectedObjectId !== undefined ? [selectedObjectId] : undefined;
    if (batchScope === "selected" && selectedObjectId === undefined) {
      setMessage("Select an object before deleting selected-object data.");
      return;
    }
    const target = objectIds ? `object #${objectIds[0]}` : "all objects";
    const content = deleteAnnotations && deletePrompts ? "annotations and prompts" : (deleteAnnotations ? "annotations" : "prompts");
    const confirmed = window.confirm(`Delete ${content} for ${target} from frame ${lower} to ${upper}?`);
    if (!confirmed) return;
    setBusyKey("batch");
    setUndoDelete(undefined);
    setMessage("Deleting batch...");
    try {
      const result = await batchDeleteAnnotations(project.projectId, {
        startFrame: lower,
        endFrame: upper,
        objectIds,
        deleteAnnotations,
        deletePrompts
      }, project.activeVideoId);
      if (result.deleted_object_ids.length > 0) {
        const deleted = new Set(result.deleted_object_ids);
        const nextObjects = objects.filter((object) => !deleted.has(object.objectId));
        setObjects(nextObjects);
        if (selectedObjectId !== undefined && deleted.has(selectedObjectId)) {
          setSelectedObjectId(nextObjects[0]?.objectId);
        }
      }
      await loadAnnotations();
      if (deleteAnnotations) refreshOverlay();
      setMessage(`Deleted ${result.deleted_annotations} annotations and ${result.deleted_prompts} prompts.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to delete batch.");
    } finally {
      setBusyKey("");
    }
  }

function upsertObject(rawObject: any) {
    const nextObject = {
      objectId: rawObject.object_id,
      trackId: rawObject.track_id,
      category: rawObject.category,
      color: rawObject.color,
      visible: rawObject.visible,
      locked: rawObject.locked,
      createdFrame: rawObject.created_frame
    };
    setObjects(objects.some((object) => object.objectId === nextObject.objectId)
      ? objects.map((object) => object.objectId === nextObject.objectId ? nextObject : object)
      : [...objects, nextObject]);
  }

  return (
    <section className="panel annotation-panel">
      <div className="panel-title annotation-title">
        <span>Current Frame Annotations</span>
        <span className="annotation-title-actions">
          {project && <span className="annotation-count-inline">{currentFrameAnnotations.length}</span>}
          <button disabled={!undoDelete || busyKey !== ""} title="Undo last deleted annotation" onClick={undoLastDelete}>Undo</button>
        </span>
      </div>
      {!project && <span className="empty-prompts">No project open</span>}
      {project && currentFrameAnnotations.length === 0 && <span className="empty-prompts">No annotations on frame {frameIndex}</span>}
      {message && <span className="annotation-message">{message}</span>}
      {project && (
        <details className="annotation-batch-panel">
          <summary className="annotation-batch-head">
            <span>Batch Delete</span>
            <span>{Math.min(clampFrame(batchStartFrame, Math.max(0, project.frameCount - 1)), clampFrame(batchEndFrame, Math.max(0, project.frameCount - 1)))}-{Math.max(clampFrame(batchStartFrame, Math.max(0, project.frameCount - 1)), clampFrame(batchEndFrame, Math.max(0, project.frameCount - 1)))}</span>
          </summary>
          <div className="annotation-range-row">
            <label>
              <span>From</span>
              <input
                className="text-input"
                type="number"
                min={0}
                max={project.frameCount ? project.frameCount - 1 : 0}
                value={batchStartFrame}
                onChange={(event) => setBatchStartFrame(Number(event.target.value))}
                aria-label="Batch delete start frame"
              />
            </label>
            <label>
              <span>To</span>
              <input
                className="text-input"
                type="number"
                min={0}
                max={project.frameCount ? project.frameCount - 1 : 0}
                value={batchEndFrame}
                onChange={(event) => setBatchEndFrame(Number(event.target.value))}
                aria-label="Batch delete end frame"
              />
            </label>
          </div>
          <select className="text-input" value={batchScope} onChange={(event) => setBatchScope(event.target.value as "all" | "selected")}>
            <option value="all">All objects</option>
            <option value="selected">Selected object</option>
          </select>
          <div className="annotation-batch-actions">
            <button className="command danger" disabled={busyKey !== ""} onClick={() => removeBatch(true, false)}>Annotations</button>
            <button className="command danger" disabled={busyKey !== ""} onClick={() => removeBatch(false, true)}>Prompts</button>
            <button className="command danger" disabled={busyKey !== ""} onClick={() => removeBatch(true, true)}>Both</button>
          </div>
        </details>
      )}
      <div className="annotation-list">
        {currentFrameAnnotations.map((row) => {
          const key = `${row.frameIndex}:${row.objectId}`;
          const active = row.objectId === selectedObjectId;
          return (
            <div className={`annotation-row ${active ? "selected" : ""}`} key={key}>
              <button className="annotation-main" title="Select annotation" onClick={() => jumpTo(row)}>
                <span className="swatch" style={{ background: rgb(row.color) }} />
                <span className="annotation-label">
                  <strong>#{row.objectId}</strong>
                  <span>{row.category}</span>
                </span>
              </button>
              <button className="annotation-icon" disabled={busyKey === key} title={row.locked ? "Unlock annotation editing" : "Lock annotation editing"} onClick={() => toggleLock(row)}>
                {row.locked ? <Lock size={15} /> : <Unlock size={15} />}
              </button>
              <button className="annotation-icon danger" disabled={busyKey === key} title="Delete completed annotation" onClick={() => remove(row)}>
                <Trash2 size={15} />
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function clampFrame(frameIndex: number, maxFrame: number) {
  if (!Number.isFinite(frameIndex)) return 0;
  return Math.max(0, Math.min(maxFrame, Math.round(frameIndex)));
}
