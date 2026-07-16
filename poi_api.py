import psycopg2
import psycopg2.extras
import jwt
import os
import json
import redis
import logging
from fastapi import FastAPI,HTTPException,Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import datetime,timedelta
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from psycopg2 import pool

app=FastAPI()
pwd_context=CryptContext(schemes=["bcrypt"])
security=HTTPBearer()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

load_dotenv()

DB_PASSWORD=os.getenv("DB_PASSWORD")
SECRET_KEY=os.getenv("SECRET_KEY")
REDIS_HOST=os.getenv("REDIS_HOST","localhost")
PG_HOST=os.getenv("PG_HOST","localhost")
ALGORITHM="HS256"

r=redis.Redis(host=REDIS_HOST,port=6379,decode_responses=True)

#连接池
pg_pool=pool.ThreadedConnectionPool(minconn=1,maxconn=10,
host=PG_HOST,user="root",dbname="repoi_system",
cursor_factory=psycopg2.extras.RealDictCursor)

#CORS跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

#清除POI缓存
def clear_poi_cache():
    for key in r.scan_iter("pois:*"):
        r.delete(key)

#POI模型
class POIItem(BaseModel):
    name: str
    type: str
    age: str
    address: str
    batch: str
    lat: float
    lon: float
    remark: str

#用户注册模型
class UserRegister(BaseModel):
    username: str
    password: str

#用户登录模型
class UserLogin(BaseModel):
    username: str
    password: str

#连接数据库
def get_conn():
    return pg_pool.getconn()

#释放连接
def put_conn(conn):
    pg_pool.putconn(conn)

#公用Token验证
def get_current_user(credentials=Depends(security)):
    token=credentials.credentials
    try:
        payload=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401,detail="Token已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401,detail="Token无效")

#注册路由
@app.post("/register")
def register(user: UserRegister):
    conn=get_conn()
    try:
        hashed=pwd_context.hash(user.password)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO users(username,password_hash) VALUES(%s,%s)",(user.username,hashed))
        conn.commit()
        logging.info(f"新用户注册: {user.username}")
        return {"message": "注册成功"}
    except Exception as e:
        conn.rollback()
        if "Duplicate entry" in str(e):
            raise HTTPException(status_code=409,detail="用户名已存在")
        raise HTTPException(status_code=500,detail="服务器错误")
    finally:
        put_conn(conn)

#登录路由
@app.post("/login")
def  login(user: UserLogin):
    conn=get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username=%s",(user.username,))
            result=cursor.fetchone()
        if result is None:
            raise HTTPException(status_code=404,detail="USER NOT FOUND")
        if not pwd_context.verify(user.password,result["password_hash"]):
            raise HTTPException(status_code=401,detail="密码错误")
        data={
                "sub": user.username,
                "exp": datetime.now()+timedelta(hours=24)
        }
        token=jwt.encode(data,SECRET_KEY,algorithm=ALGORITHM)
        logging.info(f"用户登录: {user.username}")
        return {"access_token": token, "token_type": "bearer"}
    finally:
        put_conn(conn)

#查询点
@app.get("/pois")
def get_pois(
          keyword: str = None,
          type: str = None,
          batch: str = None,
          province: str = None,
          lat_min: float = None,
          lat_max: float = None,
          lon_min: float = None,
          lon_max: float = None,
          page: int = 1,
          page_size: int = 20,
          format: str = None,
          user=Depends(get_current_user)):
#组合redis
    cache_parts = []
    if type is not None:
        cache_parts.append(f"type={type}")
    if batch is not None:
        cache_parts.append(f"batch={batch}")
    if province is not None:
        cache_parts.append(f"prov={province}")
    if lat_min is not None:
        cache_parts.append(f"bbox={lat_min},{lat_max},{lon_min},{lon_max}")
    cache_parts.append(f"p={page}")
    cache_parts.append(f"ps={page_size}")
    cache_parts.append(f"fmt={format or 'none'}")
    cache_key = "pois:" + ":".join(cache_parts) if cache_parts else "pois:all"

# 查缓存
    if keyword is None:
        cached = r.get(cache_key)
        if cached:
            logging.info(f"redis查询POI: keyword={keyword}, type={type}, page={page}, format={format}")
            return json.loads(cached)
#分页
    offset = (page - 1) * page_size 
    try:
        conn=get_conn()
        with conn.cursor() as cursor:
            sql="SELECT * FROM pois WHERE 1=1"
            params=[]
            count_sql="SELECT COUNT(*) as total FROM pois WHERE 1=1"
            if keyword is not None:
                sql+=" AND (name LIKE %s OR address LIKE %s)"
                count_sql+=" AND (name LIKE %s OR address LIKE %s)"
                kw = f"%{keyword}%" 
                params.append(kw)
                params.append(kw)
            if type is not None:
                sql+=" AND type = %s"
                count_sql+=" AND type = %s"
                params.append(type)
            if batch is not None:
                sql+=" AND batch =%s"
                count_sql+=" AND batch =%s"
                params.append(batch)
            if province is not None:
                sql+=" AND address LIKE %s"
                count_sql+=" AND address LIKE %s"
                params.append(f"%{province}%")
            if lat_min is not None:
                sql+=" AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) "
#其他非点对象
                count_sql+=" AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) "
#其他非点对象双重精度判断
            #sql+=" AND ST_Intersects(geom,ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
            #count_sql+=" AND ST_Intersects(geom,ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
                params.append(lon_min)
                params.append(lat_min)
                params.append(lon_max)
                params.append(lat_max)
            count_params = params.copy() 
            sql += " LIMIT %s OFFSET %s"
            params.append(page_size)
            params.append(offset)
            cursor.execute(sql,params)
            items=cursor.fetchall()
            cursor.execute(count_sql, count_params)
            total = cursor.fetchone()["total"]
    finally:        
            put_conn(conn)
    response_data = {"total": total, "page": page, "page_size": page_size, "items": items}
    if format == "geojson":
        gjson = []
        for c in items:
            props = {"name": c["name"], "type": c["type"], "age": c["age"], "address": c["address"], "batch": c["batch"]}
            if c["remark"] is not None:
                props["remark"] = c["remark"]
            gjson.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": props
            })
        result = {"type": "FeatureCollection", "features": gjson}
    else:
        safe_keyword = (keyword or "").replace("\n", " ").replace("\r", " ")[:50]
        safe_type = (type or "")[:30]
        logging.info(f"POI查询: keyword={safe_keyword}, type={safe_type}, page={page}")
        result = response_data
    if keyword is None:
        r.set(cache_key, json.dumps(result), ex=3600)
    return result


#添加POI
@app.post("/pois",status_code=201)
def add_poi(poi: POIItem,user=Depends(get_current_user)):
    conn=get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO pois(name,type,age,address,batch,lat,lon,remark) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(poi.name,poi.type,poi.age,poi.address,poi.batch,poi.lat,poi.lon,poi.remark))
            conn.commit()
            clear_poi_cache()
            return {"message": "添加成功"}
    finally:
        put_conn(conn)


#更新poi
@app.put("/pois/{poi_id}")
def update_poi(poi_id: int,poi:POIItem,user=Depends(get_current_user)):
    conn=get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE pois SET name=%s,type=%s,age=%s,address=%s,batch=%s,lat=%s,lon=%s,remark=%s WHERE id=%s",(poi.name,poi.type,poi.age,poi.address,poi.batch,poi.lat,poi.lon,poi.remark,poi_id))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404,detail="POI NOT FOUND")
            conn.commit()
            clear_poi_cache()
            return {"message": "修改成功"}
    finally:
        put_conn(conn)

#删除POI
@app.delete("/pois/{poi_id}")
def delete_poi(poi_id: int,user=Depends(get_current_user)):
    conn=get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM pois WHERE id=%s",(poi_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404,detail="POI NOT FOUND")
            conn.commit()
            clear_poi_cache()
            return {"message": "删除成功"}
    finally:
        put_conn(conn)

#统计
@app.get("/stats/{group}")
def get_stats(group: str,user=Depends(get_current_user)):
    valid={"province": "address", "type": "type", "batch": "batch"}
    if group not in valid:
        raise HTTPException(400)
    field=valid[group]
    conn=get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {field} as name,COUNT(*) as count FROM pois GROUP BY {field} ORDER BY count DESC")
            result=cursor.fetchall()
            return result
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))
    finally:
            put_conn(conn)

#半径查询
@app.get("/pois/radius")
def radius_get(
    lon: float,
    lat: float,
    radius: float,
    page: int = 1,
    page_size: int = 20,
    format: str = None,
    user= Depends(get_current_user)):
    #半径判断
    if radius <= 0 or radius > 200000:
        raise HTTPException(status_code=400, detail="半径需在 1-200000 米之间")
    #分页
    offset = (page - 1) * page_size

    conn=get_conn()
    pgsql="SELECT * FROM pois WHERE ST_DWithin(geom::geography,ST_SetSRID(ST_MakePoint(%s, %s),4326)::geography,%s) LIMIT %s OFFSET %s"
    count_pgsql="SELECT COUNT(*) as total FROM pois WHERE ST_DWithin(geom::geography,ST_SetSRID(ST_MakePoint(%s, %s),4326)::geography,%s)"
    try:
        with conn.cursor() as cursor:
            cursor.execute(pgsql,(lon, lat, radius, page_size, offset))
            items=cursor.fetchall()
            cursor.execute(count_pgsql,(lon, lat, radius))
            total=cursor.fetchone()["total"]
            response_data = {"total": total, "page": page, "page_size": page_size, "items": items}
        gjson=[]
        if format == "geojson":
            for c in items:
                props = {"name": c["name"], "type": c["type"], "age": c["age"], "address": c["address"], "batch": c["batch"]}
                if c["remark"] is not None:
                    props["remark"] = c["remark"]
                gjson.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": props
            })
            return {"type": "FeatureCollection", "features": gjson}
        return response_data
    finally:
        put_conn(conn)

#叠加分析查省份
# @app.get("/pois/byprovince")
# def byprovince(name: str, page: int = 1, page_size: int =20, format: str =None, user=Depends(get_current_user)):
#     cache_parts = []
#     cache_parts.append(f"prov={name}")
#     cache_parts.append(f"fmt={format or 'none'}")
#     cache_parts.append(f"p={page}")
#     cache_parts.append(f"ps={page_size}")
#     cache_pro="pois:"+ ":".join(cache_parts) if cache_parts else "pois:all"
#     cached=r.get(cache_pro)
#     if cached:
#         logging.info(f"redis查询POI: province={name}, page={page}, format={format}")
#         return json.loads(cached)
#     offset=(page-1) * page_size
#     sql="SELECT * FROM pois WHERE ST_Contains( (SELECT ST_Union(geom_4326) FROM provinces WHERE name LIKE %s), pois.geom) LIMIT %s OFFSET %s "
#     name=f"%{name}%"
#     count_sql="SELECT COUNT(*) as total FROM pois WHERE ST_Contains( (SELECT ST_Union(geom_4326) FROM provinces WHERE name LIKE %s), pois.geom) "
#     try:
#         conn=get_conn()
#         with conn.cursor() as cursor:
#             cursor.execute(sql,(name,page_size, offset))
#             items=cursor.fetchall()
#             cursor.execute(count_sql,(name,))
#             total=cursor.fetchone()["total"]
#     finally:
#         put_conn(conn)
#     response_data = {"total": total, "page": page, "page_size": page_size, "items": items}
#     gjson=[]
#     if format == "geojson":
#         for c in items:
#             props = {"name": c["name"], "type": c["type"], "age": c["age"], "address": c["address"], "batch": c["batch"]}
#             if c["remark"] is not None:
#                 props["remark"] = c["remark"]
#             gjson.append({
#             "type": "Feature",
#             "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
#             "properties": props
#         })
#         result= {"type": "FeatureCollection", "features": gjson}
#     else:
#         result = response_data
#     logging.info(f"redis查询POI: province={name}, page={page}, format={format}")
#     r.set(cache_pro,json.dumps(result),ex=3600)
#     return result

#缓冲区分析
@app.get("/pois/{poi_id}/buffer")
def buffer(poi_id: int, radius: float, page: int =1, page_size: int =20, format: str = None, user=Depends(get_current_user)):
    if radius<0 or radius>200000:
        raise HTTPException(status_code=400, detail="半径需在 1-200000 米之间")
    offset=(page-1) * page_size
    sql="SELECT * FROM pois WHERE ST_Contains((SELECT ST_Buffer(geom::geography, %s)::geometry FROM pois WHERE id =%s),pois.geom) AND pois.id !=%s  LIMIT %s OFFSET %s   "
    count_sql="SELECT COUNT(*) as total FROM pois WHERE ST_Contains((SELECT ST_Buffer(geom::geography, %s)::geometry FROM pois WHERE id =%s),pois.geom) AND pois.id !=%s "
    try:
        conn=get_conn()
        with conn.cursor() as cursor:
            cursor.execute(sql,(radius, poi_id, poi_id, page_size, offset))
            items=cursor.fetchall()
            cursor.execute(count_sql,(radius, poi_id, poi_id))
            total=cursor.fetchone()["total"]
            cursor.execute("SELECT ST_Area(ST_Buffer(geom::geography, %s)) / 10000 AS area_ha FROM pois WHERE id =%s",(radius,poi_id))
            area_ha=cursor.fetchone()["area_ha"]
            cursor.execute("SELECT ST_AsGeoJSON(ST_Buffer(geom::geography, %s)) AS buffer_geojson FROM pois WHERE id =%s",(radius,poi_id))
            buffer_geojson=json.loads(cursor.fetchone()["buffer_geojson"])
    finally:
        put_conn(conn)
    response_data = {"total": total, "page": page, "page_size": page_size, "items": items, "area": area_ha}
    gjson=[]
    if format == "geojson":
        for c in items:
            props = {"name": c["name"], "type": c["type"], "age": c["age"], "address": c["address"], "batch": c["batch"]}
            if c["remark"] is not None:
                props["remark"] = c["remark"]
            gjson.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
            "properties": props
        })
        result = {"type": "FeatureCollection", "total": total, "page": page, "page_size": page_size, "buffer_area_ha": round(area_ha, 2), "buffer_geometry": buffer_geojson,"features": gjson}
    else:
        result = response_data
    return result
