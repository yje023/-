# 全区单位考核系统 — API 接口规范 v1.1

## 通用说明
- 基础路径：`/api`
- 认证方式：请求头 `Authorization: Bearer <token>`
- 返回格式：`{ data?: any, msg?: string }`
- 列表返回：`{ data: { items: [], total: number }, msg: string }`

## 认证模块 `POST/GET/PUT /api/auth`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /auth/login | 登录 | 否 |
| GET | /auth/me | 当前用户信息 | 是 |
| PUT | /auth/password | 修改密码 | 是 |
| PUT | /auth/identity | 切换主考/被考核身份 | 是 |

## 机构管理 `/api/orgs`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /orgs | 组织机构树/列表（支持 ?search= &parent_id=） |
| POST | /orgs | 新建机构 |
| PUT | /orgs/:id | 编辑机构 |
| DELETE | /orgs/:id | 删除机构 |
| POST | /orgs/batch-delete | 批量删除 |
| POST | /orgs/import | xlsx 批量导入 |
| GET | /orgs/export | xlsx 导出 |

## 单位管理 `/api/units`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /units | 单位列表（支持 ?search= &org_id=） |
| POST | /units | 新建单位 |
| PUT | /units/:id | 编辑单位 |
| DELETE | /units/:id | 删除单位 |
| PUT | /units/:id/move | 移动单位到其他机构 |
| POST | /units/batch-delete | 批量删除 |
| POST | /units/import | xlsx 批量导入 |
| GET | /units/export | xlsx 导出 |

## 用户管理 `/api/users`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /users | 用户列表（支持 ?search= &unit_id=） |
| POST | /users | 新建用户 |
| PUT | /users/:id | 编辑用户 |
| DELETE | /users/:id | 删除用户 |

## 角色管理 `/api/roles`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /roles | 角色列表（支持 ?search=） |
| POST | /roles | 新建角色（含权限配置） |
| PUT | /roles/:id | 编辑角色 |
| DELETE | /roles/:id | 删除角色 |
| GET | /roles/menus | 获取所有菜单权限列表 |

## 考核方案 `/api/plans`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /plans | 方案列表 |
| POST | /plans | 创建方案 |
| PUT | /plans/:id | 编辑方案 |
| DELETE | /plans/:id | 删除方案 |
| POST | /plans/:id/issue | 下发方案 |
| POST | /plans/:id/dimensions | 添加评价维度 |
| PUT | /dimensions/:id | 编辑评价维度 |
| DELETE | /dimensions/:id | 删除评价维度 |
| POST | /dimensions/:id/assessment-dims | 添加考核维度（仅单位实际考核） |
| PUT | /assessment-dims/:id | 编辑考核维度 |
| DELETE | /assessment-dims/:id | 删除考核维度 |
| PUT | /plans/:id/assessor-units | 设置主考单位 |
| POST | /plans/:id/groups | 创建被考核分组 |
| PUT | /groups/:id | 编辑分组 |
| DELETE | /groups/:id | 删除分组 |
| PUT | /groups/:id/weights | 设置分组维度权重 |

## 考核任务 `/api/tasks`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /tasks | 任务列表（支持 ?plan_id= &unit_id= &status=） |
| POST | /tasks | 创建任务 |
| PUT | /tasks/:id | 编辑任务 |
| DELETE | /tasks/:id | 删除任务 |
| PUT | /tasks/:id/review | 审核任务 |
| POST | /tasks/import | xlsx 批量导入 |
| GET | /tasks/export | xlsx 导出 |
| POST | /tasks/:id/submit | 被考核单位提交填报 |
| POST | /tasks/:id/score | 主考单位打分 |
