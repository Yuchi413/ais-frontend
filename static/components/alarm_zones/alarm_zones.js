/* ---------------------------------------------------------
   alarm_zones.js — 加入紅點通知 + CN 船列表版
---------------------------------------------------------- */

const viewer = window.CESIUM_VIEWER;
import { loadCSS, loadHTML, makePanelDraggable } from "../../utils.js";

loadCSS("components/alarm_zones/alarm_zones.css");

loadHTML(`
  <div id="alarmControlPanel">
    <div class="panel-header">
      <h3>警戒區設定</h3>
      <button id="toggleAlarmPanelBtn">-</button>
    </div>
    <div id="alarmContent">
      
      <div class="alarm-section">
        <div class="section-header">
          <span>🆕 新增警戒區</span>
          <div class="btn-row">
            <button id="addAlarmBtn">＋</button>
            <button id="saveAlarmBtn">💾</button>
            <button id="reloadAlarmBtn">🔄</button>
          </div>
        </div>
        <div class="section-body">
          <div class="sub-label">暫存繪製</div>
          <ul id="newAlarmList"></ul>
        </div>
      </div>

      <div class="divider"></div>

      <div class="alarm-section">
        <div class="section-header">
          <span>📂 資料庫</span>
        </div>
        <div class="section-body">
          <div class="sub-label">已儲存警戒區</div>
          <ul id="oldAlarmList"></ul>
        </div>
      </div>

    </div>
  </div>
`);

makePanelDraggable("alarmControlPanel", ".panel-header");

const alarmContent = document.getElementById("alarmContent");
const toggleAlarmPanelBtn = document.getElementById("toggleAlarmPanelBtn");
let alarmCollapsed = true;
alarmContent.style.display = "none";

toggleAlarmPanelBtn.addEventListener("click", () => {
  alarmCollapsed = !alarmCollapsed;
  alarmContent.style.display = alarmCollapsed ? "none" : "block";
  toggleAlarmPanelBtn.textContent = alarmCollapsed ? "+" : "-";
});

// === 全域變數 ===
let alarmZones = [];
let oldAlarms = [];
let newAlarms = [];
let previewPoints = [];
let previewPolygon = null;
let drawHandler = null;

// ⭐ 用來存放後端最新 CN ship 資料
let CN_ZONE_SHIPS = {}; // { zoneId: [ships...] }

// ⭐ 每 10 秒打 API
setInterval(fetchZoneShipStatus, 10000);

// -----------------------------------------------------------
// 🚀 從後端 API 抓取 CN 船在各區域的最新資料
// -----------------------------------------------------------
async function fetchZoneShipStatus() {
  try {
    const resp = await fetch("http://127.0.0.1:5000/api/custom_zone_cn");
    const json = await resp.json();

    if (json.status !== "success") {
      console.warn("⚠️ API 狀態錯誤:", json);
      return;
    }

    CN_ZONE_SHIPS = json.data;  
    updateAlarmBadges();

  } catch (err) {
    console.warn("⚠️ 無法取得警戒區船舶資料:", err);
  }
}


// -----------------------------------------------------------
// 🔴 更新紅點通知 + 展開的列表內容
// -----------------------------------------------------------
function updateAlarmBadges() {
  Object.keys(CN_ZONE_SHIPS).forEach(zoneId => {
    const listItem = document.querySelector(`#alarm-item-${zoneId}`);
    const badge = document.querySelector(`#alarm-badge-${zoneId}`);
    const detailBox = document.querySelector(`#alarm-detail-${zoneId}`);

    if (!listItem) return;

    const ships = CN_ZONE_SHIPS[zoneId];

    if (ships && ships.length > 0) {
      badge.style.display = "inline-block";
      detailBox.innerHTML = ships.map(s => `
        <div class="ship-item">
          🚢 ${s.shipname}<br>
          📍 ${s.lat}, ${s.lon}
        </div>
      `).join("");

    } else {
      badge.style.display = "none";
      detailBox.innerHTML = "";
    }
  });
}

// -----------------------------------------------------------
// 🚀 載入資料庫的警戒區（預設不顯示）
// -----------------------------------------------------------
window.addEventListener("DOMContentLoaded", loadAlarmZonesFromDB);
document.getElementById("reloadAlarmBtn").addEventListener("click", loadAlarmZonesFromDB);

async function loadAlarmZonesFromDB() {
  oldAlarms.forEach((z) => viewer.entities.remove(z.entity));

  alarmZones = [];
  oldAlarms = [];
  document.getElementById("oldAlarmList").innerHTML = "";

  try {
    const resp = await fetch("http://127.0.0.1:5000/api/alarm_zones");
    const geojson = await resp.json();

    if (geojson.features) {
      geojson.features.forEach((f) => {
        if (f.geometry?.type === "Polygon") {
          const coords = f.geometry.coordinates[0];
          const flat = coords.flat();
          const zoneId = f.properties.id;
          const id = "alarm-" + zoneId;
          const name = f.properties.name;

          const entity = viewer.entities.add({
            id,
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArray(flat),
              material: Cesium.Color.ORANGE.withAlpha(0.3),
              outline: true,
              outlineColor: Cesium.Color.ORANGE,
            },
            show: false
          });

          const zone = { id, zoneId, name, entity, coords };
          alarmZones.push(zone);
          oldAlarms.push(zone);

          addAlarmListItem("oldAlarmList", id, name, zoneId, false, false);
        }
      });
    }

    // 更新紅點
    updateAlarmBadges();

  } catch (err) {
    console.error("❌ 載入警戒區失敗:", err);
  }
}

// -----------------------------------------------------------
// ✏️ 新增警戒區（繪圖流程）
// -----------------------------------------------------------
document.getElementById("addAlarmBtn").addEventListener("click", () => {
  if (drawHandler) drawHandler.destroy();
  clearPreviewEntities();

  let drawPositions = [];

  alert("🟡 左鍵點選多邊形頂點，右鍵完成繪製（至少三個點）");

  drawHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

  // 左鍵畫點
  drawHandler.setInputAction((click) => {
    const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
    if (!cartesian) return;

    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const lon = Cesium.Math.toDegrees(carto.longitude);
    const lat = Cesium.Math.toDegrees(carto.latitude);

    drawPositions.push(lon, lat);

    const point = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      point: {
        pixelSize: 8,
        color: Cesium.Color.RED,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2
      },
    });
    previewPoints.push(point);

    // 即時多邊形視覺
    if (drawPositions.length >= 6) {
      const hierarchy = Cesium.Cartesian3.fromDegreesArray(drawPositions);

      if (!previewPolygon) {
        previewPolygon = viewer.entities.add({
          polygon: {
            hierarchy,
            material: Cesium.Color.YELLOW.withAlpha(0.3),
            outline: true,
            outlineColor: Cesium.Color.GOLD,
          },
        });
      } else {
        previewPolygon.polygon.hierarchy = hierarchy;
      }
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  // 右鍵完成
  drawHandler.setInputAction(() => {
    if (drawPositions.length < 6) {
      alert("❌ 至少需要三個點！");
      clearPreviewEntities();
      drawHandler.destroy();
      return;
    }

    drawPositions.push(drawPositions[0], drawPositions[1]);
    clearPreviewEntities();

    const name = prompt("請輸入警戒區名稱：", "新警戒區");
    if (!name) {
      drawHandler.destroy();
      return;
    }

    const id = "alarm-" + Date.now();
    const coords = [];

    for (let i = 0; i < drawPositions.length; i += 2) {
      coords.push([drawPositions[i], drawPositions[i + 1]]);
    }

    const entity = viewer.entities.add({
      id,
      polygon: {
        hierarchy: Cesium.Cartesian3.fromDegreesArray(drawPositions),
        material: Cesium.Color.LIME.withAlpha(0.3),
        outline: true,
        outlineColor: Cesium.Color.LIME,
      },
    });

    const zone = { id, name, coords, entity, isNew: true };
    alarmZones.push(zone);
    newAlarms.push(zone);

    addAlarmListItem("newAlarmList", id, name, null, true, true);

    drawHandler.destroy();
  }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);
});

// -------------------------------------------------------------
// 💾 儲存新警戒區
// -------------------------------------------------------------
document.getElementById("saveAlarmBtn").addEventListener("click", async () => {
  if (newAlarms.length === 0) {
    alert("目前沒有新警戒區！");
    return;
  }

  const features = newAlarms.map((zone) => ({
    type: "Feature",
    properties: { name: zone.name },
    geometry: { type: "Polygon", coordinates: [zone.coords] },
  }));

  try {
    const resp = await fetch("http://127.0.0.1:5000/api/alarm_zones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "FeatureCollection",
        features,
      }),
    });

    if (resp.ok) {
      alert("✅ 新警戒區已儲存！");
      await loadAlarmZonesFromDB();

      newAlarms.forEach((z) => viewer.entities.remove(z.entity));
      newAlarms = [];
      document.getElementById("newAlarmList").innerHTML = "";

    } else {
      alert("❌ 儲存失敗：" + (await resp.text()));
    }

  } catch (err) {
    alert("伺服器連線錯誤");
  }
});

// -------------------------------------------------------------
// 工具：清除暫存 Preview
// -------------------------------------------------------------
function clearPreviewEntities() {
  previewPoints.forEach((p) => viewer.entities.remove(p));
  previewPoints = [];
  if (previewPolygon) viewer.entities.remove(previewPolygon);
  previewPolygon = null;
}

// -------------------------------------------------------------
// 🟥 加入警戒區清單項目（含紅點 + 展開 CN 船列表）
// -------------------------------------------------------------
function addAlarmListItem(listId, id, name, dbId = null, isNew = false, defaultChecked = true) {
  const list = document.getElementById(listId);
  const li = document.createElement("li");
  li.id = `alarm-item-${dbId ?? id}`;
  li.className = "alarm-item";
  li.style.marginBottom = "6px";

  li.innerHTML = `
    <div class="alarm-header">
      <input type="checkbox" id="chk-${id}" ${defaultChecked ? "checked" : ""}>
      <label for="chk-${id}" class="alarm-name">${name}</label>
      <span class="alarm-badge" id="alarm-badge-${dbId}" style="
            display:none;
            width:10px;height:10px;
            background:red;border-radius:50%;
            margin-left:6px;"></span>
      <button id="del-${id}" class="alarm-del-btn">🗑️</button>
    </div>

    <div id="alarm-detail-${dbId}"
        class="alarm-detail-box"
        style="display:none; margin-left:22px; background:#f4f4f4; padding:5px; border-radius:5px;">
    </div>

  `;

  list.appendChild(li);

  const checkbox = li.querySelector(`#chk-${id}`);
  const detailBox = li.querySelector(`#alarm-detail-${dbId}`);
  const nameLabel = li.querySelector(".alarm-name");

  // 切換顯示多邊形
  checkbox.addEventListener("change", (e) => {
    const zone = alarmZones.find((z) => z.id === id);
    if (zone) zone.entity.show = e.target.checked;
  });

  // 點名稱 → 展開/收起 CN 船列表
  nameLabel.addEventListener("click", () => {
    detailBox.style.display = detailBox.style.display === "none" ? "block" : "none";
  });

  // 刪除
  document.getElementById(`del-${id}`).addEventListener("click", async () => {
    if (!confirm(`確定刪除 ${name}？`)) return;

    viewer.entities.removeById(id);
    alarmZones = alarmZones.filter((z) => z.id !== id);
    li.remove();

    // 刪除 DB 內的（非新建立的）
    if (!isNew && dbId) {
      try {
        const resp = await fetch(`http://127.0.0.1:5000/api/alarm_zones/${dbId}`, {
          method: "DELETE",
        });

        if (!resp.ok) throw new Error(await resp.text());
        console.log(`✅ 已刪除警戒區 ${dbId}`);

      } catch (err) {
        alert("刪除失敗：" + err);
      }
    } else if (isNew) {
      newAlarms = newAlarms.filter((z) => z.id !== id);
    }
  });
}

// -------------------------------------------------------------
// 🔥 初始化監聽並立即抓一次
// -------------------------------------------------------------
fetchZoneShipStatus();

