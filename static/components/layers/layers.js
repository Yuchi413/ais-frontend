import { viewer } from "../viewer/viewer.js";
import { loadCSS, loadHTML, makePanelDraggable } from "../../utils.js";

// ------------------------------------------------------
// UI
// ------------------------------------------------------
loadCSS('components/layers/layers.css');

loadHTML(`
<div id="layerControlPanel">
    <div class="panel-header">
        <h3>圖層清單</h3>
        <button id="toggleLayersPanelBtn">-</button>
    </div>

    <div id="layerControlContent">

        <h4>底圖切換</h4>
        <select id="basemapSelector">
            <option value="bing">Bing 衛星</option>
            <option value="osm">OSM 開放街圖</option>
            <option value="night">夜間燈光（Earth at Night）</option>
        </select>

        <hr>

        <h4>主題圖層</h4>
        <ul id="geojsonLayerList"></ul>

        <hr>

        <button id="downloadSettingsBtn">下載設定</button>
        <input type="file" id="uploadSettingsFile" style="display:none;">
        <button id="uploadSettingsBtn">上傳設定</button>

    </div>
</div>
`);

makePanelDraggable("layerControlPanel", ".panel-header");


// ------------------------------------------------------
// DOM
// ------------------------------------------------------
const geojsonLayerList  = document.getElementById("geojsonLayerList");
const basemapSelector = document.getElementById("basemapSelector");
const uploadSettingsBtn = document.getElementById("uploadSettingsBtn");
const uploadSettingsFile = document.getElementById("uploadSettingsFile");
const downloadSettingsBtn = document.getElementById("downloadSettingsBtn");
const toggleLayersPanelBtn = document.getElementById("toggleLayersPanelBtn");
const layerControlContent = document.getElementById("layerControlContent");

let isCollapsed = true;
layerControlContent.style.display = "none";


// ------------------------------------------------------
// GeoJSON 圖層儲存
// ------------------------------------------------------
const geojsonLayers = {}; // {name: dataSource}


// ------------------------------------------------------
// 1️⃣ 底圖切換（Bing / OSM / 夜間燈光）
// ------------------------------------------------------
async function applyBaseMap(type) {
    while (viewer.imageryLayers.length > 0) {
        viewer.imageryLayers.remove(viewer.imageryLayers.get(0), false);
    }

    // 1. Bing 衛星
    if (type === "bing") {
        viewer.imageryLayers.addImageryProvider(
            await Cesium.IonImageryProvider.fromAssetId(2)
        );
    }

    // 2. OSM
    else if (type === "osm") {
        viewer.imageryLayers.addImageryProvider(
            new Cesium.UrlTemplateImageryProvider({
                url: "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
            })
        );
    }

    // 3. 夜間燈光 Earth at Night
    else if (type === "night") {
        viewer.imageryLayers.addImageryProvider(
            await Cesium.IonImageryProvider.fromAssetId(3812)
        );
    }
}

basemapSelector.addEventListener("change", () => {
    applyBaseMap(basemapSelector.value);
});

// 預設 Bing
applyBaseMap("bing");



// ------------------------------------------------------
// 2️⃣ GeoJSON 圖層（Ion Asset）
// ------------------------------------------------------
async function addGeoJsonLayer(name, ionAssetId) {
    try {
        const resource = await Cesium.IonResource.fromAssetId(ionAssetId);
        const dataSource = await Cesium.GeoJsonDataSource.load(resource, {
            clampToGround: false
        });

        viewer.dataSources.add(dataSource);
        geojsonLayers[name] = dataSource;

        let color = Cesium.Color.YELLOW.withAlpha(0.9);
        if (name.includes("12")) color = Cesium.Color.WHITE.withAlpha(1.0);
        if (name.includes("24")) color = Cesium.Color.WHITE.withAlpha(0.5);

        dataSource.entities.values.forEach(ent => {
            if (ent.polyline) {
                ent.polyline.width = 2;
                ent.polyline.height = 50;
                ent.polyline.material = color;
            }
        });

        dataSource.show = false;
        createGeoJsonListItem(name, dataSource);

    } catch (err) {
        console.error("GeoJSON 載入錯誤：", err);
    }
}



// ------------------------------------------------------
// ⭐ 新增：外部 URL GeoJSON（n8n AOI）
// ------------------------------------------------------
async function addExternalGeoJsonLayer(name, url) {
    try {
        const dataSource = await Cesium.GeoJsonDataSource.load(url, {
            clampToGround: false
        });

        viewer.dataSources.add(dataSource);
        geojsonLayers[name] = dataSource;

        // 自訂樣式
        dataSource.entities.values.forEach(ent => {
            if (ent.polygon) {
                ent.polygon.material = Cesium.Color.ORANGE.withAlpha(0.4);
                ent.polygon.outline = true;
                ent.polygon.outlineColor = Cesium.Color.RED;
                ent.polygon.outlineWidth = 2;
            }
            if (ent.polyline) {
                ent.polyline.width = 3;
                ent.polyline.material = Cesium.Color.RED.withAlpha(0.8);
            }

            // ✅ 讓 InfoBox 的 source 變成可點連結
            const date = getProp(ent, "date");
            const source = getProp(ent, "source");

            if (date || source) {
                ent.description = `
                <table class="cesium-infoBox-defaultTable">
                    <tr><th>date</th><td>${date || "—"}</td></tr>
                    <tr><th>source</th><td>${linkify(source)}</td></tr>
                </table>
                `;
            }
        });


        dataSource.show = false;
        createGeoJsonListItem(name, dataSource);

    } catch (err) {
        console.error(`外部 GeoJSON (${name}) 載入錯誤：`, err);
    }
}



// ------------------------------------------------------
// 建立列表項目 UI
// ------------------------------------------------------
function createGeoJsonListItem(name, dataSource) {
    const li = document.createElement("li");

    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = false;

    check.addEventListener("change", () => {
        dataSource.show = check.checked;
    });

    const label = document.createElement("span");
    label.textContent = name;

    li.appendChild(check);
    li.appendChild(label);
    geojsonLayerList.appendChild(li);
}



// ------------------------------------------------------
// 3️⃣ 設定檔（GeoJSON 顯示狀態）
// ------------------------------------------------------
downloadSettingsBtn.addEventListener("click", () => {
    const json = {};

    Object.keys(geojsonLayers).forEach(name => {
        json[name] = geojsonLayers[name].show;
    });

    const blob = new Blob([JSON.stringify(json, null, 2)], {
        type: "application/json"
    });

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "geojson-layer-settings.json";
    a.click();
});

uploadSettingsBtn.addEventListener("click", () => {
    uploadSettingsFile.click();
});

uploadSettingsFile.addEventListener("change", e => {
    const file = e.target.files[0];
    const reader = new FileReader();

    reader.onload = () => {
        const saved = JSON.parse(reader.result);
        Object.keys(saved).forEach(name => {
            if (geojsonLayers[name]) {
                geojsonLayers[name].show = saved[name];
            }
        });
    };

    reader.readAsText(file);
});



// ------------------------------------------------------
// 4️⃣ 面板開合
// ------------------------------------------------------
toggleLayersPanelBtn.addEventListener("click", () => {
    isCollapsed = !isCollapsed;
    layerControlContent.style.display = isCollapsed ? "none" : "block";
    toggleLayersPanelBtn.textContent = isCollapsed ? "+" : "-";
});



// ------------------------------------------------------
// 5️⃣ 預設載入海域圖層 + AOI
// ------------------------------------------------------
addGeoJsonLayer("海纜", 3390457);
addGeoJsonLayer("12海里範圍", 3460591);
addGeoJsonLayer("24海里範圍", 3860511);

// ⭐ 新增 AOI 外部來源
addExternalGeoJsonLayer("軍事航行警告區域", "https://n8n-ccit.serveray.org/webhook/aoi");


function getProp(ent, key) {
  const p = ent.properties?.[key];
  if (!p) return "";
  return (typeof p.getValue === "function") ? p.getValue(Cesium.JulianDate.now()) : p;
}

function linkify(url) {
  if (!url) return "—";
  const s = String(url).trim();
  if (!/^https?:\/\//i.test(s)) return s; // 不是 http/https 就照文字
  return `<a href="${s}" target="_blank" rel="noopener noreferrer">${s}</a>`;
}
