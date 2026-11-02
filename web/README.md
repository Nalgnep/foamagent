# 发泡管理系统前端（Vue 3 + Element Plus）

本目录为原生 JS 前端（`../frontend/app.js`）的重构版本，只做前端重构，
不改动后端逻辑。API 全部走相对路径 `/api/...`，请求头带 `X-User`
（演示用户，顶栏 el-select 选择，默认 `process_engineer`）。

## 开发 / 构建

```bash
cd web
npm install
npm run build   # 产物输出到 web/dist
npm run preview # 预览时 /api 代理到 http://127.0.0.1:8000（需后端在 8000 端口运行）
```

## 待主 agent 后续处理（本任务不做）

- 后端挂载 `web/dist`（当前后端仍挂载 `../frontend`）
- Dockerfile / docker-compose 的前端构建步骤
- GitHub 推送与 instabox 部署

## 数据说明

所有数字均来自后端 API；无独立验证集的指标在界面上显示为“未验证”，
不照抄任何截图数字。演示数据、模拟 PLC 回执的边界与 `../LIMITATIONS.md` 一致。
