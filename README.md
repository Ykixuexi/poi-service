# Heritage Explorer — 全国文物保护单位空间信息系统

基于 FastAPI + PostgreSQL + PostGIS 的 RESTful POI 服务后端，支持全国 2356 处重点文物保护单位的空间查询、叠加分析、缓冲区分析、GeoJSON 输出、JWT 认证、Redis 缓存、Docker 容器化部署。

## 技术栈

| 层级 | 技术 |
|---|---|
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 17 + PostGIS 3.5 |
| 缓存 | Redis 7 |
| 认证 | JWT（HTTPBearer + bcrypt） |
| 前端 | Vue 3 + 高德地图（静态文件挂载，负责联调） |
| 部署 | Docker + docker-compose |
| 配置 | .env 环境变量 + psycopg2 连接池 |

## 接口列表

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | 用户注册 |
| POST | `/login` | 用户登录，返回 JWT Token |

### POI 查询

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/pois` | 组合查询（keyword/type/batch/province/框选/分页，10 个可选参数） |
| GET | `/pois?format=geojson` | GeoJSON 格式输出 |
| POST | `/pois` | 新增 POI（需认证） |
| PUT | `/pois/{poi_id}` | 修改 POI（需认证） |
| DELETE | `/pois/{poi_id}` | 删除 POI（需认证） |

### 空间分析

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/pois/radius?lat=&lon=&radius=` | 半径查询（ST_DWithin，球面距离） |
| GET | `/pois/{poi_id}/buffer?radius=` | 缓冲区分析（ST_Buffer + ST_Contains，含面积） |

### 统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/stats/province` | 按省份统计 |
| GET | `/stats/type` | 按类型统计 |
| GET | `/stats/batch` | 按批次统计 |

### 静态资源

| 路径 | 说明 |
|---|---|
| `/docs` | Swagger API 文档 |
| `/static/index.html` | 前端地图界面 |

## 空间能力

- **框选查询**：`geom && ST_MakeEnvelope()`，GIST 空间索引加速
- **半径查询**：`ST_DWithin(geom::geography, center, radius)`，geography 球面距离
- **叠加分析**：`ST_Contains(province_geom, pois.geom)`，点面叠加（暂离线）
- **缓冲区分析**：`ST_Buffer(geom::geography, radius)` + `ST_Contains`，返回面内 POI 及缓冲区面积
- **坐标系**：WGS84（EPSG:4326），GeoJSON 符合 OGC 规范

## 数据库表

| 表 | 说明 |
|---|---|
| `pois` | 2356 条文保单位（含 `geom geometry(Point,4326)` + GIST 索引） |
| `users` | 用户账号 |
| `provinces` | 全国 33 个省级行政区边界（MultiPolygon, 4326 + GIST 索引） |
| `spatial_ref_sys` | PostGIS 坐标系定义（自动生成） |

## 缓存策略

- **固定维度筛选**（type/batch/province 等）：Redis 缓存，1 小时 TTL
- **关键词搜索**（高度个性化）：直查数据库
- **GeoJSON 格式**：独立缓存 key（与普通 JSON 区分）
- 增删改后通过 SCAN 游标批量失效缓存

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 PostgreSQL（需提前安装）
pg_ctl -D "pgdata路径" start

# 3. 初始化数据库
psql -U root -d postgres -c "CREATE DATABASE repoi_system;"
psql -U root -d repoi_system -c "CREATE EXTENSION postgis;"

# 4. 导入数据
python import_poi.py               # Excel → PostgreSQL
# 省份 Shapefile 数据需手动导入

# 5. 建索引
psql -U root -d repoi_system -c "CREATE INDEX idx_pois_geom ON pois USING GIST (geom);"
psql -U root -d repoi_system -c "CREATE INDEX idx_pois_geog ON pois USING GIST ((geom::geography));"

# 6. 启动服务
uvicorn poi_api:app --reload

# 7. 访问
# API 文档:  http://localhost:8000/docs
# 前端页面:  http://localhost:8000/static/index.html
```

## Docker 部署

```bash
docker compose up --build -d
```

## 架构

```
用户浏览器 → Vue 3 + 高德地图
       ↓
  FastAPI (uvicorn)
       ├── JWT 认证中间件
       ├── Redis 缓存层（Cache-Aside）
       │   ├── 下拉框筛选 → 缓存
       │   └── 关键词搜索 → 直查
       └── PostgreSQL + PostGIS（psycopg2 连接池）
           ├── GIST 空间索引
           ├── geometry（框选）
           └── geography（半径/缓冲区）
```
