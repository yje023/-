# 全区单位考核系统 — 技术架构 v1.1

## 架构概览
```
浏览器 (前端)  ──HTTP──>  Flask (后端)  ──SQL──>  SQLite (数据库)
   Vue 3                    REST API                 单文件
   Element Plus             JWT 认证
```

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 前端框架 | Vue 3 | 3.5.x |
| UI 组件库 | Element Plus | 2.9.x |
| 状态管理 | Pinia | 2.3.x |
| 路由 | Vue Router | 4.5.x |
| HTTP 客户端 | Axios | 1.7.x |
| 后端框架 | Flask | 3.1.x |
| 认证 | Flask-JWT-Extended | 4.7.x |
| ORM | Flask-SQLAlchemy | via SQLAlchemy |
| 密码加密 | Werkzeug | 3.1.x |
| Excel 处理 | openpyxl | 3.1.x |
| 数据库 | SQLite | - |
| 构建工具 | Vite | 6.x |

## 目录结构
```
qjqgbkhxt/
├── docs/                  # 项目文档
├── dev-logs/              # 开发日志
├── backend/
│   ├── app.py             # Flask 入口
│   ├── config.py          # 配置文件
│   ├── models.py          # 数据模型
│   ├── routes/            # API 路由（按模块分文件）
│   ├── services/          # 业务逻辑层
│   └── utils/             # 工具类（xlsx处理等）
├── frontend/
│   ├── src/
│   │   ├── api/           # 后端接口封装
│   │   ├── components/    # 公用组件
│   │   ├── router/        # 路由配置
│   │   ├── store/         # Pinia 状态管理
│   │   └── views/         # 页面视图
│   └── vite.config.js
├── start.bat              # 一键启动
└── requirements.txt       # Python 依赖
```

## 安全设计
- 密码 bcrypt 哈希存储
- JWT token，24小时过期
- 后端权限校验（不依赖前端隐藏菜单）
- 数据库文件不对外暴露
- xlsx 上传校验（类型、格式、数据合法性）
- 批量操作使用数据库事务

## API 设计规范
- RESTful 风格
- 统一前缀 `/api/`
- 统一返回格式 `{ data, msg }`
- 认证通过 `Authorization: Bearer <token>` 头
