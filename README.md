# VideoSegLabeling

Version: `1.0.0`

VideoSegLabeling is a browser-based video segmentation labeling tool. It supports project management, folder/video upload, frame browsing, object management, point/box/text prompts, polygon editing, mask propagation, batch deletion, and project export.

The project is designed for two distribution paths:

- **GitHub source repository**: contains backend source, frontend source, scripts, docs, dependency manifests, and SAM3 as a Git submodule.
- **GitHub Release package**: contains backend source plus a prebuilt `frontend/dist`, so users do not need Node.js or npm to run the UI.

Docker is intentionally not included in `1.0.0`.

## License

This project is licensed under Apache-2.0. See `LICENSE`.

SAM3 is referenced as a Git submodule and is governed by Meta's SAM License. SAM3 model weights, checkpoints, and other SAM Materials are not committed to this repository or included in release packages. Configure local SAM3 paths with `SAM_REPO_PATH`, `SAM_CHECKPOINT_PATH`, and `SAM31_CHECKPOINT_PATH`.

## Quick Start From Release

Use this path if you downloaded `VideoSegLabeling-1.0.0.tar.gz` from GitHub Releases.

```bash
tar -xzf VideoSegLabeling-1.0.0.tar.gz
cd VideoSegLabeling-1.0.0
./install.sh
./start.sh
```

Choose option `1` in `install.sh` to install Python dependencies only. The release package already includes the frontend build.

Open:

```text
http://127.0.0.1:8010
```

By default the app starts with `SAM_BACKEND=mock`, which is useful for checking the UI and project workflow before configuring a real SAM backend.

## Quick Start From Source

Use this path if you cloned the repository.

```bash
git clone <your-repo-url>
cd VideoSegLabeling
cp .env.example .env
./install.sh
```

Choose option `2` to install Python dependencies and fetch SAM3. Choose option `3` if you also want to build `frontend/dist` and run everything from one FastAPI server:

```bash
./start.sh
```

For active frontend development, run backend and frontend separately:

```bash
./start_backend.sh
```

```bash
./start_frontend.sh
```

Then open:

```text
http://localhost:5173
```

## Manual Install

Python runtime:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional SAM3 setup:

```bash
git submodule update --init --recursive
```

If you are using a release package without Git metadata:

```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```

Optional frontend build from source:

```bash
cd frontend
npm ci
npm run build
```

Start:

```bash
./start.sh
```

## Configuration

Copy `.env.example` to `.env` and edit as needed.

Common variables:

```env
BACKEND_PORT=8010
PROJECTS_DIR=./projects
SAM_BACKEND=mock
SAM_DEVICE=cuda:0
CUDA_VISIBLE_DEVICES=0
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

Backend options:

- `SAM_BACKEND=mock`: portable default, no model required.
- `SAM_BACKEND=sam3_video`: SAM3 video predictor path.
- `SAM_BACKEND=sam3_multiplex_video`: SAM3.1 multiplex video path.

SAM3 source is available through the `sam3/` submodule and is governed by Meta's SAM License. Model checkpoints are external dependencies and are not committed. Place them at the paths configured in `.env`.

On multi-GPU servers, expose one physical GPU and keep the app-local device as `cuda:0`:

```bash
CUDA_VISIBLE_DEVICES=0 SAM_DEVICE=cuda:0 ./start.sh
```

## Project Data

Projects are stored under `projects/` by default:

```text
projects/{project_id}/
  project.json
  annotations.json
  videos/
  frames/
  masks/
  overlays/
```

Uploaded folders preserve their original relative structure where possible, so segmented video groups and labels can be kept together inside a project.

`projects/*` is ignored by Git. Only `projects/.gitkeep` is committed.

## Build A Release

From a source checkout:

```bash
./build_release.sh
```

The script builds the frontend and creates:

```text
release/VideoSegLabeling-1.0.0/
release/VideoSegLabeling-1.0.0.tar.gz
```

Upload the `.tar.gz` file to GitHub Releases. End users can run it with Python only; they do not need frontend source, npm, Vite, or TypeScript.

To build another version:

```bash
./build_release.sh 1.0.1
```

## Repository Layout

```text
backend/              FastAPI backend, project storage, SAM service adapters
frontend/             React + Vite + TypeScript frontend source
sam3/                 Git submodule pointing to facebookresearch/sam3
checkpoints/.gitkeep  Placeholder for local model checkpoints
projects/.gitkeep     Placeholder for local project data
requirements.txt      Python dependency list
install.sh            Interactive and CLI installer
start.sh              Release/source entrypoint
start_backend.sh      Backend-only entrypoint
start_frontend.sh     Frontend dev server entrypoint
build_release.sh      Creates GitHub Release package
docs/                 Notes and deployment references
```

## GitHub Publishing Checklist

Before pushing:

```bash
git status
git submodule status
npm --prefix frontend run build
python -m py_compile backend/app/main.py backend/run_backend.py
```

Recommended first release flow:

```bash
git tag v1.0.0
./build_release.sh 1.0.0
```

Then push the repository and upload `release/VideoSegLabeling-1.0.0.tar.gz` as the `v1.0.0` release asset.
