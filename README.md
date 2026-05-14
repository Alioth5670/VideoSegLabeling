# 🎬 VideoSegLabeling

**English | [中文](README_ZH.md)**

> A powerful browser-based video segmentation labeling tool with AI-assisted annotations, real-time mask propagation, and flexible project management.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.1.0-green.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react)

## ✨ Key Features

- 🎥 **Video & Multimedia Support** - Upload and manage multiple video projects
- 🖱️ **Flexible Annotation Tools** - Point, bounding box, text prompt, and polygon editing
- 🤖 **AI-Powered Segmentation** - Integrated SAM3/SAM3.1 for intelligent segmentation
- 📊 **Mask Propagation** - Automatically propagate segmentation results across video frames
- 📁 **Project Management** - Complete project creation, editing, deletion, and export workflows
- 🔄 **Batch Operations** - Efficient batch deletion and editing capabilities
- 🖥️ **Web Interface** - Modern React + TypeScript frontend

## 📦 Distribution Methods

This project is available through two distribution channels:

| Type | Description | Use Case |
|------|-------------|----------|
| **GitHub Source Repository** | Contains backend code, frontend source, scripts, docs, and SAM3 submodule | Development, custom extensions |
| **GitHub Release Package** | Includes prebuilt frontend (`frontend/dist`), no Node.js required | Quick deployment, production |

> ℹ️ Docker deployment is not included in this version.

## 📜 License

This project is licensed under the **Apache 2.0** license. See [LICENSE](LICENSE) for details.

### ⚖️ SAM3 License Notice

SAM3 is referenced as a Git submodule and is governed by Meta's SAM License. SAM3 model weights, checkpoints, and other SAM materials are **not included** in this repository or release packages. Configure local SAM3 paths using these environment variables:

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

---

## 🚀 Quick Start

### Method 1: From Release Package (Recommended for New Users)

1. **Download and Extract**
   ```bash
   tar -xzf VideoSegLabeling-x.x.x.tar.gz
   cd VideoSegLabeling-x.x.x
   ```

2. **Install Dependencies**
   ```bash
   ./install.sh
   # Select option 1: Install Python dependencies only (frontend is pre-built)
   ```

3. **Launch Application**
   ```bash
   ./start.sh
   ```

4. **Open in Browser**
   ```
   http://127.0.0.1:8010
   ```

   > By default uses `SAM_BACKEND=mock`, ideal for testing UI and workflow without GPU setup.

---

### Method 2: From Source Code (For Developers)

1. **Clone Repository**
   ```bash
   git clone <your-repo-url>
   cd VideoSegLabeling
   cp .env.example .env
   ```

2. **Install Dependencies**
   ```bash
   ./install.sh
   # Select option 2: Install Python dependencies and fetch SAM3
   # Select option 3: Build frontend as well (recommended for all-in-one deployment)
   ```

3. **Start Application**
   
   **Option A: All-in-One Launch** (Backend and frontend share one FastAPI server)
   ```bash
   ./start.sh
   # Visit http://127.0.0.1:8010
   ```

   **Option B: Separate Launch** (Best for frontend development)
   ```bash
   # Terminal 1: Start backend
   ./start_backend.sh
   
   # Terminal 2: Start frontend dev server
   ./start_frontend.sh
   # Visit http://localhost:5173
   ```

---

## 📖 Manual Installation (Advanced Users)

### Python Virtual Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# On Windows:
# .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

### SAM3 Setup (Optional)

**From Git submodule:**
```bash
git submodule update --init --recursive
```

**Or clone directly (for release package users):**
```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```

### Frontend Build (Optional, source code users only)

```bash
cd frontend
npm ci
npm run build
```

### Start Application

```bash
./start.sh
```

---

## ⚙️ Configuration

### Environment Variables

1. **Copy Configuration Template**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file**

### Common Configuration Variables

```env
# Server configuration
BACKEND_PORT=8010
PROJECTS_DIR=./projects

# SAM model backend
SAM_BACKEND=mock                           # Options: mock, sam3_video, sam3_multiplex_video
SAM_DEVICE=cuda:0
CUDA_VISIBLE_DEVICES=0

# SAM3 path configuration
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

### Backend Model Comparison

| Backend | Description | Requirements | Use Case |
|---------|-------------|--------------|----------|
| **mock** | Mock backend, no model needed | None | UI testing, demos |
| **sam3_video** | SAM3 video predictor | GPU + SAM3.pt | Video segmentation |
| **sam3_multiplex_video** | SAM3.1 multiplex video | GPU + SAM3.1_multiplex.pt | High-performance segmentation |

### Multi-GPU Configuration

On multi-GPU servers, it's recommended to expose only one physical GPU:

```bash
CUDA_VISIBLE_DEVICES=0 SAM_DEVICE=cuda:0 ./start.sh
```

---

## 📁 Project Data Structure

Projects are stored in the `projects/` directory by default:

```
projects/
├── {project_id}/
│   ├── project.json          # Project metadata
│   ├── annotations.json      # Annotation data
│   ├── videos/               # Uploaded video files
│   ├── frames/               # Extracted video frames
│   ├── masks/                # Segmentation masks
│   └── overlays/             # Mask overlay images
└── .gitkeep
```

**Features:**
- Uploaded folder structures are preserved
- Related videos and labels can be kept together in one project
- `projects/*` is Git-ignored, only `.gitkeep` is committed

---

## 💾 Building Release

### Create New Version

```bash
./build_release.sh
```

Generated files:
```
release/VideoSegLabeling-x.x.x/
release/VideoSegLabeling-x.x.x.tar.gz
```

### Release Specific Version

```bash
./build_release.sh 1.0.1
```

### Release Process

1. ✅ Script automatically builds frontend
2. ✅ Packages backend code
3. ✅ Generates `.tar.gz` file
4. 📤 Upload to GitHub Releases

> End users only need Python; no Node.js/npm/Vite/TypeScript required.

---

## 🗂️ Repository Structure

```
VideoSegLabeling/
├── backend/                    # FastAPI backend service
│   ├── run_backend.py          # Startup script
│   └── app/
│       ├── main.py             # Main application
│       ├── config.py           # Configuration
│       ├── api/                # API routes
│       ├── schemas/            # Data models
│       ├── services/           # Business logic
│       └── utils/              # Utilities
│
├── frontend/                   # React + Vite frontend
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── api/                # API client
│       ├── components/         # React components
│       ├── store/              # State management
│       ├── types/              # TypeScript types
│       └── utils/              # Utilities
│
├── sam3/                       # SAM3 model (Git submodule)
│   └── [Meta official code]
│
├── checkpoints/                # Model checkpoint directory
│   ├── sam3.pt                 # SAM3 weights (download required)
│   └── sam3.1_multiplex.pt     # SAM3.1 weights (download required)
│
├── projects/                   # Project data directory
│   └── [Project videos and annotations]
│
├── docs/                       # Documentation and guides
├── deploy/                     # Deployment configuration examples
├── requirements.txt            # Python dependencies
├── install.sh                  # Installation script
├── start.sh                    # Startup script
├── start_backend.sh            # Backend startup script
├── start_frontend.sh           # Frontend dev server script
├── build_release.sh            # Build release script
├── stop.sh                     # Shutdown script
├── LICENSE                     # Apache 2.0 license
└── README.md                   # This file
```

---

## 🎮 Usage Guide

### Create New Project

1. **Open application** → Home page
2. **Click** "Create Project" button
3. **Enter** project name and description
4. **Confirm** creation

### Upload Videos

1. **Enter project** → "Videos" tab
2. **Click** "Upload" button
3. **Select** video files or folder
4. **Wait** for upload and processing
5. **Preview** uploaded video list

### Annotate Videos

#### Basic Annotation Workflow

1. **Select video** and click to enter annotation editor
2. **Browse frames** using timeline or keyboard shortcuts
3. **Create annotations**:
   - 🖱️ **Point Prompt**: Click on object location
   - 📦 **Bounding Box**: Drag to create boundary
   - ✏️ **Polygon**: Click to draw shape
   - 💬 **Text Label**: Add text description to objects

4. **Propagate Masks**:
   - After annotation, click "Propagate" button
   - AI automatically applies mask to subsequent frames (if SAM backend configured)

5. **Edit and Adjust**:
   - Double-click mask to edit
   - Adjust boundaries, add or remove regions
   - Click "Save" to save changes

#### Keyboard Shortcuts

| Shortcut | Function |
|----------|----------|
| `←` / `→` | Previous / Next frame |
| `Spacebar` | Play / Pause |
| `Delete` | Delete selected annotation |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Escape` | Cancel current operation |

### Export Project

1. **Enter project** → "Export" tab
2. **Select** export format:
   - 📸 **Frames + Masks**: Images and masks
   - 📊 **JSON**: Annotation metadata
   - 🎥 **Video**: Video with mask overlay
3. **Click** "Export" to start
4. **Download** generated files

### Manage Objects

1. **View all objects** in annotation panel
2. **For each object**:
   - ✏️ Edit name and properties
   - 🎨 Change color
   - 🗑️ Delete individual object
3. **Batch delete**: Select multiple objects then click "Delete Selected"

---

## 🐛 Troubleshooting

### Issue: Blank page after startup

**Solution:**
```bash
# Clear browser cache
# Or in Chrome DevTools:
# Settings → Network conditions → Disable cache (check)
# Then refresh page
```

### Issue: Cannot connect to backend

**Check steps:**
```bash
# 1. Ensure backend is running
ps aux | grep start_backend.sh

# 2. Check if port is in use
lsof -i :8010

# 3. View backend logs
tail -f logs/backend.log
```

### Issue: Model loading fails (SAM backend)

**Checklist:**
- ✅ SAM3 submodule initialized: `git submodule update --init --recursive`
- ✅ Checkpoint files exist:
  ```bash
  ls -lh checkpoints/
  ```
- ✅ Correct paths in `.env`
- ✅ Sufficient GPU memory (≥ 8GB recommended)

### Issue: Styles not loading in frontend dev mode

**Solution:**
```bash
# Restart frontend dev server
./start_frontend.sh

# Clear Vite cache
rm -rf frontend/node_modules/.vite
```

### Issue: Project export is slow

**Optimization tips:**
- Reduce video resolution
- Lower video frame rate
- Export only necessary frame range

---

## 🔗 Resources

| Resource | Link |
|----------|------|
| **SAM3 Official** | [facebookresearch/sam3](https://github.com/facebookresearch/sam3) |
| **SAM License** | [Meta Research](https://github.com/facebookresearch/sam/blob/main/LICENSE) |
| **Deployment Guide** | [docs/server_deployment.md](docs/server_deployment.md) |
| **Report Issues** | [GitHub Issues](https://github.com/your-repo/issues) |

---

## 🚢 GitHub Release Checklist

### Pre-Release Verification

Before pushing code and creating a Release, execute these checks:

```bash
# 1. Check Git status
git status

# 2. Check submodule status
git submodule status

# 3. Build frontend
npm --prefix frontend run build

# 4. Verify Python syntax
python -m py_compile backend/app/main.py backend/run_backend.py

# 5. Run tests (if available)
# pytest tests/

# 6. Check for untracked files
git status --porcelain
```

### Release Process

1. **Create version tag**
   ```bash
   git tag vx.x.x
   ```

2. **Build Release package**
   ```bash
   ./build_release.sh x.x.x
   ```

3. **Push to GitHub**
   ```bash
   git push origin main
   git push origin vx.x.x
   ```

4. **Create GitHub Release**
   - Go to GitHub → Releases → "Create a new release"
   - Select `vx.x.x` tag
   - Write release notes
   - Upload `release/VideoSegLabeling-x.x.x.tar.gz`
   - Click "Publish release"

### Release Checklist

- [ ] Features tested and working
- [ ] Frontend and backend start correctly
- [ ] README documentation updated
- [ ] Version numbers updated
- [ ] Submodule points to correct branch
- [ ] No Git conflicts or uncommitted changes
- [ ] Frontend built
- [ ] Release package generated
- [ ] GitHub Release created

---

## 📚 Development Guide

### Frontend Development Workflow

```bash
# 1. Start backend
./start_backend.sh

# 2. In another terminal, start frontend dev server
./start_frontend.sh

# 3. Open http://localhost:5173
# Frontend changes auto-reload
```

### Backend Development Workflow

```bash
# Activate virtual environment
source .venv/bin/activate

# Start dev server with auto-reload
python backend/run_backend.py --reload

# Or use uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### Adding New Dependencies

```bash
# Python packages
pip install <package-name>
pip freeze > requirements.txt

# Frontend packages
cd frontend
npm install <package-name>
git add package.json package-lock.json
```

---

## ❓ FAQ

**Q: Why use Git submodules?**
> A: SAM3 is large; as a submodule it reduces clone time and keeps code independent. Users can choose whether they need the full SAM3 source.

**Q: Where to download model weights?**
> A: SAM3 and SAM3.1 weights must be downloaded separately from the [Meta SAM3 official repository](https://github.com/facebookresearch/sam3) and placed in `checkpoints/`.

**Q: Can it run on CPU?**
> A: Yes, but GPU is recommended for better performance. Use `SAM_DEVICE=cpu` configuration.

**Q: Does the Release package include all features?**
> A: Yes, all features are included. The only difference is the frontend is pre-built, so Node.js isn't needed.

**Q: How to upgrade to a new version?**
> A: Download the new Release package and extract it. Project data in `projects/` is preserved automatically.

**Q: Is multi-language support available?**
> A: Currently supports Chinese and English primarily. Other language contributions welcome!

---

## 🤝 Contributing

We welcome code contributions, bug reports, and feature suggestions!

### Reporting Bugs

1. Check [existing Issues](https://github.com/your-repo/issues)
2. Create new Issue with:
   - OS and Python version
   - Detailed reproduction steps
   - Error logs
   - Expected vs actual behavior

### Submitting PRs

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Create Pull Request

### Coding Standards

- **Python**: Follow PEP 8
- **TypeScript**: Use Prettier formatting
- **Commits**: Use clear, meaningful messages

---

## 📝 Changelog

### v0.1.0 (Current)

**New Features:**
- ✨ Complete video segmentation labeling tool
- 🤖 SAM3/SAM3.1 integration
- 📊 Mask propagation functionality
- 💾 Flexible project export

**Known Limitations:**
- Docker deployment not included
- SAM3 weights require separate download

---

## 📧 Contact

- 📖 Full documentation: See `docs/` directory
- 🐛 Issues: [GitHub Issues](https://github.com/your-repo/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/your-repo/discussions)

---

**Enjoy using VideoSegLabeling! Feel free to provide feedback and suggestions.** 🌟
