/* global Cesium */
const viewer = window.CESIUM_VIEWER;
import { loadCSS, loadHTML, makePanelDraggable } from "../../utils.js";

// =====================
//  載入 CSS + HTML（已移除 MMSI）
// =====================
loadCSS("components/blackname/blackname.css");

loadHTML(`
  <div id="blacknameControlPanel">
    <div class="panel-header">
      <h3>黑名單船舶</h3>
      <button id="toggleblacknamePanelBtn">-</button>
    </div>

    <div id="blacknameControlContent">
      
      <!-- 🆕 新增黑名單 -->
      <div class="blackname-section">
        <div class="section-header">
          <span>🆕 新增黑名單</span>
        </div>
        <div class="section-body">
          <label>船名（必填）：<br>
            <input type="text" id="bn-name" placeholder="例如：CHINACOASTGUARD 14603" style="width: 210px;">
          </label><br>
          <label>備註（選填）：<br>
            <input type="text" id="bn-note" placeholder="例如：海警常出沒金門" style="width: 210px;">
          </label><br>
          <button id="bn-addBtn">加入黑名單</button>
        </div>
      </div>

      <div class="divider"></div>

      <!-- 📂 黑名單列表 -->
      <div class="blackname-section">
        <div class="section-header">
          <span>📂 黑名單列表</span>
          <div class="btn-row">
            <button id="bn-refreshPosBtn">🔄 更新位置</button>
            <button id="bn-reloadListBtn">📥 重新載入</button>
          </div>
        </div>
        <div class="section-body">
          <div class="sub-label">勾選顯示在地圖上（淺藍點）</div>
          <ul id="bn-list"></ul>
        </div>
      </div>

    </div>
  </div>
`);

// 讓面板可拖曳
makePanelDraggable("blacknameControlPanel", ".panel-header");

// =====================
//  DOM 物件
// =====================
const blacknameControlContent = document.getElementById("blacknameControlContent");
const toggleblacknamePanelBtn = document.getElementById("toggleblacknamePanelBtn");

const bnNameInput  = document.getElementById("bn-name");
const bnNoteInput  = document.getElementById("bn-note");
const bnAddBtn     = document.getElementById("bn-addBtn");

const bnList       = document.getElementById("bn-list");
const bnRefreshPosBtn = document.getElementById("bn-refreshPosBtn");
const bnReloadListBtn = document.getElementById("bn-reloadListBtn");

// =====================
//  面板收合
// =====================
let isCollapsed = true;
blacknameControlContent.style.display = "none";

toggleblacknamePanelBtn.addEventListener("click", () => {
  isCollapsed = !isCollapsed;
  blacknameControlContent.style.display = isCollapsed ? "none" : "block";
  toggleblacknamePanelBtn.textContent = isCollapsed ? "+" : "-";
});

// =====================
//  設定常數 & 狀態
// =====================
const BLACKLIST_API = "http://127.0.0.1:5000/api/blacklist_ships";
const CHINA_LATEST_API = "http://127.0.0.1:5000/api/chinaboat/latest";

let blacklistItems = [];
let latestCNShips = [];
let latestFetchedTime = 0;

// =====================
//  抓最新 CN 船
// =====================
async function fetchLatestCNShips(force = false) {
  const now = Date.now();

  if (!force && now - latestFetchedTime < 60 * 1000 && latestCNShips.length > 0) return;

  try {
    const resp = await fetch(CHINA_LATEST_API);
    const json = await resp.json();
    latestCNShips = json.data || [];
    latestFetchedTime = now;
    console.log(`🛰 最新 CN 船舶資料: ${latestCNShips.length} 筆`);
  } catch (err) {
    console.error("❌ 取得最新 CN 船資料失敗：", err);
    alert("無法取得中國籍船舶最新位置，請檢查後端 /chinaboat/latest");
  }
}

// =====================
//  只用「船名」比對
// =====================
function findShipForItem(item) {
  if (!latestCNShips.length) return null;

  const targetName = (item.name || "").trim().toUpperCase();
  if (!targetName) return null;

  return latestCNShips.find(ship => {
    const shipName = (ship.shipname || "").trim().toUpperCase();
    return shipName === targetName;
  }) || null;
}

// =====================
//  建立淺藍點
// =====================
function createShipEntityForItem(item, ship) {
  if (!ship || isNaN(ship.lat) || isNaN(ship.lon)) return null;

  const position = Cesium.Cartesian3.fromDegrees(ship.lon, ship.lat);

  return viewer.entities.add({
    name: item.name,
    position,
    point: {
      pixelSize: 12,
      color: Cesium.Color.SKYBLUE.withAlpha(0.9),
      outlineColor: Cesium.Color.WHITE.withAlpha(0.9),
      outlineWidth: 2
    },
    label: {
      text: item.name,
      font: "14px sans-serif",
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(15, -15),
    },
    description: `
      <b>黑名單船舶</b><br>
      船名：${item.name}<br>
      備註：${item.note || "無"}<br>
      經緯度：${ship.lat.toFixed(5)}, ${ship.lon.toFixed(5)}<br>
      速度：${ship.speed ?? "未知"} 節<br>
      航向：${ship.course ?? "未知"}°<br>
      更新時間：${ship.timestamp}
    `
  });
}

function removeItemEntity(item) {
  if (item.entity) {
    viewer.entities.remove(item.entity);
    item.entity = null;
  }
}

// =====================
// 更新位置
// =====================
async function updateItemEntityPosition(item, flyTo = false) {
  await fetchLatestCNShips(false);

  const ship = findShipForItem(item);
  if (!ship) {
    alert(`查無「${item.name}」最新位置！`);
    removeItemEntity(item);
    return;
  }

  removeItemEntity(item);
  item.entity = createShipEntityForItem(item, ship);

  if (flyTo && item.entity) {
    viewer.flyTo(item.entity, { duration: 1.5 });
  }
}

// =====================
// UI：加入、刪除、列表
// =====================
function clearBlacklistListUI() {
  bnList.innerHTML = "";
}

function addBlacklistListItem(item) {
  const li = document.createElement("li");
  li.style.marginBottom = "4px";

  const checkboxId = `bn-chk-${item.id}`;
  const locateBtnId = `bn-loc-${item.id}`;
  const delBtnId = `bn-del-${item.id}`;

  li.innerHTML = `
    <input type="checkbox" id="${checkboxId}">
    <label for="${checkboxId}">
      ${item.name}
      ${item.note ? `<span style="color:#888;font-size:12px;">（${item.note}）</span>` : ""}
    </label>
    <button id="${locateBtnId}" style="margin-left:6px;">📍</button>
    <button id="${delBtnId}" style="margin-left:4px;">🗑️</button>
  `;

  bnList.appendChild(li);

  const chk = li.querySelector(`#${checkboxId}`);
  const locBtn = li.querySelector(`#${locateBtnId}`);
  const delBtn = li.querySelector(`#${delBtnId}`);

  chk.addEventListener("change", async () => {
    if (chk.checked) {
      await updateItemEntityPosition(item, false);
    } else {
      removeItemEntity(item);
    }
  });

  locBtn.addEventListener("click", async () => {
    chk.checked = true;
    await updateItemEntityPosition(item, true);
  });

  delBtn.addEventListener("click", async () => {
    if (!confirm(`確定移除「${item.name}」？`)) return;

    try {
      await fetch(`${BLACKLIST_API}/${item.id}`, { method: "DELETE" });
      removeItemEntity(item);
      li.remove();
      blacklistItems = blacklistItems.filter(x => x.id !== item.id);
    } catch (err) {
      alert("刪除失敗！");
    }
  });
}

// =====================
// 從 DB 載入黑名單
// =====================
async function loadBlacklistFromDB() {
  clearBlacklistListUI();
  blacklistItems.forEach(removeItemEntity);
  blacklistItems = [];

  const resp = await fetch(BLACKLIST_API);
  const json = await resp.json();

  const items = json.items || [];
  items.forEach(raw => {
    const item = {
      id: raw.id,
      name: raw.name,
      note: raw.note || "",
      entity: null
    };
    blacklistItems.push(item);
    addBlacklistListItem(item);
  });

  console.log(`📂 已載入黑名單 ${blacklistItems.length} 筆`);
}

// =====================
// 新增黑名單
// =====================
async function handleAddBlacklist() {
  const name = bnNameInput.value.trim();
  const note = bnNoteInput.value.trim();

  if (!name) {
    alert("船名必填！");
    return;
  }

  const payload = { name, note };

  const resp = await fetch(BLACKLIST_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const created = await resp.json();

  const item = {
    id: created.id,
    name,
    note,
    entity: null
  };

  blacklistItems.push(item);
  addBlacklistListItem(item);

  bnNameInput.value = "";
  bnNoteInput.value = "";

  alert("已加入黑名單！");
}

// =====================
// 事件
// =====================
bnAddBtn.addEventListener("click", handleAddBlacklist);
bnReloadListBtn.addEventListener("click", loadBlacklistFromDB);

bnRefreshPosBtn.addEventListener("click", async () => {
  await fetchLatestCNShips(true);

  const liNodes = Array.from(bnList.querySelectorAll("li"));
  for (const li of liNodes) {
    const chk = li.querySelector("input[type=checkbox]");
    if (!chk || !chk.checked) continue;

    const idStr = chk.id.replace("bn-chk-", "");
    const item = blacklistItems.find(x => String(x.id) === idStr);
    if (item) await updateItemEntityPosition(item, false);
  }

  alert("位置已更新！");
});

// =====================
// 初始化
// =====================
window.addEventListener("DOMContentLoaded", () => {
  loadBlacklistFromDB();
  fetchLatestCNShips(true);
});
