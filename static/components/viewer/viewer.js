import { loadCSS, loadHTML } from "../../utils.js";

// 載入外部 CSS 文件
loadCSS('components/viewer/viewer.css');

// 載入 HTML 結構
loadHTML(`
      <div id="cesiumContainer"></div>
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
  geocoder: false,
  infoBox: true,
  selectionIndicator: false,
  navigationInstructionsInitiallyVisible: false,
});

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
