# 💾 Release Guide

**[Documentation](README.md) | [中文](../zh/release.md)**

## Build Release Package

```bash
./build_release.sh
./build_release.sh 1.0.1
```

Generated output:

```text
release/VideoSegLabeling-x.x.x/
release/VideoSegLabeling-x.x.x.tar.gz
```

Release package users only need Python; Node.js/npm/Vite/TypeScript are not required.

## Release Checks

```bash
git status
git submodule status
npm --prefix frontend run build
python -m py_compile backend/app/main.py backend/run_backend.py
git status --porcelain
```

## Release Flow

```bash
git tag vx.x.x
./build_release.sh x.x.x
git push origin main
git push origin vx.x.x
```

Then create a GitHub Release and upload `release/VideoSegLabeling-x.x.x.tar.gz`.
