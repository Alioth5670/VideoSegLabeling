import { Eye, EyeOff, Link2Off, Trash2 } from "lucide-react";
import { createObject, deleteObject, removeObjectFromSession, updateObject } from "../api/project";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";
import { rgb } from "../utils/color";

function normalizeObject(obj: any) {
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

export default function ObjectPanel() {
  const { project, objects, selectedObjectId, setObjects, setSelectedObjectId } = useProjectStore();
  const frameIndex = useAnnotationStore((s) => s.frameIndex);
  const refreshOverlay = useAnnotationStore((s) => s.refreshOverlay);
  const sessionId = useAnnotationStore((s) => s.sessionId);
  const sessionObjectIds = useAnnotationStore((s) => s.sessionObjectIds);
  const removeSessionObjectId = useAnnotationStore((s) => s.removeSessionObjectId);

  async function addObject() {
    if (!project) return;
    const input = window.prompt("Category", "object");
    if (input === null) return;
    const category = input.trim() || "object";
    const obj = normalizeObject(await createObject(project.projectId, category, frameIndex, project.activeVideoId));
    setObjects([...objects, obj]);
    setSelectedObjectId(obj.objectId);
  }

  async function patchObject(objectId: number, patch: Record<string, unknown>) {
    if (!project) return;
    const updated = normalizeObject(await updateObject(project.projectId, objectId, patch, project.activeVideoId));
    setObjects(objects.map((obj) => (obj.objectId === objectId ? updated : obj)));
    refreshOverlay();
  }

  async function removeObject(objectId: number) {
    if (!project) return;
    const target = objects.find((obj) => obj.objectId === objectId);
    const label = target ? `#${target.objectId} ${target.category}` : `#${objectId}`;
    const confirmed = window.confirm(`Delete object ${label}? This will remove its masks and frame annotations from the project.`);
    if (!confirmed) return;
    const result = await deleteObject(project.projectId, objectId, project.activeVideoId, sessionId);
    if (result.sam_warning) {
      console.warn(`Failed to remove object ${objectId} from SAM session: ${result.sam_warning}`);
    }
    const next = objects.filter((obj) => obj.objectId !== objectId);
    setObjects(next);
    setSelectedObjectId(next[0]?.objectId);
    removeSessionObjectId(objectId);
    refreshOverlay();
  }

  async function removeTrackedObject(objectId: number) {
    if (!project || !sessionId) return;
    await removeObjectFromSession(project.projectId, objectId, sessionId, project.activeVideoId);
    removeSessionObjectId(objectId);
  }

  return (
    <section className="panel object-panel">
      <div className="panel-title object-panel-title">
        <span>Objects</span>
        <button disabled={selectedObjectId === undefined} onClick={() => setSelectedObjectId(undefined)}>Clear</button>
      </div>
      <button className="command" disabled={!project} onClick={addObject}>Add Object</button>
      {objects.length === 0 && <span className="empty-prompts">No objects</span>}
      <div className="object-list">
        {objects.map((obj) => {
          const trackedInSession = sessionObjectIds.includes(obj.objectId);
          return (
          <div className={`object-row ${selectedObjectId === obj.objectId ? "selected" : ""}`} key={obj.objectId} onClick={() => setSelectedObjectId(obj.objectId)}>
            <span className="swatch" style={{ background: rgb(obj.color) }} />
            <label className="object-category">
              <span>#{obj.objectId}</span>
              <input aria-label={`Object ${obj.objectId} category`} value={obj.category} onChange={(e) => patchObject(obj.objectId, { category: e.target.value })} />
            </label>
            <button title="Toggle visibility" onClick={(e) => { e.stopPropagation(); patchObject(obj.objectId, { visible: !obj.visible }); }}>
              {obj.visible ? <Eye size={16} /> : <EyeOff size={16} />}
            </button>
            <button disabled={!trackedInSession || !sessionId} title="Remove from current SAM session" onClick={(e) => { e.stopPropagation(); removeTrackedObject(obj.objectId); }}>
              <Link2Off size={16} />
            </button>
            <button className="danger" title="Delete object" onClick={(e) => { e.stopPropagation(); removeObject(obj.objectId); }}>
              <Trash2 size={16} />
            </button>
          </div>
          );
        })}
      </div>
    </section>
  );
}
