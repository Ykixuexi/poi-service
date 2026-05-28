# Heritage Explorer — 全国文物保护单位空间信息系统

> 基于 RESTful API 的 POI 信息服务，提供全国 2356 处文物保护单位的查询与地图可视化

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ 功能特性

- 🔐 **双重认证** — 支持 API Key 和 JWT Token 两种认证方式
- 🔍 **多维查询** — 按名称、省份、类型、批次组合筛选
- 📍 **空间检索** — 支持坐标范围（bbox）和中心半径查询
- 🗺️ **地图可视化** — 高德地图集成，支持框选查询
- 📱 **响应式设计** — 适配桌面端与移动端
- 🌙 **深色主题** — 科技感 UI，玻璃拟态设计

---

## 🛠️ 技术栈

### 后端
| 技术 | 说明 |
|------|------|
| **Python 3.8+** | 运行环境 |
| **FastAPI** | 高性能异步 Web 框架 |
| **Uvicorn** | ASGI 服务器 |
| **Pandas** | 数据处理与筛选 |
| **PyJWT** | JWT Token 生成与验证 |

### 前端
| 技术 | 说明 |
|------|------|
| **Vue 3** | 响应式 UI 框架（CDN 引入） |
| **高德地图 JS API** | 地图服务与交互 |
| **CSS3** | Flexbox 布局、CSS 变量、媒体查询 |
| **Google Fonts** | Inter + Noto Serif SC 字体 |

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/poi-service.git
cd poi-service
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 准备数据

将 `全国文保单位.xlsx` 放置于 `../数据包/实验3-POI/` 目录下

### 4. 启动服务

```bash
python app.py
```

### 5. 访问应用

| 地址 | 说明 |
|------|------|
| http://127.0.0.1:8000 | API 根路径 |
| http://127.0.0.1:8000/static/index.html | 前端界面 |
| http://127.0.0.1:8000/docs | Swagger API 文档 |

---

## 📡 API 接口

### 认证方式

```bash
# 方式1: API Key（URL 参数）
GET /api/poi?apikey=sicisp2026

# 方式2: JWT Token（Header）
POST /api/token?user_id=test  # 获取 Token
GET /api/poi -H "Authorization: Bearer <token>"
```

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/poi` | POI 列表（支持 province/type/batch 参数组合筛选） |
| GET | `/api/poi/search?name=xxx` | 按名称模糊搜索 |
| GET | `/api/poi/province/{省份}` | 按省份查询 |
| GET | `/api/poi/type/{类型}` | 按类型查询 |
| GET | `/api/poi/batch/{批次}` | 按批次查询 |
| GET | `/api/poi/bbox` | 按坐标范围查询 |
| GET | `/api/poi/radius` | 按中心半径查询 |
| GET | `/api/poi/{id}` | 获取单个 POI 详情 |
| GET | `/api/stats/overview` | 统计概览 |

### 响应格式

```json
{
  "code": 200,
  "biz_code": 1000,
  "message": "查询成功",
  "data": { ... },
  "timestamp": "2026-05-28T16:00:00"
}
```

---

## 📁 项目结构

```
├── app.py                 # FastAPI 后端主程序
├── requirements.txt       # Python 依赖
├── README.md              # 项目说明
├── UI_GUIDE.md            # 前端 UI 修改指南
├── .gitignore
└── static/
    └── index.html         # Vue 3 前端单页应用
```

---

## 🎨 界面预览

- **深色科技风格** — 网格背景 + 呼吸光晕
- **玻璃拟态卡片** — 半透明毛玻璃效果
- **地图标记** — 发光圆点 + 名称标签
- **响应式布局** — 移动端自适应

---

## 📝 开发说明

### 高德地图 Key 配置

1. 访问 [高德开放平台](https://lbs.amap.com/) 注册账号
2. 创建应用 → 添加 Key（Web端 JS API）
3. 修改 `static/index.html` 中的 Key 值

### 自定义 API Key

修改 `app.py` 中的配置：

```python
API_KEY = "your_custom_key"
SECRET_KEY = "your_jwt_secret"
```

---

## 📄 License

MIT License
