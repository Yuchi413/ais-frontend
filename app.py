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

def get_offset_point_from_place(place_name, direction, distance_nm):
    """
    從指定地點出發，依照方位與距離（海浬）計算偏移點，
    回傳一個 FeatureCollection：
      - 基準點（base_point）
      - 目標點（offset_point）
      - 兩點之間的 LineString（arrow_line）
    """
    base = get_location_coordinates(place_name)
    if not base:
        return None

    # 基準點座標
    lat = base["latitude"]
    lon = base["longitude"]

    # 海浬 → 公里
    distance_km = float(distance_nm) * 1.852

    # 方位對應角度（0 = 正東, π/2 = 正北）
    dir_map = {
        "東": 0.0, "正東": 0.0,
        "東北": math.pi / 4,
        "北": math.pi / 2, "正北": math.pi / 2,
        "西北": 3 * math.pi / 4,
        "西": math.pi, "正西": math.pi,
        "西南": 5 * math.pi / 4,
        "南": 3 * math.pi / 2, "正南": 3 * math.pi / 2,
        "東南": 7 * math.pi / 4,
    }

    angle = dir_map.get(direction)
    if angle is None:
        return None  # 模型給了奇怪方位就直接回 None

    # 跟你 buffer 一樣的近似算法
    delta_lat = (distance_km / 111.32) * math.sin(angle)
    denom = 111.32 * math.cos(math.radians(lat))
    delta_lon = (distance_km / denom) * math.cos(angle) if abs(denom) >= 1e-6 else 0.0

    lat2 = lat + delta_lat
    lon2 = lon + delta_lon

    target_name = f"{place_name}{direction}外海{distance_nm}海浬"

    features = [
        # 1) 基準點
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "name": place_name,
                "feature_type": "base_point"
            }
        },
        # 2) 目標偏移點
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon2, lat2]
            },
            "properties": {
                "name": target_name,
                "feature_type": "offset_point",
                "base_place": place_name,
                "direction": direction,
                "distance_nm": distance_nm
            }
        },
        # 3) 兩點之間的連線（之後前端改成箭頭）
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [lon, lat],
                    [lon2, lat2]
                ]
            },
            "properties": {
                "name": f"{place_name} → {target_name}",
                "feature_type": "arrow_line"
            }
        }
    ]

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
1. 先用自然語言完整回答使用者問題（第一部分），
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
         "properties": { "name": "台北101" }
       },
       {
         "type": "Feature",
         "geometry": { "type": "Point", "coordinates": [121.4440921, 25.168927] },
         "properties": { "name": "淡水老街" }
       }
     ]
   }

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
                    "name": "get_offset_point_from_place",
                    "description": "從基準地點、方位與距離（海浬）計算偏移位置，適用於「基隆港東北外海10海浬」這類描述。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "place_name": {
                                "type": "string",
                                "description": "基準地點名稱，例如 '基隆港'"
                            },
                            "direction": {
                                "type": "string",
                                "description": "方位，例如 '東北', '東南', '西北', '正東', '正北', '正南', '西南' 等"
                            },
                            "distance_nm": {
                                "type": "number",
                                "description": "距離（海浬），例如 10 表示 10 海浬"
                            }
                        },
                        "required": ["place_name", "direction", "distance_nm"]
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
                    elif fn_name == "get_offset_point_from_place":
                        tool_result = get_offset_point_from_place(
                            arguments["place_name"],
                            arguments["direction"],
                            arguments["distance_nm"],
                        )
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
