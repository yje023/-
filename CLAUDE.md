# CLAUDE.md — 全区单位考核系统开发指引

## 项目概述
全区单位考核系统 v1.1，基于 Flask + Vue 3 + Element Plus + SQLite 搭建的多人协作考核管理平台。

## 标准文件路径

| 文件 | 路径 | 说明 |
|------|------|------|
| 需求文档 | [docs/requirements.md](docs/requirements.md) | 完整功能需求 |
| 技术架构 | [docs/architecture.md](docs/architecture.md) | 技术选型与架构设计 |
| 设计规范 | [docs/design-spec.md](docs/design-spec.md) | 色彩、布局、交互规范 |
| API规范 | [docs/api-spec.md](docs/api-spec.md) | 所有接口定义 |
| 开发计划 | [.claude/plans/](.claude/plans/) | Claude Code 计划文件 |
| 开发日志 | [dev-logs/](dev-logs/) | 每日开发记录 |

## 工作说明

### 启动命令
```bash
# 后端
"C:\Users\Autismskyx\AppData\Local\Programs\Python\Python312\python.exe" backend/app.py

# 前端
cd frontend && npm run dev
```

### 开发流程
1. 每次开发前，阅读 `dev-logs/` 中最新日志，了解当前进度
2. 按照开发阶段逐步推进，每个阶段完成后验证通过再进入下一阶段
3. 每次修改后更新 `dev-logs/` 对应日期的日志文件
4. 遵循 `docs/design-spec.md` 的设计规范
5. API 变更同步更新 `docs/api-spec.md`

### 技术要点
- Python 路径：`C:\Users\Autismskyx\AppData\Local\Programs\Python\Python312\python.exe`
- 后端端口：5000，前端端口：3000
- 前端通过 Vite proxy 转发 `/api` 到后端
- 密码使用 Werkzeug bcrypt 加密
- JWT token 24小时过期
- 数据库文件：`backend/assessment.db`（SQLite，首次运行自动创建）
