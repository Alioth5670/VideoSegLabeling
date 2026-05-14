#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-0.1.0}"
NAME="VideoSegLabeling-${VERSION}"
RELEASE_ROOT="${ROOT_DIR}/release"
PACKAGE_DIR="${RELEASE_ROOT}/${NAME}"
ARCHIVE_PATH="${RELEASE_ROOT}/${NAME}.tar.gz"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js 18+ to build the frontend before packaging." >&2
  exit 1
fi

mkdir -p "${RELEASE_ROOT}"

write_release_readmes() {
  cat > "${PACKAGE_DIR}/README.md" <<'EOF'
# 🎬 VideoSegLabeling

**English | [中文](README_ZH.md)**

Browser-based video segmentation labeling tool with AI-assisted annotations, mask propagation, and project export workflows.

## 🚀 Quick Start

```bash
./install.sh
./start.sh
```

Open:

```text
http://127.0.0.1:8010
```

The release package includes a prebuilt frontend, so Node.js/npm/Vite/TypeScript are not required for normal use.

## 📚 Documentation

- [Release documentation](docs/en/README.md)
- [中文 Release 文档](docs/zh/README.md)
- [License](LICENSE)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## ⚖️ SAM3 Notice

SAM3 weights and checkpoints are not included in this release package. Configure local paths with:

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```
EOF

  cat > "${PACKAGE_DIR}/README_ZH.md" <<'EOF'
# 🎬 VideoSegLabeling

**[English](README.md) | 中文**

基于浏览器的视频分割标注工具，支持 AI 辅助标注、掩码传播和项目导出工作流。

## 🚀 快速开始

```bash
./install.sh
./start.sh
```

打开：

```text
http://127.0.0.1:8010
```

Release 包已包含预构建前端，正常使用不需要 Node.js/npm/Vite/TypeScript。

## 📚 文档

- [中文 Release 文档](docs/zh/README.md)
- [Release documentation](docs/en/README.md)
- [许可证](LICENSE)
- [第三方声明](THIRD_PARTY_NOTICES.md)

## ⚖️ SAM3 说明

SAM3 权重和检查点不包含在此 Release 包中。通过以下环境变量配置本地路径：

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```
EOF
}

copy_release_docs() {
  local lang="$1"
  local package_docs_dir="${PACKAGE_DIR}/docs/${lang}"

  mkdir -p "${package_docs_dir}"

  cp "${ROOT_DIR}/docs/${lang}/configuration.md" "${package_docs_dir}/configuration.md"
  cp "${ROOT_DIR}/docs/${lang}/usage.md" "${package_docs_dir}/usage.md"
  cp "${ROOT_DIR}/docs/${lang}/troubleshooting.md" "${package_docs_dir}/troubleshooting.md"
  cp "${ROOT_DIR}/docs/${lang}/license.md" "${package_docs_dir}/license.md"

  if [[ "${lang}" == "en" ]]; then
    cat > "${package_docs_dir}/README.md" <<'EOF'
# 🎬 VideoSegLabeling Release Documentation

**English | [中文](../zh/README.md) | [Home](../../README.md)**

This release package includes the documentation needed to install, configure, use, and troubleshoot VideoSegLabeling.

| Topic | Description |
|-------|-------------|
| [🚀 Quick Start](quick-start.md) | Install and start the release package |
| [⚙️ Configuration](configuration.md) | Environment variables, SAM backend options, GPU setup, and data layout |
| [🎮 Usage Guide](usage.md) | Project creation, video upload, annotation, shortcuts, and export |
| [🐛 Troubleshooting](troubleshooting.md) | Common startup, backend, model, frontend, and export issues |
| [📜 License Notes](license.md) | Apache 2.0 and SAM3 license notes |
EOF
    cat > "${package_docs_dir}/quick-start.md" <<'EOF'
# 🚀 Quick Start

**[Documentation](README.md) | [中文](../zh/quick-start.md)**

This Release package includes the prebuilt frontend. You only need Python for normal use.

## Start From Release Package

```bash
./install.sh
./start.sh
```

Open:

```text
http://127.0.0.1:8010
```

The default `SAM_BACKEND=mock` is suitable for testing the UI and workflow without GPU setup.

## Manual Python Installation

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

## SAM3 Setup

SAM3 source and model weights are not included in the release package. Clone SAM3 and place checkpoints under `checkpoints/`:

```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```
EOF
  else
    cat > "${package_docs_dir}/README.md" <<'EOF'
# 🎬 VideoSegLabeling Release 文档

**[English](../en/README.md) | 中文 | [首页](../../README_ZH.md)**

此 Release 包只包含安装、配置、使用和排障所需的文档。

| 主题 | 说明 |
|------|------|
| [🚀 快速开始](quick-start.md) | 安装并启动 Release 包 |
| [⚙️ 配置说明](configuration.md) | 环境变量、SAM 后端选项、GPU 配置和数据结构 |
| [🎮 使用指南](usage.md) | 创建项目、上传视频、标注、快捷键和导出 |
| [🐛 故障排除](troubleshooting.md) | 常见启动、后端、模型、前端和导出问题 |
| [📜 许可证说明](license.md) | Apache 2.0 和 SAM3 许可证说明 |
EOF
    cat > "${package_docs_dir}/quick-start.md" <<'EOF'
# 🚀 快速开始

**[文档目录](README.md) | [English](../en/quick-start.md)**

Release 包已包含预构建前端，正常使用只需要 Python。

## 从 Release 包启动

```bash
./install.sh
./start.sh
```

打开：

```text
http://127.0.0.1:8010
```

默认使用 `SAM_BACKEND=mock`，适合先测试 UI 和工作流，无需 GPU 配置。

## 手动安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows 激活方式：

```bash
.venv\Scripts\activate
```

## SAM3 设置

Release 包不包含 SAM3 源码和模型权重。克隆 SAM3，并将检查点放到 `checkpoints/`：

```bash
git clone https://github.com/facebookresearch/sam3.git sam3
```
EOF
  fi
}

echo "Building frontend"
cd "${ROOT_DIR}/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build

echo "Preparing ${PACKAGE_DIR}"
rm -rf "${PACKAGE_DIR}" "${ARCHIVE_PATH}"
mkdir -p "${PACKAGE_DIR}/frontend" "${PACKAGE_DIR}/projects" "${PACKAGE_DIR}/checkpoints"

cp -R "${ROOT_DIR}/backend" "${PACKAGE_DIR}/backend"
cp -R "${ROOT_DIR}/frontend/dist" "${PACKAGE_DIR}/frontend/dist"
cp "${ROOT_DIR}/requirements.txt" "${PACKAGE_DIR}/requirements.txt"
cp "${ROOT_DIR}/LICENSE" "${PACKAGE_DIR}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${PACKAGE_DIR}/THIRD_PARTY_NOTICES.md"
cp "${ROOT_DIR}/.env.example" "${PACKAGE_DIR}/.env.example"
cp "${ROOT_DIR}/install.sh" "${PACKAGE_DIR}/install.sh"
cp "${ROOT_DIR}/start.sh" "${PACKAGE_DIR}/start.sh"
cp "${ROOT_DIR}/start_backend.sh" "${PACKAGE_DIR}/start_backend.sh"
cp "${ROOT_DIR}/stop.sh" "${PACKAGE_DIR}/stop.sh"
cp "${ROOT_DIR}/projects/.gitkeep" "${PACKAGE_DIR}/projects/.gitkeep"
cp "${ROOT_DIR}/checkpoints/.gitkeep" "${PACKAGE_DIR}/checkpoints/.gitkeep"

write_release_readmes
copy_release_docs "en"
copy_release_docs "zh"

find "${PACKAGE_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${PACKAGE_DIR}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

chmod +x "${PACKAGE_DIR}/install.sh" "${PACKAGE_DIR}/start.sh" "${PACKAGE_DIR}/start_backend.sh" "${PACKAGE_DIR}/stop.sh"

cd "${RELEASE_ROOT}"
tar -czf "${ARCHIVE_PATH}" "${NAME}"

echo "Release package created:"
echo "  ${PACKAGE_DIR}"
echo "  ${ARCHIVE_PATH}"
