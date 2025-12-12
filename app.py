import os
import math
import json
import requests
from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from routes.blacklist_api import blacklist_api

# 從 .env 文件中載入環境變數
load_dotenv()

# 初始化 Flask 應用程式
app = Flask(__name__)
CORS(app)

# 載入黑名單 API
app.register_blueprint(blacklist_api, url_prefix="/api")

# 設定 OpenAI API 金鑰
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 從環境變數中讀取 Google Places API 金鑰
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")



# --------------------- 與地理位置相關的函式 ---------------------
def get_location_coordinates(place_name):
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": place_name,
        "inputtype": "textquery",
        "fields": "geometry",
        "key": GOOGLE_PLACES_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data.get("candidates"):
        location = data["candidates"][0]["geometry"]["location"]
        return {"latitude": location["lat"], "longitude": location["lng"]}
    else:
        return None

def get_multiple_locations(place_names):
    features = []
    for name in place_names:
        coordinates = get_location_coordinates(name)
        if coordinates:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [coordinates["longitude"], coordinates["latitude"]]
                },
                "properties": {
                    "name": name
                }
            }
            features.append(feature)
    if features:
        return {
            "type": "FeatureCollection",
            "features": features
        }
    else:
        return None

def 建立_buffer_polygon(lon, lat, radius_km, num_points=64):
    points = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        delta_lat = (radius_km / 111.32) * math.sin(angle)
        denom = 111.32 * math.cos(math.radians(lat))
        delta_lon = (radius_km / denom) * math.cos(angle) if abs(denom) >= 1e-6 else 0
        points.append([lon + delta_lon, lat + delta_lat])
    points.append(points[0])
    return points

def get_buffer_polygon(place_name, radius_km):
    """
    取得以指定地點為中心且半徑為 radius_km 公里的圓形（buffer），
    同時回傳中心點位置，最終回傳的 GeoJSON 包含兩個 feature:
      - type 為 "Polygon" 的 buffer 圓
      - type 為 "Point" 的中心點
    """
    center = get_location_coordinates(place_name)
    if not center:
        return None
    lon = center["longitude"]
    lat = center["latitude"]
    polygon = 建立_buffer_polygon(lon, lat, radius_km)
    features = []
    polygon_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [polygon]
        },
        "properties": {
            "name": place_name,
            "radius_km": radius_km,
            "feature_type": "buffer"
        }
    }
    point_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat]
        },
        "properties": {
            "name": place_name,
            "feature_type": "center"
        }
    }
    features.append(polygon_feature)
    features.append(point_feature)
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    return geojson

def get_multiple_buffer_polygons(locations):
    """
    參數 locations 為列表，每個項目格式例如：
      {"place_name": "三芝雷達站", "radius_km": 10}
    回傳的 GeoJSON 會包含每個地點的 buffer 圓以及中心點資訊
    """
    features = []
    for loc in locations:
        coordinates = get_location_coordinates(loc["place_name"])
        if coordinates:
            lon = coordinates["longitude"]
            lat = coordinates["latitude"]
            polygon = 建立_buffer_polygon(lon, lat, loc["radius_km"])
            polygon_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [polygon]
                },
                "properties": {
                    "name": loc["place_name"],
                    "radius_km": loc["radius_km"],
                    "feature_type": "buffer"
                }
            }
            point_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "properties": {
                    "name": loc["place_name"],
                    "feature_type": "center"
                }
            }
            features.append(polygon_feature)
            features.append(point_feature)
    if features:
        return {
            "type": "FeatureCollection",
            "features": features
        }
    else:
        return None


### NEW ###  多點→Polygon
def get_polygon_from_coordinates(coordinates):
    """
    依序將多個 {'latitude': xx, 'longitude': xx} 連線成 GeoJSON Polygon。
    至少需 3 點；未滿 3 點回傳 None。
    """
    if not isinstance(coordinates, list) or len(coordinates) < 3:
        return None

    # 轉成 [lon, lat]，並將首點加入末端閉合
    ring = [[pt["longitude"], pt["latitude"]] for pt in coordinates]
    ring.append(ring[0])

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"feature_type": "polygon_from_points"}
            }
        ]
    }


def load_geojson(geojson_data):
    """
    驗證並載入 GeoJSON 資料。
    參數 geojson_data 為 dict 或 JSON 字串，包含 type、features 等欄位。
    若驗證成功則回傳該 GeoJSON，否則回傳 None。
    """
    try:
        # 若輸入為字串，先轉換成 dict
        if isinstance(geojson_data, str):
            data = json.loads(geojson_data)
        else:
            data = geojson_data

        # 驗證基本結構
        if not isinstance(data, dict):
            return {"error": "GeoJSON 必須是 dict 或有效的 JSON 字串"}

        if data.get("type") not in ["FeatureCollection", "Feature", "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"]:
            return {"error": "GeoJSON type 無效"}

        if "features" in data and not isinstance(data["features"], list):
            return {"error": "features 必須是陣列"}

        # 驗證通過，回傳該 GeoJSON
        return {"status": "success", "data": data}

    except json.JSONDecodeError:
        return {"error": "GeoJSON 格式錯誤，無法解析 JSON"}
    except Exception as ex:
        return {"error": f"載入 GeoJSON 時發生錯誤: {str(ex)}"}


# --------------------- 方位角與距離相關的函式 ---------------------

# 地球半徑（公里）
EARTH_RADIUS_KM = 6371.0
# 海里與公里的轉換係數
KM_TO_NM = 0.539957  # 1 海里 ≈ 1.852 公里，反向轉換

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    使用 Haversine 公式計算兩點間的大圓距離
    回傳: (distance_km, distance_nm)
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    distance_km = EARTH_RADIUS_KM * c
    distance_nm = distance_km * KM_TO_NM
    
    return distance_km, distance_nm


def calculate_bearing(lat1, lon1, lat2, lon2):
    """
    計算從點1到點2的方位角（0-360度，0=北，90=東，180=南，270=西）
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    
    y = math.sin(dlon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    
    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)
    bearing_deg = (bearing_deg + 360) % 360
    
    return bearing_deg


def destination_point(lat, lon, bearing_deg, distance_km):
    """
    根據起點、方位角和距離計算終點座標
    """
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    
    d = distance_km / EARTH_RADIUS_KM
    
    lat2_rad = math.asin(
        math.sin(lat_rad) * math.cos(d) + 
        math.cos(lat_rad) * math.sin(d) * math.cos(bearing_rad)
    )
    
    lon2_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(d) * math.cos(lat_rad),
        math.cos(d) - math.sin(lat_rad) * math.sin(lat2_rad)
    )
    
    lat2 = math.degrees(lat2_rad)
    lon2 = math.degrees(lon2_rad)
    
    return {"latitude": lat2, "longitude": lon2}


def calculate_point_by_bearing_distance(origin_place, bearing_degrees, distance_km):
    """
    從指定地名按給定方位角和距離計算新座標，回傳目標點的經緯度及 GeoJSON
    """
    origin = get_location_coordinates(origin_place)
    if not origin:
        return {"error": f"無法找到地點: {origin_place}"}
    
    dest = destination_point(origin["latitude"], origin["longitude"], bearing_degrees, distance_km)
    
    features = []
    
    # 起點
    origin_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [origin["longitude"], origin["latitude"]]
        },
        "properties": {
            "name": origin_place,
            "feature_type": "origin"
        }
    }
    
    # 終點
    dest_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [dest["longitude"], dest["latitude"]]
        },
        "properties": {
            "name": f"{origin_place}東北方{bearing_degrees}°、{distance_km}km",
            "feature_type": "destination"
        }
    }
    
    # 方位線
    line_feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [origin["longitude"], origin["latitude"]],
                [dest["longitude"], dest["latitude"]]
            ]
        },
        "properties": {
            "name": "方位線",
            "feature_type": "bearing_line",
            "bearing_degrees": bearing_degrees,
            "distance_km": distance_km,
            "distance_nm": distance_km * KM_TO_NM,
            "origin": origin_place
        }
    }
    
    features.extend([origin_feature, dest_feature, line_feature])
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


def calculate_bearing_distance_between_points(origin_place, destination_place):
    """
    計算兩個地點之間的方位角、公里距離和海里距離
    """
    origin = get_location_coordinates(origin_place)
    destination = get_location_coordinates(destination_place)
    
    if not origin:
        return {"error": f"無法找到起點: {origin_place}"}
    if not destination:
        return {"error": f"無法找到終點: {destination_place}"}
    
    bearing = calculate_bearing(
        origin["latitude"], origin["longitude"],
        destination["latitude"], destination["longitude"]
    )
    distance_km, distance_nm = haversine_distance(
        origin["latitude"], origin["longitude"],
        destination["latitude"], destination["longitude"]
    )
    
    features = []
    
    # 起點
    origin_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [origin["longitude"], origin["latitude"]]
        },
        "properties": {
            "name": origin_place,
            "feature_type": "origin"
        }
    }
    
    # 終點
    dest_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [destination["longitude"], destination["latitude"]]
        },
        "properties": {
            "name": destination_place,
            "feature_type": "destination"
        }
    }
    
    # 方位線
    line_feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [origin["longitude"], origin["latitude"]],
                [destination["longitude"], destination["latitude"]]
            ]
        },
        "properties": {
            "name": "方位線",
            "feature_type": "bearing_line",
            "bearing_degrees": bearing,
            "distance_km": distance_km,
            "distance_nm": distance_nm,
            "origin": origin_place,
            "destination": destination_place
        }
    }
    
    features.extend([origin_feature, dest_feature, line_feature])
    
    return {
        "type": "FeatureCollection",
        "features": features,
        "bearing_degrees": bearing,
        "distance_km": distance_km,
        "distance_nm": distance_nm
    }


def get_line_from_bearing_distance(origin_place, bearing_degrees, distance_km):
    """
    從指定起點按方位角和距離繪製方位線，回傳 GeoJSON（包含起點、終點和連接線）
    """
    return calculate_point_by_bearing_distance(origin_place, bearing_degrees, distance_km)


def calculate_multiple_bearings(origin_place, target_places):
    """
    從一個起點地名計算到多個目標地名的方位角和距離，回傳 GeoJSON 包含所有方位線
    """
    origin = get_location_coordinates(origin_place)
    if not origin:
        return {"error": f"無法找到起點: {origin_place}"}
    
    features = []
    
    # 添加起點
    origin_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [origin["longitude"], origin["latitude"]]
        },
        "properties": {
            "name": origin_place,
            "feature_type": "origin"
        }
    }
    features.append(origin_feature)
    
    # 計算到每個目標的方位和距離
    for target_place in target_places:
        destination = get_location_coordinates(target_place)
        if not destination:
            continue
        
        bearing = calculate_bearing(
            origin["latitude"], origin["longitude"],
            destination["latitude"], destination["longitude"]
        )
        distance_km, distance_nm = haversine_distance(
            origin["latitude"], origin["longitude"],
            destination["latitude"], destination["longitude"]
        )
        
        # 目標點
        target_feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [destination["longitude"], destination["latitude"]]
            },
            "properties": {
                "name": target_place,
                "feature_type": "target",
                "bearing_degrees": bearing,
                "distance_km": distance_km,
                "distance_nm": distance_nm
            }
        }
        features.append(target_feature)
        
        # 方位線
        line_feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [origin["longitude"], origin["latitude"]],
                    [destination["longitude"], destination["latitude"]]
                ]
            },
            "properties": {
                "name": f"到{target_place}的方位線",
                "feature_type": "bearing_line",
                "bearing_degrees": bearing,
                "distance_km": distance_km,
                "distance_nm": distance_nm,
                "origin": origin_place,
                "destination": target_place
            }
        }
        features.append(line_feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


def find_points_in_bearing_range(origin_place, bearing_start, bearing_end, max_distance_km, target_places=None):
    """
    在指定的方位角範圍和距離內找出扇形區域，並可選地查找該區域內的目標點
    """
    origin = get_location_coordinates(origin_place)
    if not origin:
        return {"error": f"無法找到起點: {origin_place}"}
    
    # 生成扇形區域的邊界點
    num_sector_points = 32
    sector_points = []
    
    # 添加起點
    sector_points.append([origin["longitude"], origin["latitude"]])
    
    # 從起始方位角到終止方位角的圓弧
    bearing_diff = (bearing_end - bearing_start) % 360
    if bearing_diff == 0:
        bearing_diff = 360
    
    for i in range(num_sector_points + 1):
        angle = bearing_start + (bearing_diff * i / num_sector_points)
        point = destination_point(origin["latitude"], origin["longitude"], angle, max_distance_km)
        sector_points.append([point["longitude"], point["latitude"]])
    
    # 回到起點完成多邊形
    sector_points.append([origin["longitude"], origin["latitude"]])
    
    features = []
    
    # 起點
    origin_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [origin["longitude"], origin["latitude"]]
        },
        "properties": {
            "name": origin_place,
            "feature_type": "origin"
        }
    }
    features.append(origin_feature)
    
    # 扇形區域
    sector_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [sector_points]
        },
        "properties": {
            "name": f"扇形範圍({bearing_start}°-{bearing_end}°, {max_distance_km}km)",
            "feature_type": "bearing_sector",
            "bearing_start": bearing_start,
            "bearing_end": bearing_end,
            "max_distance_km": max_distance_km,
            "origin": origin_place
        }
    }
    features.append(sector_feature)
    
    # 查找目標點（如果提供了）
    if target_places:
        for target_place in target_places:
            destination = get_location_coordinates(target_place)
            if not destination:
                continue
            
            bearing = calculate_bearing(
                origin["latitude"], origin["longitude"],
                destination["latitude"], destination["longitude"]
            )
            distance_km, distance_nm = haversine_distance(
                origin["latitude"], origin["longitude"],
                destination["latitude"], destination["longitude"]
            )
            
            # 檢查是否在扇形範圍內
            bearing_in_range = (bearing_start <= bearing <= bearing_end) or \
                             ((bearing_start > bearing_end) and (bearing >= bearing_start or bearing <= bearing_end))
            distance_ok = distance_km <= max_distance_km
            
            if bearing_in_range and distance_ok:
                target_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [destination["longitude"], destination["latitude"]]
                    },
                    "properties": {
                        "name": target_place,
                        "feature_type": "target_in_range",
                        "bearing_degrees": bearing,
                        "distance_km": distance_km,
                        "distance_nm": distance_nm
                    }
                }
                features.append(target_feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }




# --------------------- 結束地理位置相關的函式 ---------------------

# 定義靜態文件的目錄路徑
FOLDER_PATH = os.path.join(os.getcwd(), 'static')

@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def serve_file(filename):
    if filename.endswith(".js"):
        return send_from_directory(FOLDER_PATH, filename, mimetype='application/javascript')
    if filename.endswith(".css"):
        return send_from_directory(FOLDER_PATH, filename, mimetype='text/css')
    return send_from_directory(FOLDER_PATH, filename)


@app.route('/generate', methods=['POST'])
def generate_text():
    try:
        data = request.get_json()
        user_message = (data.get('prompt') or '').strip()
        if not user_message:
            return jsonify({'error': '訊息為必填'}), 400

        # ========= 1. system prompt：自然語言 + 不亂露座標 =========
        system_prompt = '''
你是個情報分析師，會使用繁體中文回覆。

請嚴格遵守以下規則：
1. 先用自然語言以繁體中文完整回答使用者問題（第一部分），
   說明地點的大致位置、所屬城市/區域、附近海域或地理背景等。
2. 除非使用者在問題中「明確」要求經緯度或座標
   （例如出現「經緯度」、「座標」、「latitude」、「longitude」等字眼），
   否則你在自然語言回答中「不要」寫出任何數字形式的座標
   （例如 25.03, 121.56 這種）。
3. 若問題與地點、地區、景點或範圍有關，且你有透過工具取得座標或 GeoJSON，
   請在回答的最後另外加上一段 GeoJSON 區塊，格式固定如下：

   geojson ```
   {
     "type": "FeatureCollection",
     "features": [
       {
         "type": "Feature",
         "geometry": { "type": "Point", "coordinates": [121.565, 25.033] },
         "properties": { "name": "台北101", "feature_type": "point" }
       },
       {
         "type": "Feature",
         "geometry": { "type": "LineString", "coordinates": [[121.565, 25.033], [121.4440921, 25.168927]] },
         "properties": { "name": "台北到淡水", "feature_type": "line" }
       },
       {
         "type": "Feature",
         "geometry": { "type": "Polygon", "coordinates": [[[121.565, 25.033], [121.4440921, 25.168927], [121.6, 25.1], [121.565, 25.033]]] },
         "properties": { "name": "目標區域", "feature_type": "polygon" }
       }
     ]
   }

4. 當使用者提到方向和距離時（例如「東北方 100 海浬」、「南西方 50 公里」），
   請使用方位角計算工具來找出確切位置。方向詞彙對應關係：
   - 北 = 0°, 北東 = 45°, 東 = 90°, 南東 = 135°
   - 南 = 180°, 南西 = 225°, 西 = 270°, 北西 = 315°
   - 東北方 ≈ 45°, 東南方 ≈ 135°, 西南方 ≈ 225°, 西北方 ≈ 315°
   記住：1 海浬 ≈ 1.852 公里，計算時需要轉換單位。
'''.strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # ========= 2. tools 定義 =========
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_location_coordinates",
                    "description": "取得單一指定地名的經緯度",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "place_name": {
                                "type": "string",
                                "description": "例如 '台北101'"
                            }
                        },
                        "required": ["place_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_buffer_polygon",
                    "description": "取得以指定地名為中心，並以指定半徑（公里）劃出的 buffer 圓（GeoJSON 格式），同時回傳中心點",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "place_name": {
                                "type": "string",
                                "description": "例如 '台北101'"
                            },
                            "radius_km": {
                                "type": "number",
                                "description": "例如 2"
                            }
                        },
                        "required": ["place_name", "radius_km"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_multiple_locations",
                    "description": "取得多個地名的經緯度，並以 GeoJSON 陣列格式回傳",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "place_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "例如 ['台北101', '淡水老街']"
                            }
                        },
                        "required": ["place_names"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_multiple_buffer_polygons",
                    "description": "取得多個地名，以各自指定半徑劃出 buffer 圓（GeoJSON 格式），並同時回傳中心點",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "locations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "place_name": {
                                            "type": "string",
                                            "description": "例如 '三芝雷達站'"
                                        },
                                        "radius_km": {
                                            "type": "number",
                                            "description": "例如 10"
                                        }
                                    },
                                    "required": ["place_name", "radius_km"]
                                },
                                "description": "例如 [{'place_name': '三芝雷達站', 'radius_km': 10}, {'place_name': '淡水漁人碼頭', 'radius_km': 10}]"
                            }
                        },
                        "required": ["locations"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_polygon_from_coordinates",
                    "description": "將多個經緯度點依順序連線為 GeoJSON Polygon",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "coordinates": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "latitude":  {"type": "number"},
                                        "longitude": {"type": "number"}
                                    },
                                    "required": ["latitude", "longitude"]
                                },
                                "description": "按照連線順序排列的座標列表"
                            }
                        },
                        "required": ["coordinates"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "load_geojson",
                    "description": "驗證並載入 GeoJSON 資料（支援點、線、面等多種圖徵）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "geojson_data": {
                                "type": "string",
                                "description": "GeoJSON 格式的字串或 JSON 物件，例如包含 Point、LineString、Polygon 等圖徵"
                            }
                        },
                        "required": ["geojson_data"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_point_by_bearing_distance",
                    "description": "從指定地名按給定方位角和距離計算新座標並生成方位線的 GeoJSON",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin_place": {
                                "type": "string",
                                "description": "起點地名，例如 '台北港'"
                            },
                            "bearing_degrees": {
                                "type": "number",
                                "description": "方位角（0-360度，0=北，90=東，180=南，270=西）"
                            },
                            "distance_km": {
                                "type": "number",
                                "description": "距離，單位公里。注意：若使用者提供的是海浬，請轉換（1海浬≈1.852公里）"
                            }
                        },
                        "required": ["origin_place", "bearing_degrees", "distance_km"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_bearing_distance_between_points",
                    "description": "計算兩個地點之間的方位角、公里距離和海里距離，並繪製方位線",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin_place": {
                                "type": "string",
                                "description": "起點地名"
                            },
                            "destination_place": {
                                "type": "string",
                                "description": "終點地名"
                            }
                        },
                        "required": ["origin_place", "destination_place"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_line_from_bearing_distance",
                    "description": "從指定起點按方位角和距離繪製方位線，回傳 GeoJSON（包含起點、終點和連接線）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin_place": {
                                "type": "string",
                                "description": "起點地名"
                            },
                            "bearing_degrees": {
                                "type": "number",
                                "description": "方位角（度）"
                            },
                            "distance_km": {
                                "type": "number",
                                "description": "距離（公里）"
                            }
                        },
                        "required": ["origin_place", "bearing_degrees", "distance_km"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_multiple_bearings",
                    "description": "從一個起點地名計算到多個目標地名的方位角和距離，回傳 GeoJSON 包含所有方位線",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin_place": {
                                "type": "string",
                                "description": "起點地名"
                            },
                            "target_places": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "目標地名列表，例如 ['淡水', '基隆', '宜蘭']"
                            }
                        },
                        "required": ["origin_place", "target_places"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_points_in_bearing_range",
                    "description": "在指定的方位角範圍和距離內生成扇形區域，並可選地查找該區域內的目標點",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin_place": {
                                "type": "string",
                                "description": "起點地名"
                            },
                            "bearing_start": {
                                "type": "number",
                                "description": "起始方位角（度）"
                            },
                            "bearing_end": {
                                "type": "number",
                                "description": "終止方位角（度）"
                            },
                            "max_distance_km": {
                                "type": "number",
                                "description": "扇形最大距離（公里）"
                            },
                            "target_places": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "可選，要查找的目標地點列表"
                            }
                        },
                        "required": ["origin_place", "bearing_start", "bearing_end", "max_distance_km"]
                    }
                }
            }
        ]

        # ========= 3. 第一次呼叫：讓模型決定要不要用 tools =========
        first_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        assistant_message = first_response.choices[0].message

        # ========= 4. 若沒有 tool_calls，就直接回傳自然語言 =========
        if not getattr(assistant_message, "tool_calls", None):
            return jsonify({'response': assistant_message.content}), 200

        # ========= 5. 有 tool_calls：實際執行 Python 函式 =========

        # 把這次 assistant（帶 tool_calls）加回 messages
        messages.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ],
        })

        # 逐一跑每個 tool_call，呼叫你在後端定義的函式
        for tc in assistant_message.tool_calls:
            fn_name = tc.function.name
            raw_args = tc.function.arguments or "{}"

            try:
                arguments = json.loads(raw_args)
            except Exception as ex:
                tool_result = {"error": f"解析函式參數失敗: {str(ex)}"}
            else:
                try:
                    if fn_name == "get_location_coordinates":
                        tool_result = get_location_coordinates(arguments["place_name"])
                    elif fn_name == "get_multiple_locations":
                        tool_result = get_multiple_locations(arguments["place_names"])
                    elif fn_name == "get_buffer_polygon":
                        radius = float(arguments["radius_km"])
                        tool_result = get_buffer_polygon(arguments["place_name"], radius)
                    elif fn_name == "get_multiple_buffer_polygons":
                        tool_result = get_multiple_buffer_polygons(arguments["locations"])
                    elif fn_name == "get_polygon_from_coordinates":
                        tool_result = get_polygon_from_coordinates(arguments["coordinates"])
                    elif fn_name == "load_geojson":
                        tool_result = load_geojson(arguments["geojson_data"])
                    elif fn_name == "calculate_point_by_bearing_distance":
                        bearing = float(arguments["bearing_degrees"])
                        distance = float(arguments["distance_km"])
                        tool_result = calculate_point_by_bearing_distance(arguments["origin_place"], bearing, distance)
                    elif fn_name == "calculate_bearing_distance_between_points":
                        tool_result = calculate_bearing_distance_between_points(arguments["origin_place"], arguments["destination_place"])
                    elif fn_name == "get_line_from_bearing_distance":
                        bearing = float(arguments["bearing_degrees"])
                        distance = float(arguments["distance_km"])
                        tool_result = get_line_from_bearing_distance(arguments["origin_place"], bearing, distance)
                    elif fn_name == "calculate_multiple_bearings":
                        tool_result = calculate_multiple_bearings(arguments["origin_place"], arguments["target_places"])
                    elif fn_name == "find_points_in_bearing_range":
                        bearing_start = float(arguments["bearing_start"])
                        bearing_end = float(arguments["bearing_end"])
                        max_dist = float(arguments["max_distance_km"])
                        target_places = arguments.get("target_places", None)
                        tool_result = find_points_in_bearing_range(arguments["origin_place"], bearing_start, bearing_end, max_dist, target_places)
                    else:
                        tool_result = {"error": f"未知的工具名稱: {fn_name}"}
                except Exception as ex:
                    tool_result = {"error": f"執行工具時發生錯誤: {str(ex)}"}

            # 把工具執行結果丟回模型，讓下一輪可以使用
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": fn_name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

        # ========= 6. 第二次呼叫：請模型根據工具結果產生「最終回答」 =========
        second_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages  # 不再帶 tools，避免無限迴圈
        )

        final_message = second_response.choices[0].message
        return jsonify({'response': final_message.content}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
