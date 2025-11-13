// JAVASCRIPT: fetch API + render UI
// Use current origin if possible (works when served by Flask under same origin),
// fallback to http://localhost:5000 for local dev.
const API_BASE = window.location.origin && window.location.origin !== "null" ? window.location.origin : "http://localhost:5000";

// Ép trực tiếp tới flask API
// const API_BASE = "http://localhost:5000";

/* Generic fetch wrapper */
async function fetchJson(url, opts = {}) {
try {
    const res = await fetch(url, opts);
    if (!res.ok) {
    const text = await res.text();
    console.error("Fetch error", url, res.status, text);
    throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return await res.json();
} catch (err) {
    console.error("Network/Fetch failed for", url, err);
    throw err;
}
}

/* Load statistics and update cards */
async function loadStats() {
const elTotal = document.getElementById("totalDetections");
const elUnique = document.getElementById("uniquePlates");
const elToday = document.getElementById("todayCount");
const elWatch = document.getElementById("watchlistCount");
const elAlerts = document.getElementById("alertsCount");
const elTime = document.getElementById("currentTime");

try {
    console.log("Fetching", API_BASE + "/api/stats");
    const res = await fetchJson(API_BASE + "/api/stats");
    if (res && res.success && res.data) {
    const d = res.data;
    elTotal.textContent = d.total ?? 0;
    elUnique.textContent = d.unique ?? 0;
    elToday.textContent = d.today ?? 0;
    elWatch.textContent = d.watchlist_count ?? 0;
    elAlerts.textContent = d.alerts_pending ?? 0;
    elTime.textContent = new Date().toLocaleString();
    } else {
    console.warn("Unexpected stats response", res);
    }
} catch (e) {
    console.error("loadStats error", e);
}
}

/* Make a plate card DOM element */
function makePlateCard(plate) {
const div = document.createElement("div");
div.className = "plate-card" + (plate.watchlist ? " watchlist" : "");
const imageHtml = plate.id ? `<img src="${API_BASE}/api/image/${plate.id}" class="plate-image" alt="plate image">` : "";
div.innerHTML = `
    ${plate.watchlist ? '<div class="watchlist-badge">WATCHLIST</div>' : ""}
    <div class="plate-number ${plate.watchlist ? "watchlist" : ""}">${(plate.plate_number || "--").toUpperCase()}</div>
    <div class="plate-info"><strong>ID:</strong><span>${plate.id ?? ""}</span></div>
    <div class="plate-info"><strong>Time:</strong><span>${plate.timestamp ?? ""}</span></div>
    ${imageHtml}
    <div class="plate-info"><strong>Confidence:</strong><span>${
    plate.confidence !== undefined ? (plate.confidence * 100).toFixed(0) + "%" : "N/A"
    }</span></div>
    <div class="plate-actions">
    <button onclick="viewPlate(${plate.id})">🔎 Xem</button>
    <button class="danger" onclick="deletePlate(${plate.id})">🗑️ Xóa</button>
    </div>
`;
return div;
}

/* Tạo thẻ HTML cho một item trong Watchlist */
function makeWatchlistCard(item) {
  const div = document.createElement("div");
  // Chúng ta dùng lại class .plate-card cho tiện, nhưng thêm class .watchlist-item
  div.className = "plate-card watchlist-item"; 
  
  div.innerHTML = `
    <div class="plate-number watchlist">${item.plate_number.toUpperCase()}</div>
    <div class="plate-info">
      <strong>Lý do:</strong>
      <span>${item.reason || "N/A"}</span>
    </div>
    <div class="plate-info">
      <strong>Ngày thêm:</strong>
      <span>${item.added_date || "N/A"}</span>
    </div>
    <div class="plate-info">
      <strong>Phát hiện:</strong>
      <span>${item.detection_count || 0} lần</span>
    </div>
    <div class="plate-actions" style="grid-template-columns: 1fr;">
      <button class="danger" onclick="deleteWatchlistItem('${item.plate_number}')">
        🗑️ Xóa khỏi Watchlist
      </button>
    </div>
  `;
  return div;
}

/* Load recent detections and render */
async function loadDetections(limit = 20) {
const container = document.getElementById("detectionContent");
container.innerHTML = '<div class="loading">Đang tải dữ liệu</div>';
try {
    console.log("Fetching", API_BASE + "/api/plates/recent?limit=" + limit);
    const res = await fetchJson(API_BASE + "/api/plates/recent?limit=" + limit);
    container.innerHTML = "";
    if (res && res.success) {
    if (!res.data || res.count === 0) {
        container.innerHTML = '<div class="no-data">Không có bản ghi</div>';
        return;
    }
    const grid = document.createElement("div");
    grid.className = "plate-grid";
    res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
    container.appendChild(grid);
    } else {
    container.innerHTML = `<div class="error">Lỗi khi tải dữ liệu</div>`;
    console.warn("Unexpected detections response", res);
    }
} catch (e) {
    container.innerHTML = `<div class="error">Không thể kết nối đến API: ${e.message}</div>`;
}
}

/* Open plate image in new tab */
function viewPlate(id) {
if (!id) {
    alert("No image available");
    return;
}
window.open(API_BASE + "/api/image/" + id, "_blank");
}

/* Delete plate */
async function deletePlate(id) {
if (!confirm("Xác nhận xóa plate id " + id + "?")) return;
try {
    const res = await fetchJson(API_BASE + "/api/plates/" + id + "?reason=deleted_by_ui", { method: "DELETE" });
    console.log("delete response", res);
    alert(res.message || "Deleted");
    await loadStats();
    await loadDetections();
} catch (e) {
    alert("Xóa thất bại: " + e.message);
}
}

/* Xóa một biển số khỏi Watchlist */
async function deleteWatchlistItem(plateNumber) {
    if (!confirm(`Xác nhận xóa "${plateNumber}" khỏi Watchlist?`)) return;

    try {
    const res = await fetchJson(API_BASE + "/api/watchlist/" + plateNumber, {
        method: "DELETE",
    });

    if (res.success) {
        alert(res.message);
        loadWatchlist(); // Tải lại danh sách watchlist
        loadStats(); // Cập nhật lại thẻ thống kê
    } else {
        alert("Xóa thất bại: " + res.message);
    }
    } catch (e) {
    alert("Lỗi khi xóa: " + e.message);
    }
}

/* Tải danh sách watchlist và render */
async function loadWatchlist() {
  const container = document.getElementById("watchlistContent");
  container.innerHTML = '<div class="loading">Đang tải watchlist</div>';
  
  try {
    const res = await fetchJson(API_BASE + "/api/watchlist");
    container.innerHTML = ""; // Xóa loading

    if (res && res.success) {
      if (!res.data || res.count === 0) {
        container.innerHTML = '<div class="no-data">Watchlist trống</div>';
        return;
      }
      
      // Dùng lại .plate-grid để có bố cục cột
      const grid = document.createElement("div");
      grid.className = "plate-grid"; 
      
      res.data.forEach((item) => grid.appendChild(makeWatchlistCard(item)));
      container.appendChild(grid);
    } else {
      container.innerHTML = `<div class="error">Lỗi khi tải watchlist: ${res.message}</div>`;
    }
  } catch (e) {
    container.innerHTML = `<div class="error">Không thể kết nối API: ${e.message}</div>`;
  }
}

/* Search plates */
function searchPlates() {
const q = document.getElementById("searchBox").value.trim();
const container = document.getElementById("detectionContent");
if (!q) {
    loadDetections();
    return;
}
container.innerHTML = '<div class="loading">Đang tìm kiếm</div>';
fetchJson(API_BASE + "/api/plates/search?q=" + encodeURIComponent(q))
    .then((res) => {
    container.innerHTML = "";
    if (!res || !res.success) {
        container.innerHTML = `<div class="error">${res?.message || "Lỗi"}</div>`;
        return;
    }
    if (!res.data || res.count === 0) {
        container.innerHTML = '<div class="no-data">Không tìm thấy</div>';
        return;
    }
    const grid = document.createElement("div");
    grid.className = "plate-grid";
    res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
    container.appendChild(grid);
    })
    .catch((err) => {
    container.innerHTML = `<div class="error">Lỗi: ${err.message}</div>`;
    });
}

function clearSearch() {
document.getElementById("searchBox").value = "";
loadDetections();
}

/* Filters (basic stub — expand as needed) */
function filterDetections(mode) {
// simple client-side behavior for demo
document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
event?.target?.classList?.add("active");
if (mode === "today") {
    // call the /api/stats/today endpoint for today's records
    const container = document.getElementById("detectionContent");
    container.innerHTML = '<div class="loading">Đang tải dữ liệu hôm nay</div>';
    fetchJson(API_BASE + "/api/stats/today")
    .then((res) => {
        container.innerHTML = "";
        if (!res || !res.success) {
        container.innerHTML = '<div class="error">Lỗi</div>';
        return;
        }
        if (!res.data || res.count === 0) {
        container.innerHTML = '<div class="no-data">Không có bản ghi hôm nay</div>';
        return;
        }
        const grid = document.createElement("div");
        grid.className = "plate-grid";
        res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
        container.appendChild(grid);
    })
    .catch((e) => {
        container.innerHTML = `<div class="error">Lỗi: ${e.message}</div>`;
    });
} else if (mode === "watchlist") {
    const container = document.getElementById("detectionContent");
    container.innerHTML = '<div class="loading">Đang tải watchlist</div>';
    fetchJson(API_BASE + "/api/watchlist")
    .then((res) => {
        container.innerHTML = "";
        if (!res || !res.success) {
        container.innerHTML = '<div class="error">Lỗi</div>';
        return;
        }
        if (!res.data || res.count === 0) {
        container.innerHTML = '<div class="no-data">Không có watchlist</div>';
        return;
        }
        const grid = document.createElement("div");
        grid.className = "plate-grid";
        res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
        container.appendChild(grid);
    })
    .catch((e) => {
        container.innerHTML = `<div class="error">Lỗi: ${e.message}</div>`;
    });
} else {
    loadDetections();
}
}

/* Small stubs for other UI buttons (so clicking không lỗi) */
function exportData() {
alert("Export chưa triển khai (demo).");
}
function showSettings() {
alert("Cài đặt chưa triển khai (demo).");
}
function showAddWatchlistModal() {
alert("Thêm watchlist (chưa triển khai).");
}
function importWatchlist() {
alert("Import watchlist (chưa triển khai).");
}
// function loadWatchlist() {
// alert("Load watchlist (chưa triển khai).");
// }
function exportWatchlist() {
alert("Export watchlist (chưa triển khai).");
}
function comparePlates() {
alert("So sánh (chưa triển khai).");
}
function findAllSimilar() {
alert("Tìm tương tự (chưa triển khai).");
}

/* Tab switch (simple) */
function switchTab(tab) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
    document.querySelector(`.tab[onclick*="${tab}"]`)?.classList?.add("active");
    document.getElementById(tab + "-section")?.classList?.add("active");

    // load relevant data
    if (tab === "detection") loadDetections();
    if (tab === "watchlist") loadWatchlist();
}

/* Initial load */
document.addEventListener("DOMContentLoaded", () => {
    console.log("Dashboard script loaded, initializing...");
    loadStats();
    loadDetections();
    setInterval(loadStats, 30_000); // refresh stats every 30s
});

/* ==================== MODAL LOGIC ==================== */
const modal = document.getElementById("addWatchlistModal");

// Hàm hiển thị modal
function showAddWatchlistModal() {
  document.getElementById("addWatchlistForm").reset(); // Xóa form cũ
  modal.style.display = "flex"; // Hiển thị modal
}

// Hàm đóng modal
function closeModal() {
  modal.style.display = "none";
}

// Hàm xử lý khi submit form
async function addWatchlistSubmit(event) {
  event.preventDefault(); // Ngăn trang tải lại

  const plateNumber = document.getElementById("wlPlateNumber").value.trim().toUpperCase();
  const reason = document.getElementById("wlReason").value.trim();

  if (!plateNumber) {
    alert("Vui lòng nhập biển số");
    return;
  }

  try {
    const res = await fetchJson(API_BASE + "/api/watchlist", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        plate_number: plateNumber,
        reason: reason,
        alert_type: "warning", // Bạn có thể thêm trường này vào form nếu muốn
      }),
    });

    if (res.success) {
      alert("Đã thêm " + plateNumber + " vào watchlist");
      closeModal();
      loadWatchlist(); // Tải lại danh sách watchlist
      loadStats(); // Cập nhật thẻ thống kê
    } else {
      alert("Thêm thất bại: " + res.message);
    }
  } catch (e) {
    alert("Lỗi khi thêm: " + e.message);
  }
}

// Đóng modal nếu bấm ra ngoài
window.onclick = function (event) {
  if (event.target == modal) {
    closeModal();
  }
};

/* =================================================== */