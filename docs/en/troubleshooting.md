# 🐛 Troubleshooting

**[Documentation](README.md) | [中文](../zh/troubleshooting.md)**

## Blank Page After Startup

Clear browser cache or disable cache in Chrome DevTools, then refresh.

## Cannot Connect to Backend

```bash
ps aux | grep start_backend.sh
lsof -i :8010
tail -f logs/backend.log
```

## SAM Model Loading Fails

Check:

- SAM3 submodule is initialized.
- Checkpoint files exist in `checkpoints/`.
- `.env` paths are correct.
- GPU memory is sufficient. At least 8 GB is recommended.

## Frontend Styles Do Not Load in Dev Mode

```bash
./start_frontend.sh
rm -rf frontend/node_modules/.vite
```

## Project Export Is Slow

Reduce video resolution or frame rate, or export only the required frame range.
