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
