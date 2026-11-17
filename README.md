# 🎬 VideoSegLabeling

**English | [中文](README_ZH.md)**

Browser-based video segmentation labeling tool with AI-assisted annotations, mask propagation, and project export workflows.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.1.0-green.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react)

## ✨ Features

- 🎥 Video project upload, management, annotation, and export
- 🖱️ Point, box, polygon, and text prompt annotation tools
- 🤖 SAM3/SAM3.1 integration with a mock backend for UI testing
- 📊 Mask propagation across video frames
- 🖥️ React + TypeScript frontend and FastAPI backend

## 🚀 Quick Start

### Release Package

```bash
tar -xzf VideoSegLabeling-x.x.x.tar.gz
cd VideoSegLabeling-x.x.x
./install.sh
./start.sh
```

Open:

```text
http://127.0.0.1:8010
```

### Source Code

```bash
git clone <your-repo-url>
cd VideoSegLabeling
cp .env.example .env
./install.sh
./start.sh
```

For frontend development:

```bash
./start_backend.sh
./start_frontend.sh
```

Then open `http://localhost:5173`.

## Updating an existing deployment

From the repository root, using the existing `venv-server` environment:

```bash
venv-server/bin/python -m pip install -r requirements.txt
(cd frontend && npm ci && npm run build)
./start.sh
```

Stop the old backend before starting the updated service. With `frontend/dist` present, `./start.sh` serves the built UI through the backend. Use `./start.sh --dev` for both development servers in tmux. Check the startup log and `BACKEND_PORT` in `.env` for the address; the example configuration uses 8010. The current local launcher activates `venv-server`; a fresh installation can create it and build the UI with `VENV_DIR="$PWD/venv-server" ./install.sh --build-frontend`.

Before upgrading, stop the service and back up all of `PROJECTS_DIR` and registered custom project directories, including hidden `.accounts.sqlite3`, per-video `annotations.sqlite3`, videos, and masks. Legacy `annotations.json` alone does not include new annotations. Account and annotation databases migrate automatically. In-memory SAM sessions do not survive backend restarts.

See [CHANGELOG.md](CHANGELOG.md) for the full change list.

## 📚 Documentation

- [Full English documentation](docs/en/README.md)
- [完整中文文档](docs/zh/README.md)
- [License](LICENSE)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## ⚖️ SAM3 Notice

SAM3 is referenced as a Git submodule and is governed by Meta's SAM License. SAM3 weights and checkpoints are not included in this repository or release packages. Configure local paths with:

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

## 📜 License

This project is licensed under Apache 2.0. See [LICENSE](LICENSE).


## Accounts and private projects

Rebuild the frontend with `cd frontend && npm run build` and restart the backend after updating. On first visit, create the administrator account (password: at least 6 characters). Complete this initialization before exposing the service to other users. Existing projects, including registered custom directories, are indexed once and assigned to that administrator without moving video or annotation files.

Use **账户管理** in the top bar to create, disable or enable ordinary accounts. Disabling an account revokes its sessions. Ordinary accounts can only access their own projects. Administrators can manage projects across accounts and transfer ownership through the project management screen. Custom storage paths and shared SAM model/device changes require an administrator.

Project lists now use a SQLite index with search and pagination; annotation metadata uses the incremental SQLite storage described below; masks remain PNG files. Back up `PROJECTS_DIR/.accounts.sqlite3` together with project files. Direct `/projects/` access is disabled; project APIs, images and exports require authentication. Sessions last 24 hours and use HttpOnly/SameSite cookies. Set `AUTH_COOKIE_SECURE=true` for HTTPS deployments.

Run isolated access-control tests with `PYTHONPATH=backend venv-server/bin/python -m unittest discover -s backend/tests -v`.


## Annotation and inference performance

Each video's `annotations.sqlite3` is the source of truth. On first access, existing `annotations.json` is imported transactionally and retained as a legacy snapshot; it is no longer updated. Include SQLite and masks in backups. Project JSON exports and the full annotation API generate up-to-date JSON in the existing format. Hot annotation operations use indexed/incremental queries, propagated objects are committed per frame, and frontend refreshes request object/frame-index summaries.

COCO RLE uses vectorized NumPy operations. PNG files are stored without ZIP recompression; JSON uses fast compression. Unchanged exports reuse completed archives, with at most two cached versions per format.

Official SAM3/SAM3.1 initialization now uses demand-loaded CPU frames (default cache: 8), without a full-video loading thread. The official per-frame metadata and initial checkpoint load still take time. A repeated session request reuses the current video. Browsing another video/project leaves the live session intact; returning restores its session ID and tracked object list. Explicitly starting a different video session, closing it, or switching model/device releases the previous state. Reset keeps the session ID but clears tracked objects. Model operations are mutually exclusive. Official tracker state offload defaults to CPU, and recent backbone features are bounded (default: 4 frames). Streaming propagation saves masks immediately, uses a bounded event queue, and cancels when the client disconnects. OOM releases the session and asks for a new one rather than silently using mock masks.

Configure `SAM_FRAME_CACHE_SIZE`, `SAM_FEATURE_CACHE_SIZE`, and `SAM_OFFLOAD_STATE_TO_CPU` in the backend environment. Detailed per-frame mask logging is disabled by default to avoid extra GPU synchronization; enable `SAM_DEBUG_LOGGING=true` when diagnosing model outputs. CPU offload trades some propagation speed for lower VRAM usage; model weights, frame resolution, and object count must still fit the GPU. Use one backend process for the shared GPU model. Restart the backend and rebuild/refresh the frontend after updating; old annotations migrate on access.


## Background export jobs

`POST /api/projects/{project_id}/export` now accepts `{ "format": "coco_video_json", "video_id": "optional" }` and returns HTTP 202 with a job, rather than a completed download. Poll `GET /api/projects/{project_id}/export/{job_id}` for `status`, `progress` (0–100), and `stage`. A `download_url` becomes available only when `status` is `completed`. Existing synchronous API clients must update to this polling flow.

Encoding and archiving run in a separate Python process without importing SAM/CUDA. One export runs at a time, with up to eight outstanding jobs; duplicate pending submissions reuse the existing job and a full queue returns HTTP 429. Numerical library threads are limited in the worker. Annotation APIs remain usable, though machine CPU, memory, and disk resources are still shared.

The UI displays actual encoding/packing stages, polls every 750ms, and offers a download button on completion. Progress is work-based, not a remaining-time estimate. Job status is stored under each project's `exports/jobs/`, and the browser remembers the current job across page refreshes. Video selection is captured on submission; annotations are read when the worker runs. Backend shutdown interrupts unfinished jobs, which must be resubmitted after restart. Completed jobs remain queryable.


## Project management

The top-bar **项目管理** button opens searchable, paginated project management for every signed-in account. Users can create, open, rename, recycle, and restore their own projects. Administrators can filter by account, create projects for enabled accounts, open other accounts' annotations, and transfer projects to another enabled account. The labeling sidebar still lists the current user's projects by default.

Active project names are unique per account, ignoring case and surrounding whitespace. Rename, restore, and transfer operations enforce this rule. Transfers revoke the previous owner's access. Disabled accounts' existing projects remain manageable by administrators.

The recycle bin retains video, annotation, and export files. Recycled projects are hidden from regular lists and blocked from normal project/download APIs until restored. Idle SAM sessions are released on recycling or transfer; active inference must finish or be stopped first. The project index schema upgrades automatically at startup.


Browsing another video does not cancel propagation. Progress and the stop button keep the original project/video/session target, so a task can still be stopped while viewing a video without a session. Results stay attached to the original video. Sessions are runtime state and do not survive a backend restart or explicit replacement by another session.

Administrators can reset account passwords (minimum 6 characters), including their own, from account management. Resetting revokes that account’s login sessions; projects, annotations, SAM sessions, and enabled/disabled status are retained. Ordinary users cannot reset passwords.

Every account can use the top-bar **修改密码** action to change its own password by providing the current password and confirming a new password of at least 6 characters. Successful changes revoke that account’s login sessions without changing projects, annotations, or SAM sessions. Forgotten passwords can be reset by an administrator.

Project lists check metadata-file availability for the current page and label missing files in management and the sidebar. Missing records can still be recycled using an index-only operation. Records are never automatically removed; restoring temporarily unavailable storage and refreshing makes the files detectable again. Recycled records require their files to be available before restoration.


## Permanent deletion from the recycle bin

Recycled projects have a **彻底删除** action requiring the exact project name. It permanently removes project videos, annotations, exports, the ownership index entry, and the path registry entry. Ordinary accounts can delete only their own recycled projects; administrators can delete any recycled project. Active projects must be recycled first.

Already missing directories allow index-only cleanup. Existing directories require matching project metadata. Shared/public roots, symlinks, overlapping project roots, and custom directories containing unrelated files are rejected. Queued or running exports must finish before deletion. Permanent deletion cannot be undone.

The SAM3.1 adapter preserves consolidated interactive corrections and per-object views when clearing nearby propagated memory. This prevents stale consolidated-frame markers from referencing deleted outputs (`KeyError` during propagation), while ordinary non-conditioning caches still clear normally. The fix stays in the backend adapter, leaving the SAM3 submodule untouched. CPU regression tests execute the checked-in tracker methods for forward, reverse, and repeated propagation. Restart the backend and create a new inference session after updating; saved annotations are retained.

## SAM3.1 device compatibility and diagnostics

The backend adapter aligns mux/demux conversion matrices with the input cache device and dtype during multiplex state transitions, then restores the original matrix, keeping offloaded caches on CPU. Segmentation failures now log a full traceback with project, video, session, frame, and object identifiers. CPU regression tests cover the adapter; real CUDA inference has not been validated locally.
