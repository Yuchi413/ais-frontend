import { loadCSS, loadHTML } from "../../utils.js";

// 載入 CSS 檔案
loadCSS('components/banner/banner.css');

// 載入 HTML 標籤
loadHTML(`
<div id="banner">
  <div id="banner-content">
    <img src="components/banner/assets/logo.png" alt="Logo" id="banner-logo">
    <div id="banner-text">
      <h1>智能海域監控與預警系統</h1>
      <div id="timestamp-row">
        <span id="localTime"></span>
        <span id="utcTime"></span>
      </div>
    </div>
  </div>
</div>
`);


// 更新時間戳記的函式
function updateTimestamp() {
    const localEl = document.getElementById('localTime');
    const utcEl = document.getElementById('utcTime');

    const now = new Date();

    // 本地（台灣時間）
    localEl.textContent = `${now.toLocaleString()}`;

    // UTC
    const yyyy = now.getUTCFullYear();
    const mm = String(now.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(now.getUTCDate()).padStart(2, "0");
    const hh = String(now.getUTCHours()).padStart(2, "0");
    const min = String(now.getUTCMinutes()).padStart(2, "0");
    const sec = String(now.getUTCSeconds()).padStart(2, "0");

    utcEl.textContent = `UTC：${yyyy}/${mm}/${dd} ${hh}:${min}:${sec}`;
}

setInterval(updateTimestamp, 1000);



// 每秒更新一次時間戳記
setInterval(updateTimestamp, 1000);
