# 🐛 故障排除

**[文档目录](README.md) | [English](../en/troubleshooting.md)**

## 启动后空白页面

清空浏览器缓存，或在 Chrome DevTools 中禁用缓存后刷新。

## 无法连接后端

```bash
ps aux | grep start_backend.sh
lsof -i :8010
tail -f logs/backend.log
```

## SAM 模型加载失败

检查：

- SAM3 子模块已初始化。
- 检查点文件存在于 `checkpoints/`。
- `.env` 中路径正确。
- GPU 显存充足，建议至少 8 GB。

## 前端开发模式样式不加载

```bash
./start_frontend.sh
rm -rf frontend/node_modules/.vite
```

## 项目导出慢

降低视频分辨率或帧率，或只导出必要帧范围。
