import psycopg2
import psycopg2.extras
import pandas as pd

df=pd.read_excel(r"C:\Users\Songyk\Desktop\课程作业\空信服务实习\实验3\data\全国文保单位.xlsx")
conn=psycopg2.connect(
     host="localhost",
     user="root",
     dbname="repoi_system",
     cursor_factory=psycopg2.extras.RealDictCursor
)


with conn.cursor() as cursor:
    for idx, row in df.iterrows():
        if pd.isna(row['remark']):
            remark = None
        else:
            remark=str(row['remark'])
        if pd.isna(row['bd_lon']):
            bd_lon = None
        else:
            bd_lon=float(row['bd_lon'])
        if pd.isna(row['bd_lat']):
            bd_lat = None
        else:
            bd_lat=float(row['bd_lat'])
        cursor.execute("INSERT INTO pois(code, classCode, name, age, address, type, batch, remark, bd_lon, bd_lat, lon, lat)VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",(str(row['code']), str(row['classCode']), str(row['name']), str(row['age']), str(row['add']), str(row['type']), str(row['batch']), remark, bd_lon, bd_lat, float(row['lon']), float(row['lat'])))

conn.commit()
conn.close()
print("over")