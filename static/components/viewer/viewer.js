// import { loadCSS, loadHTML } from "../../utils.js";

// // 載入外部 CSS 文件
// loadCSS('components/viewer/viewer.css');

// // 載入 HTML 結構
// loadHTML(`
//       <div id="cesiumContainer"></div>
// `);

// // 設定 Cesium Ion 的存取權杖
// Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlYmE4MzBmZS0wN2ZkLTQzNmQtYmFlOS1mYzgyM2E1NGViMzkiLCJpZCI6Mjc4NTkxLCJpYXQiOjE3NDAzODAxOTZ9.sVborFjUrI_1lBH4Bi2xnUloj4N-jfNkY6y6enxSsas';

// // 初始化 Cesium Viewer 並設定 Viewer 的基本參數
// export const viewer = new Cesium.Viewer('cesiumContainer', {
//   terrain: Cesium.EllipsoidTerrainProvider(),
//   timeline: false,
//   animation: false,
//   creditContainer: document.createElement('div'),
//   navigationHelpButton: false,
//   homeButton: false,
//   sceneModePicker: false,
//   baseLayerPicker: false,
//   geocoder: false,
//   infoBox: true,
//   selectionIndicator: false,
//   navigationInstructionsInitiallyVisible: false,
// });

// // ⭐⭐ 重要：讓其他模組能抓到 Viewer（blackname.js 用到）
// window.CESIUM_VIEWER = viewer;

// viewer.camera.flyTo({
//     destination: Cesium.Cartesian3.fromDegrees(121, 23.5, 3000000),
//     orientation: {
//         heading: Cesium.Math.toRadians(0.0),
//         pitch: Cesium.Math.toRadians(-90.0),
//         roll: 0.0
//     },
//     duration: 1
// });

// viewer.scene.globe.depthTestAgainstTerrain = false;



import { loadCSS, loadHTML } from "../../utils.js";

// 載入外部 CSS 文件
loadCSS('components/viewer/viewer.css');

// 載入 HTML 結構
loadHTML(`
      <div id="cesiumContainer"></div>
      <!-- 船種圖例（右下角、可拖曳、可收折） -->
    <div id="shipLegend" class="draggable">
      
      <div id="legendHeader">
        <span>船種圖例</span>
        <button id="legendToggleBtn">－</button>
      </div>

      <div id="legendContent">
        <div class="legend-item">
          <span class="legend-color" style="background: rgba(0, 0, 255, 0.7);"></span>
          <span>漁船 (2)</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: rgba(128, 128, 128, 0.7);"></span>
          <span>貨船 (3 / 7 / 8)</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: rgba(255, 255, 0, 0.7);"></span>
          <span>客船 (6)</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: rgba(255, 105, 180, 0.7);"></span>
          <span>遊艇 (1 / 9)</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: rgba(0, 255, 255, 0.7);"></span>
          <span>其他 (0 / 4 / 5)</span>
        </div>
      </div>
    </div>
`);

// 設定 Cesium Ion 的存取權杖
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlYmE4MzBmZS0wN2ZkLTQzNmQtYmFlOS1mYzgyM2E1NGViMzkiLCJpZCI6Mjc4NTkxLCJpYXQiOjE3NDAzODAxOTZ9.sVborFjUrI_1lBH4Bi2xnUloj4N-jfNkY6y6enxSsas';

// 初始化 Cesium Viewer 並設定 Viewer 的基本參數
export const viewer = new Cesium.Viewer('cesiumContainer', {
  terrain: Cesium.EllipsoidTerrainProvider(),
  timeline: false,
  animation: false,
  creditContainer: document.createElement('div'),
  navigationHelpButton: false,
  homeButton: false,
  sceneModePicker: false,
  baseLayerPicker: false,
  geocoder: true,
  infoBox: true,
  selectionIndicator: false,
  navigationInstructionsInitiallyVisible: false,
});

// ⭐⭐ 加在這裡
viewer.infoBox.frame.removeAttribute("sandbox");
viewer.infoBox.frame.setAttribute(
    "sandbox",
    "allow-same-origin allow-forms allow-scripts allow-popups allow-pointer-lock"
);

viewer.infoBox.viewModel.enableHtml = true;
viewer.infoBox.viewModel.enableCamera = true;
viewer.infoBox.viewModel.enableClose = true;

// ⭐⭐ 重要：讓其他模組能抓到 Viewer（blackname.js 用到）
window.CESIUM_VIEWER = viewer;

viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(121, 23.5, 3000000),
    orientation: {
        heading: Cesium.Math.toRadians(0.0),
        pitch: Cesium.Math.toRadians(-90.0),
        roll: 0.0
    },
    duration: 1
});

viewer.scene.globe.depthTestAgainstTerrain = false;


// === 可收折圖例 ===
document.addEventListener("DOMContentLoaded", () => {
  const legend = document.getElementById("shipLegend");
  const btn = document.getElementById("legendToggleBtn");

  btn.addEventListener("click", () => {
    const isCollapsed = legend.classList.toggle("collapsed");
    btn.textContent = isCollapsed ? "＋" : "－";
  });

  // === 可拖曳功能 ===
  let isDragging = false;
  let offsetX = 0;
  let offsetY = 0;

  const header = document.getElementById("legendHeader");

  header.addEventListener("mousedown", (e) => {
    isDragging = true;
    legend.classList.add("dragging");

    // 計算偏移
    offsetX = e.clientX - legend.getBoundingClientRect().left;
    offsetY = e.clientY - legend.getBoundingClientRect().top;

    e.preventDefault();
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;

    const x = e.clientX - offsetX;
    const y = e.clientY - offsetY;

    legend.style.left = x + "px";
    legend.style.top = y + "px";
    legend.style.right = "unset";
    legend.style.bottom = "unset";
  });

  document.addEventListener("mouseup", () => {
    isDragging = false;
    legend.classList.remove("dragging");
  });
});