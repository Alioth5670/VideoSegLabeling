# ⚙️ Configuration

**[Documentation](README.md) | [中文](../zh/configuration.md)**

Copy the environment template:

```bash
cp .env.example .env
```

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

## Backend Options

| Backend | Description | Requirements | Use Case |
|---------|-------------|--------------|----------|
| `mock` | Mock backend, no model needed | None | UI testing and demos |
| `sam3_video` | SAM3 video predictor | GPU + SAM3 checkpoint | Video segmentation |
| `sam3_multiplex_video` | SAM3.1 multiplex video predictor | GPU + SAM3.1 checkpoint | High-performance segmentation |

On multi-GPU servers, expose one physical GPU:

```bash
CUDA_VISIBLE_DEVICES=0 SAM_DEVICE=cuda:0 ./start.sh
```

## Project Data Structure

Projects are stored in `projects/` by default:

```text
projects/
├── {project_id}/
│   ├── project.json
│   ├── annotations.json
│   ├── videos/
│   ├── frames/
│   ├── masks/
│   └── overlays/
└── .gitkeep
```

Uploaded folder structures are preserved. `projects/*` is Git-ignored, with only `.gitkeep` committed.

## Repository Structure

```text
VideoSegLabeling/
├── backend/
├── frontend/
├── sam3/
├── checkpoints/
├── projects/
├── docs/
├── deploy/
├── requirements.txt
├── install.sh
├── start.sh
├── start_backend.sh
├── start_frontend.sh
├── build_release.sh
├── stop.sh
├── LICENSE
└── README.md
```
