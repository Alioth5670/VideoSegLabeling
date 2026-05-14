# 🚀 Quick Start

**[Documentation](README.md) | [中文](../zh/quick-start.md)**

## Distribution Methods

| Type | Description | Use Case |
|------|-------------|----------|
| GitHub source repository | Backend code, frontend source, scripts, docs, and SAM3 submodule | Development and custom extensions |
| GitHub Release package | Prebuilt frontend (`frontend/dist`), no Node.js required | Quick deployment and production |

Docker deployment is not included in this version.

## From Release Package

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

The default `SAM_BACKEND=mock` is suitable for testing the UI and workflow without GPU setup.

## From Source Code

```bash
git clone <your-repo-url>
cd VideoSegLabeling
cp .env.example .env
./install.sh
./start.sh
```

For separate frontend development:

```bash
./start_backend.sh
./start_frontend.sh
```

Open `http://localhost:5173`.

## Manual Installation

### Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows, activate with:

```bash
.venv\Scripts\activate
```

### SAM3 Setup

From Git submodule:

```bash
git submodule update --init --recursive
```

Or clone directly for release package usage:

```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```

### Frontend Build

```bash
cd frontend
npm ci
npm run build
```
