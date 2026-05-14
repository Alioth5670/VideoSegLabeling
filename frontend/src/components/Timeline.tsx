import { ChevronLeft, ChevronRight, Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { preloadFrameAnnotations } from "../api/annotation";
import { useAnnotationStore } from "../store/annotationStore";
import { useProjectStore } from "../store/projectStore";

const PRELOAD_AHEAD_FRAMES = 10;
const MAX_CACHED_FRAMES = 240;
const frameCache = new Map<string, { image: HTMLImageElement; lastUsed: number }>();
const frameRequests = new Map<string, Promise<void>>();

export default function Timeline() {
  const project = useProjectStore((s) => s.project);
  const frameIndex = useAnnotationStore((s) => s.frameIndex);
  const annotatedFrames = useAnnotationStore((s) => s.annotatedFrames);
  const playing = useAnnotationStore((s) => s.playing);
  const scrubbing = useAnnotationStore((s) => s.scrubbing);
  const setFrameIndex = useAnnotationStore((s) => s.setFrameIndex);
  const setPlaying = useAnnotationStore((s) => s.setPlaying);
  const setScrubbing = useAnnotationStore((s) => s.setScrubbing);
  const togglePlaying = useAnnotationStore((s) => s.togglePlaying);
  const projectFrameCount = project?.frameCount ?? 0;
  const validAnnotatedFrames = annotatedFrames.filter((frame) => frame >= 0 && frame < projectFrameCount);
  const firstAnnotatedFrame = validAnnotatedFrames.length > 0 ? Math.min(...validAnnotatedFrames) : undefined;
  const lastAnnotatedFrame = validAnnotatedFrames.length > 0 ? Math.max(...validAnnotatedFrames) : undefined;
  const [scrubFrame, setScrubFrame] = useState(frameIndex);
  const displayedFrame = scrubbing ? scrubFrame : frameIndex;

  useEffect(() => {
    if (!scrubbing) setScrubFrame(frameIndex);
  }, [frameIndex, scrubbing]);

  useEffect(() => {
    if (!project || scrubbing) return;
    const start = frameIndex + 1;
    const end = Math.min(project.frameCount - 1, frameIndex + PRELOAD_AHEAD_FRAMES);
    for (let index = start; index <= end; index += 1) {
      preloadFrame(frameUrl(project.projectId, index, project.activeVideoId));
    }
  }, [project, frameIndex, scrubbing]);

  useEffect(() => {
    if (!playing || !project) return;
    if (frameIndex >= project.frameCount - 1) {
      setPlaying(false);
      return;
    }

    let cancelled = false;
    let timeoutId: number | undefined;
    const delay = Math.max(30, 1000 / Math.max(project.fps, 1));

    timeoutId = window.setTimeout(() => {
      const currentFrame = useAnnotationStore.getState().frameIndex;
      const nextFrame = Math.min(project.frameCount - 1, currentFrame + 1);
      const nextUrl = frameUrl(project.projectId, nextFrame, project.activeVideoId);

      Promise.all([
        preloadFrame(nextUrl),
        preloadFrameAnnotations(project.projectId, nextFrame, project.activeVideoId)
      ]).then(() => {
        if (cancelled) return;
        setFrameIndex(nextFrame);
        if (nextFrame >= project.frameCount - 1) setPlaying(false);
      }).catch(() => {
        if (cancelled) return;
        setPlaying(false);
      });
    }, delay);

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [playing, project, frameIndex, setFrameIndex, setPlaying]);

  if (!project || project.frameCount === 0) return null;

  return (
    <footer className="timeline">
      <button title="Previous frame" onClick={() => setFrameIndex(Math.max(0, frameIndex - 1))}><ChevronLeft size={18} /></button>
      <button title="Play or pause" onClick={togglePlaying}>{playing ? <Pause size={18} /> : <Play size={18} />}</button>
      <button title="Next frame" onClick={() => setFrameIndex(Math.min(project.frameCount - 1, frameIndex + 1))}><ChevronRight size={18} /></button>
      <button title="Jump to first annotated frame" disabled={firstAnnotatedFrame === undefined} onClick={() => firstAnnotatedFrame !== undefined && setFrameIndex(firstAnnotatedFrame)}><SkipBack size={17} /></button>
      <button title="Jump to last annotated frame" disabled={lastAnnotatedFrame === undefined} onClick={() => lastAnnotatedFrame !== undefined && setFrameIndex(lastAnnotatedFrame)}><SkipForward size={17} /></button>
      <div className="timeline-range">
        <input
          className="timeline-scrubber"
          type="range"
	          min={0}
	          max={project.frameCount - 1}
	          value={displayedFrame}
	          style={{ "--timeline-progress": `${(displayedFrame / Math.max(1, project.frameCount - 1)) * 100}%` } as CSSProperties}
	          onPointerDown={() => {
	            setScrubFrame(frameIndex);
	            setScrubbing(true);
	            setPlaying(false);
	          }}
	          onPointerUp={() => {
	            setFrameIndex(scrubFrame);
	            setScrubbing(false);
	          }}
	          onPointerCancel={() => setScrubbing(false)}
	          onBlur={() => {
	            if (scrubbing) setFrameIndex(scrubFrame);
	            setScrubbing(false);
	          }}
	          onChange={(e) => {
	            const nextFrame = Number(e.target.value);
	            if (scrubbing) {
	              setScrubFrame(nextFrame);
	            } else {
	              setFrameIndex(nextFrame);
	            }
	          }}
	        />
        <div className="frame-marks">
          {annotatedFrames.map((frame) => (
            <span key={frame} style={{ left: `${(frame / Math.max(1, project.frameCount - 1)) * 100}%` }} />
          ))}
        </div>
      </div>
      <input className="frame-input" type="number" min={0} max={project.frameCount - 1} value={frameIndex} onChange={(e) => setFrameIndex(Number(e.target.value))} />
	      <span>{displayedFrame + 1} / {project.frameCount}</span>
    </footer>
  );
}

function frameUrl(projectId: string, frameIndex: number, videoId?: string) {
  const params = videoId ? `?video_id=${videoId}` : "";
  return `/api/projects/${projectId}/frames/${frameIndex}${params}`;
}

function preloadFrame(url: string) {
  const cached = frameCache.get(url);
  if (cached) {
    cached.lastUsed = Date.now();
    return Promise.resolve();
  }
  const existing = frameRequests.get(url);
  if (existing) return existing;

  const request = new Promise<void>((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      frameCache.set(url, { image, lastUsed: Date.now() });
      frameRequests.delete(url);
      trimFrameCache();
      resolve();
    };
    image.onerror = () => {
      frameRequests.delete(url);
      reject(new Error(`Failed to load frame: ${url}`));
    };
    image.src = url;
  });
  frameRequests.set(url, request);
  return request;
}

function trimFrameCache() {
  if (frameCache.size <= MAX_CACHED_FRAMES) return;
  const entries = [...frameCache.entries()].sort((a, b) => a[1].lastUsed - b[1].lastUsed);
  for (const [url] of entries.slice(0, frameCache.size - MAX_CACHED_FRAMES)) {
    frameCache.delete(url);
  }
}
