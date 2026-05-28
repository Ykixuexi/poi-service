"""
POI 信息服务 - RESTful API
全国文物保护单位查询服务
"""
from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
import pandas as pd
import jwt
import math
import os
from datetime import datetime, timedelta

# ==================== 配置 ====================
SECRET_KEY = "sicisp2026_poi_secret_key"
ALGORITHM = "HS256"
API_KEY = "sicisp2026"  # 简单 API Key

# 业务状态码
class BizCode:
    SUCCESS = 1000           # 成功
    UNAUTHORIZED = 1001      # 未授权
    INVALID_TOKEN = 1002     # Token 无效
    POI_NOT_FOUND = 2001     # POI 未找到
    INVALID_PARAMS = 2002    # 参数无效
    SERVER_ERROR = 5000      # 服务器错误

# ==================== 数据加载 ====================
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "数据包", "实验3-POI", "全国文保单位.xlsx")

def load_poi_data():
    """加载 POI 数据"""
    df = pd.read_excel(DATA_PATH)
    # 提取省份（从地址中）
    df['province'] = df['add'].apply(lambda x: x[:3] if pd.notna(x) and len(x) >= 3 else '未知')
    # 是否有扩展信息（备注）
    df['has_extra'] = df['remark'].notna()
    # 处理 NaN 值，替换为 None（JSON 兼容）
    df = df.fillna('')
    return df

poi_df = load_poi_data()
print(f"已加载 {len(poi_df)} 条 POI 数据")

# ==================== FastAPI 应用 ====================
app = FastAPI(
    title="POI 信息服务",
    description="全国文物保护单位查询 RESTful API",
    version="1.0.0"
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务（前端页面）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ==================== 响应格式 ====================
def api_response(code: int, biz_code: int, message: str, data=None, help_url: str = None):
    """统一 API 响应格式"""
    response = {
        "code": code,
        "biz_code": biz_code,
        "message": message,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    if help_url:
        response["help_url"] = help_url
    return JSONResponse(status_code=code, content=response)

# ==================== 认证 ====================
def create_token(user_id: str) -> str:
    """生成 JWT Token"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_auth(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, alias="apikey")
):
    """验证认证信息（支持 JWT 和 API Key）"""
    # 方式1：API Key
    if api_key == API_KEY:
        return {"user_id": "apikey_user", "auth_type": "apikey"}
    
    # 方式2：JWT Token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return {"user_id": payload["user_id"], "auth_type": "jwt"}
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已过期")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token 无效")
    
    raise HTTPException(status_code=401, detail="未提供有效的认证信息")

# ==================== API 路由 ====================

@app.get("/")
def root():
    """API 首页"""
    return api_response(200, BizCode.SUCCESS, "POI 信息服务运行中", {
        "service": "全国文物保护单位查询服务",
        "version": "1.0.0",
        "endpoints": {
            "获取Token": "POST /api/token",
            "POI列表": "GET /api/poi",
            "POI详情": "GET /api/poi/{id}",
            "按名称查询": "GET /api/poi/search?name=xxx",
            "按省份查询": "GET /api/poi/province/{province}",
            "按范围查询": "GET /api/poi/bbox?min_lon=&min_lat=&max_lon=&max_lat=",
            "按半径查询": "GET /api/poi/radius?lon=&lat=&radius=",
        }
    })

@app.post("/api/token")
def get_token(user_id: str = Query(..., description="用户ID")):
    """获取 JWT Token"""
    token = create_token(user_id)
    return api_response(200, BizCode.SUCCESS, "Token 生成成功", {
        "token": token,
        "expires_in": 86400,
        "token_type": "Bearer"
    })

@app.get("/api/poi")
def list_poi(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=5000, description="每页数量"),
    has_extra: Optional[bool] = Query(None, description="是否有扩展信息"),
    province: Optional[str] = Query(None, description="省份"),
    poi_type: Optional[str] = Query(None, alias="type", description="类型"),
    batch: Optional[str] = Query(None, description="批次"),
    auth: dict = Depends(verify_auth)
):
    """获取 POI 列表（分页，支持多条件组合筛选）"""
    df = poi_df.copy()
    
    # 筛选省份
    if province:
        df = df[df['add'].str.contains(province, na=False)]
    
    # 筛选类型
    if poi_type:
        df = df[df['type'].str.contains(poi_type, na=False)]
    
    # 筛选批次
    if batch:
        df = df[df['batch'].str.contains(batch, na=False)]
    
    # 筛选有无扩展信息
    if has_extra is not None:
        df = df[df['has_extra'] == has_extra]
    
    total = len(df)
    start = (page - 1) * size
    end = start + size
    
    records = df.iloc[start:end].to_dict('records')
    
    return api_response(200, BizCode.SUCCESS, "查询成功", {
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size),
        "items": records
    })

@app.get("/api/poi/search")
def search_poi(
    name: str = Query(..., min_length=1, description="名称关键词"),
    auth: dict = Depends(verify_auth)
):
    """按名称搜索 POI"""
    df = poi_df[poi_df['name'].str.contains(name, na=False)]
    
    if len(df) == 0:
        return api_response(404, BizCode.POI_NOT_FOUND, f"未找到包含 '{name}' 的 POI", 
                          help_url="/api/poi")
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/province/{province}")
def get_poi_by_province(
    province: str,
    auth: dict = Depends(verify_auth)
):
    """按省份查询 POI"""
    df = poi_df[poi_df['add'].str.contains(province, na=False)]
    
    if len(df) == 0:
        return api_response(404, BizCode.POI_NOT_FOUND, f"未找到 '{province}' 的 POI",
                          help_url="/api/poi")
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "province": province,
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/bbox")
def get_poi_by_bbox(
    min_lon: float = Query(..., description="最小经度"),
    min_lat: float = Query(..., description="最小纬度"),
    max_lon: float = Query(..., description="最大经度"),
    max_lat: float = Query(..., description="最大纬度"),
    auth: dict = Depends(verify_auth)
):
    """按坐标范围查询 POI（地图拉框）"""
    if min_lon > max_lon or min_lat > max_lat:
        return api_response(400, BizCode.INVALID_PARAMS, "坐标范围参数无效",
                          help_url="/api/poi/bbox?min_lon=100&min_lat=25&max_lon=105&max_lat=30")
    
    df = poi_df[
        (poi_df['lon'] >= min_lon) & (poi_df['lon'] <= max_lon) &
        (poi_df['lat'] >= min_lat) & (poi_df['lat'] <= max_lat)
    ]
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/radius")
def get_poi_by_radius(
    lon: float = Query(..., description="中心点经度"),
    lat: float = Query(..., description="中心点纬度"),
    radius: float = Query(..., gt=0, le=500, description="半径（公里）"),
    auth: dict = Depends(verify_auth)
):
    """按中心半径查询 POI"""
    def haversine(lon1, lat1, lon2, lat2):
        """计算两点间距离（公里）"""
        R = 6371  # 地球半径
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c
    
    # 计算每个 POI 到中心点的距离
    df = poi_df.copy()
    df['distance'] = df.apply(lambda row: haversine(lon, lat, row['lon'], row['lat']), axis=1)
    df = df[df['distance'] <= radius].sort_values('distance')
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "center": [lon, lat],
        "radius_km": radius,
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/type/{poi_type}")
def get_poi_by_type(
    poi_type: str,
    auth: dict = Depends(verify_auth)
):
    """按类型查询 POI"""
    df = poi_df[poi_df['type'].str.contains(poi_type, na=False)]
    
    if len(df) == 0:
        return api_response(404, BizCode.POI_NOT_FOUND, f"未找到类型 '{poi_type}' 的 POI",
                          help_url="/api/stats/types")
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "type": poi_type,
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/batch/{batch}")
def get_poi_by_batch(
    batch: str,
    auth: dict = Depends(verify_auth)
):
    """按批次查询 POI"""
    df = poi_df[poi_df['batch'].str.contains(batch, na=False)]
    
    if len(df) == 0:
        return api_response(404, BizCode.POI_NOT_FOUND, f"未找到批次 '{batch}' 的 POI",
                          help_url="/api/stats/batches")
    
    return api_response(200, BizCode.SUCCESS, f"找到 {len(df)} 条结果", {
        "batch": batch,
        "total": len(df),
        "items": df.to_dict('records')
    })

@app.get("/api/poi/{poi_id}")
def get_poi_detail(
    poi_id: int,
    auth: dict = Depends(verify_auth)
):
    """获取单个 POI 详情"""
    df = poi_df[poi_df['code'] == poi_id]
    
    if len(df) == 0:
        return api_response(404, BizCode.POI_NOT_FOUND, f"POI (code={poi_id}) 不存在",
                          help_url="/api/poi")
    
    return api_response(200, BizCode.SUCCESS, "查询成功", df.iloc[0].to_dict())

@app.get("/api/stats/overview")
def get_stats_overview(auth: dict = Depends(verify_auth)):
    """获取统计概览"""
    return api_response(200, BizCode.SUCCESS, "统计概览", {
        "total_count": len(poi_df),
        "province_count": poi_df['province'].nunique(),
        "type_count": poi_df['type'].nunique(),
        "has_extra_count": int(poi_df['has_extra'].sum()),
        "batch_distribution": poi_df['batch'].value_counts().to_dict(),
        "type_distribution": poi_df['type'].value_counts().to_dict()
    })

@app.get("/api/stats/provinces")
def get_province_stats(auth: dict = Depends(verify_auth)):
    """获取各省份 POI 数量统计"""
    stats = poi_df.groupby('province').size().sort_values(ascending=False).to_dict()
    return api_response(200, BizCode.SUCCESS, "省份统计", {
        "total_provinces": len(stats),
        "distribution": stats
    })

@app.get("/api/stats/types")
def get_type_stats(auth: dict = Depends(verify_auth)):
    """获取各类型 POI 数量统计"""
    stats = poi_df['type'].value_counts().to_dict()
    return api_response(200, BizCode.SUCCESS, "类型统计", {
        "total_types": len(stats),
        "distribution": stats
    })

@app.get("/api/stats/batches")
def get_batch_stats(auth: dict = Depends(verify_auth)):
    """获取各批次 POI 数量统计"""
    stats = poi_df['batch'].value_counts().to_dict()
    return api_response(200, BizCode.SUCCESS, "批次统计", {
        "total_batches": len(stats),
        "distribution": stats
    })

# ==================== 启动 ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
