// ==================== CONFIGURATION ====================
const API_BASE = window.location.origin && window.location.origin !== "null" 
    ? window.location.origin 
    : "http://localhost:5000";

// State management
let currentFilter = 'all';
let currentTab = 'detection';
let searchCache = new Map();
let autoRefreshInterval = null;

// ==================== UTILITY FUNCTIONS ====================
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

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    toast.innerHTML = `
        <span style="font-size: 1.5em;">${icons[type] || '📢'}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString('vi-VN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==================== STATS ====================
async function loadStats() {
    try {
        console.log("Fetching stats from", API_BASE + "/api/stats");
        const res = await fetchJson(API_BASE + "/api/stats");
        
        if (res && res.success && res.data) {
            const d = res.data;
            
            // Update stats with animation
            animateValue('totalDetections', 0, d.total || 0, 1000);
            animateValue('uniquePlates', 0, d.unique || 0, 1000);
            animateValue('todayCount', 0, d.today || 0, 1000);
            animateValue('watchlistCount', 0, d.watchlist_count || 0, 1000);
            animateValue('alertsCount', 0, d.alerts_pending || 0, 1000);
            
            // Update time
            document.getElementById("currentTime").textContent = new Date().toLocaleString('vi-VN');
        }
    } catch (e) {
        console.error("loadStats error", e);
    }
}

function animateValue(id, start, end, duration) {
    const obj = document.getElementById(id);
    if (!obj) return;
    
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        obj.textContent = Math.round(current);
    }, 16);
}

// ==================== PLATE CARDS ====================
function makePlateCard(plate) {
    const div = document.createElement("div");
    div.className = "plate-card" + (plate.is_watchlist ? " watchlist" : "");
    
    const imageHtml = plate.image_path 
        ? `<img src="${API_BASE}/api/image/${plate.id}" class="plate-image" alt="Plate image" onerror="this.style.display='none'" loading="lazy">` 
        : "";
    
    const confidence = plate.confidence !== undefined 
        ? (plate.confidence * 100).toFixed(1) + "%" 
        : "N/A";
    
    const watchlistIcon = plate.is_watchlist ? '⚠️ ' : '';

    div.innerHTML = `
        ${plate.is_watchlist ? '<div class="watchlist-badge">⚠️ WATCHLIST</div>' : ""}
        <div class="plate-number ${plate.is_watchlist ? "watchlist" : ""}">${watchlistIcon}${(plate.plate_number || "--").toUpperCase()}</div>
        ${imageHtml}
        <div class="plate-info"><strong>🆔 ID:</strong><span>#${plate.id || ""}</span></div>
        <div class="plate-info"><strong>🕐 Thời gian:</strong><span>${formatDate(plate.timestamp)}</span></div>
        <div class="plate-info"><strong>📊 Độ tin cậy:</strong><span>${confidence}</span></div>
        <div class="plate-info"><strong>📹 Nguồn:</strong><span>${plate.source || "N/A"}</span></div>
        ${plate.frame_number ? `<div class="plate-info"><strong>🎬 Frame:</strong><span>${plate.frame_number}</span></div>` : ''}
        <div class="plate-actions">
            ${plate.image_path ? `<button onclick="viewPlate(${plate.id})" class="info">🔎 Xem ảnh</button>` : ''}
            <button onclick="addToWatchlistQuick('${plate.plate_number}')" class="warning">➕ Watch</button>
            <button class="danger" onclick="deletePlate(${plate.id})">🗑️ Xóa</button>
        </div>
    `;
    return div;
}

function makeWatchlistCard(item) {
    const div = document.createElement("div");
    div.className = "plate-card watchlist-item";
    
    const alertIcons = {
        'danger': '🚨',
        'warning': '⚠️',
        'info': 'ℹ️'
    };
    const alertIcon = alertIcons[item.alert_type] || '⚠️';
    
    div.innerHTML = `
        <div class="watchlist-badge">${alertIcon}</div>
        <div class="plate-number watchlist">${item.plate_number.toUpperCase()}</div>
        <div class="plate-info">
            <strong>📝 Lý do:</strong>
            <span>${item.reason || "Không có"}</span>
        </div>
        <div class="plate-info">
            <strong>🏷️ Loại:</strong>
            <span>${alertIcon} ${item.alert_type || 'warning'}</span>
        </div>
        <div class="plate-info">
            <strong>📅 Ngày thêm:</strong>
            <span>${formatDate(item.added_date)}</span>
        </div>
        <div class="plate-info">
            <strong>🔍 Phát hiện:</strong>
            <span>${item.detection_count || 0} lần</span>
        </div>
        <div class="plate-info">
            <strong>👁️ Lần cuối:</strong>
            <span>${item.last_seen ? formatDate(item.last_seen) : "Chưa xuất hiện"}</span>
        </div>
        <div class="plate-actions">
            <button onclick="editWatchlistItem('${item.plate_number}', \`${item.reason || ''}\`, '${item.alert_type || 'warning'}')" class="warning">✏️ Sửa</button>
            <button class="danger" onclick="deleteWatchlistItem('${item.plate_number}')">🗑️ Xóa</button>
        </div>
    `;
    return div;
}

// ==================== DETECTIONS ====================
async function loadDetections(limit = 50) {
    const container = document.getElementById("detectionContent");
    container.innerHTML = '<div class="loading">Đang tải dữ liệu</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/plates/recent?limit=" + limit);
        container.innerHTML = "";
        
        if (res && res.success) {
            if (!res.data || res.count === 0) {
                container.innerHTML = '<div class="no-data">Không có bản ghi nào</div>';
                return;
            }
            
            const grid = document.createElement("div");
            grid.className = "plate-grid";
            res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
            container.appendChild(grid);
            
            showToast(`Đã tải ${res.count} bản ghi`, 'success');
        } else {
            container.innerHTML = `<div class="error">❌ Lỗi khi tải dữ liệu</div>`;
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Không thể kết nối đến API: ${e.message}</div>`;
    }
}

const debouncedSearch = debounce(async function() {
    const query = document.getElementById("searchBox").value.trim();
    const container = document.getElementById("detectionContent");
    
    if (!query) {
        loadDetections();
        return;
    }
    
    // Check cache
    if (searchCache.has(query)) {
        renderSearchResults(searchCache.get(query), query);
        return;
    }
    
    container.innerHTML = '<div class="loading">Đang tìm kiếm</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/plates/search?q=" + encodeURIComponent(query));
        
        // Cache result
        searchCache.set(query, res);
        renderSearchResults(res, query);
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}, 500);

function searchPlates() {
    debouncedSearch();
}

function renderSearchResults(res, query) {
    const container = document.getElementById("detectionContent");
    container.innerHTML = "";
    
    if (res && res.success) {
        if (!res.data || res.count === 0) {
            container.innerHTML = `<div class="no-data">Không tìm thấy kết quả cho "${query}"</div>`;
            return;
        }
        
        const grid = document.createElement("div");
        grid.className = "plate-grid";
        res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
        container.appendChild(grid);
        
        showToast(`Tìm thấy ${res.count} kết quả`, 'success');
    }
}

function clearSearch() {
    document.getElementById("searchBox").value = "";
    document.getElementById("advancedSearch").classList.remove("active");
    searchCache.clear();
    loadDetections();
}

function toggleAdvancedSearch() {
    const panel = document.getElementById("advancedSearch");
    panel.classList.toggle("active");
}

function applyAdvancedSearch() {
    const dateFrom = document.getElementById("dateFrom").value;
    const dateTo = document.getElementById("dateTo").value;
    const minConf = document.getElementById("minConfidence").value;
    const status = document.getElementById("statusFilter").value;
    
    showToast("Tính năng Advanced Search đang phát triển", "info");
    console.log("Advanced search params:", { dateFrom, dateTo, minConf, status });
}

async function filterDetections(mode) {
    document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    event?.target?.classList?.add("active");
    currentFilter = mode;
    
    const container = document.getElementById("detectionContent");
    container.innerHTML = '<div class="loading">Đang tải dữ liệu</div>';
    
    try {
        if (mode === "today") {
            const res = await fetchJson(API_BASE + "/api/stats/today");
            container.innerHTML = "";
            
            if (res && res.success && res.data && res.count > 0) {
                const grid = document.createElement("div");
                grid.className = "plate-grid";
                res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
                container.appendChild(grid);
                showToast(`Có ${res.count} phát hiện hôm nay`, 'success');
            } else {
                container.innerHTML = '<div class="no-data">Chưa có phát hiện nào hôm nay</div>';
            }
        } else if (mode === "watchlist") {
            const res = await fetchJson(API_BASE + "/api/plates/recent?limit=100");
            container.innerHTML = "";
            
            if (res && res.success && res.data) {
                const watchlistPlates = res.data.filter(p => p.is_watchlist);
                
                if (watchlistPlates.length > 0) {
                    const grid = document.createElement("div");
                    grid.className = "plate-grid";
                    watchlistPlates.forEach((p) => grid.appendChild(makePlateCard(p)));
                    container.appendChild(grid);
                    showToast(`Có ${watchlistPlates.length} biển số trong watchlist`, 'warning');
                } else {
                    container.innerHTML = '<div class="no-data">Không có phát hiện watchlist</div>';
                }
            }
        } else if (mode === "high-confidence") {
            const res = await fetchJson(API_BASE + "/api/plates/recent?limit=100");
            container.innerHTML = "";
            
            if (res && res.success && res.data) {
                const highConfPlates = res.data.filter(p => p.confidence >= 0.8);
                
                if (highConfPlates.length > 0) {
                    const grid = document.createElement("div");
                    grid.className = "plate-grid";
                    highConfPlates.forEach((p) => grid.appendChild(makePlateCard(p)));
                    container.appendChild(grid);
                    showToast(`Có ${highConfPlates.length} phát hiện độ tin cậy cao`, 'success');
                } else {
                    container.innerHTML = '<div class="no-data">Không có phát hiện độ tin cậy cao</div>';
                }
            }
        } else {
            loadDetections();
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

function viewPlate(id) {
    if (!id) {
        showToast("Không có ảnh", "error");
        return;
    }
    window.open(API_BASE + "/api/image/" + id, "_blank");
}

async function deletePlate(id) {
    if (!confirm("Xác nhận xóa bản ghi #" + id + "?")) return;
    
    try {
        const res = await fetchJson(API_BASE + "/api/plates/" + id + "?reason=Xóa từ dashboard", { 
            method: "DELETE" 
        });
        
        showToast(res.message || "Đã xóa thành công", "success");
        await loadStats();
        
        // Refresh current view
        if (currentFilter === 'all') {
            await loadDetections();
        } else {
            filterDetections(currentFilter);
        }
    } catch (e) {
        showToast("Xóa thất bại: " + e.message, "error");
    }
}

function addToWatchlistQuick(plateNumber) {
    document.getElementById("wlPlateNumber").value = plateNumber;
    showAddWatchlistModal();
}

// ==================== WATCHLIST ====================
async function loadWatchlist() {
    const container = document.getElementById("watchlistContent");
    container.innerHTML = '<div class="loading">Đang tải watchlist</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist");
        container.innerHTML = "";
        
        if (res && res.success) {
            if (!res.data || res.count === 0) {
                container.innerHTML = '<div class="no-data">Watchlist trống</div>';
                return;
            }
            
            const grid = document.createElement("div");
            grid.className = "plate-grid";
            res.data.forEach((item) => grid.appendChild(makeWatchlistCard(item)));
            container.appendChild(grid);
            
            showToast(`Có ${res.count} biển số trong watchlist`, 'info');
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

async function deleteWatchlistItem(plateNumber) {
    if (!confirm(`Xác nhận xóa "${plateNumber}" khỏi watchlist?`)) return;
    
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist/" + encodeURIComponent(plateNumber), {
            method: "DELETE",
        });
        
        if (res.success) {
            showToast(res.message || "Đã xóa khỏi watchlist", "success");
            loadWatchlist();
            loadStats();
        } else {
            showToast("Xóa thất bại: " + res.message, "error");
        }
    } catch (e) {
        showToast("Lỗi khi xóa: " + e.message, "error");
    }
}

function editWatchlistItem(plateNumber, reason, alertType) {
    document.getElementById("editPlateNumber").value = plateNumber;
    document.getElementById("editReason").value = reason || "";
    document.getElementById("editAlertType").value = alertType || "warning";
    document.getElementById("editWatchlistModal").classList.add("active");
}

async function editWatchlistSubmit(event) {
    event.preventDefault();
    
    const plateNumber = document.getElementById("editPlateNumber").value;
    const reason = document.getElementById("editReason").value.trim();
    const alertType = document.getElementById("editAlertType").value;
    
    try {
        // Delete old entry
        await fetchJson(API_BASE + "/api/watchlist/" + encodeURIComponent(plateNumber), { 
            method: "DELETE" 
        });
        
        // Add new entry with updated info
        const res = await fetchJson(API_BASE + "/api/watchlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plate_number: plateNumber,
                reason: reason,
                alert_type: alertType
            })
        });
        
        if (res.success) {
            showToast("Đã cập nhật watchlist", "success");
            closeEditModal();
            loadWatchlist();
            loadStats();
        }
    } catch (e) {
        showToast("Cập nhật thất bại: " + e.message, "error");
    }
}

// ==================== ALERTS ====================
async function loadAlerts() {
    const container = document.getElementById("alertsContent");
    container.innerHTML = '<div class="loading">Đang tải cảnh báo</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/alerts");
        container.innerHTML = "";
        
        if (res && res.success) {
            if (!res.data || res.count === 0) {
                container.innerHTML = '<div class="no-data">Không có cảnh báo nào</div>';
                return;
            }
            
            res.data.forEach(alert => {
                const alertCard = document.createElement("div");
                alertCard.className = "alert-card danger";
                alertCard.innerHTML = `
                    <div class="alert-content">
                        <h4>🚨 ${alert.plate_number}</h4>
                        <p><strong>Loại:</strong> ${alert.alert_type}</p>
                        <p>${alert.message}</p>
                        <small>🕐 ${formatDate(alert.timestamp)}</small>
                    </div>
                    <button class="success" onclick="resolveAlert(${alert.id})">✅ Xử lý</button>
                `;
                container.appendChild(alertCard);
            });
            
            showToast(`Có ${res.count} cảnh báo chưa xử lý`, 'warning');
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

async function resolveAlert(id) {
    showToast("Tính năng đang phát triển", "info");
}

function resolveAllAlerts() {
    showToast("Tính năng đang phát triển", "info");
}

function clearAlerts() {
    showToast("Tính năng đang phát triển", "info");
}

// ==================== MODALS ====================
function showAddWatchlistModal() {
    document.getElementById("addWatchlistForm").reset();
    document.getElementById("addWatchlistModal").classList.add("active");
}

function closeModal() {
    document.getElementById("addWatchlistModal").classList.remove("active");
}

function closeEditModal() {
    document.getElementById("editWatchlistModal").classList.remove("active");
}

async function addWatchlistSubmit(event) {
    event.preventDefault();
    
    const plateNumber = document.getElementById("wlPlateNumber").value.trim().toUpperCase();
    const reason = document.getElementById("wlReason").value.trim();
    const alertType = document.getElementById("wlAlertType").value;
    
    if (!plateNumber) {
        showToast("Vui lòng nhập biển số", "error");
        return;
    }
    
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plate_number: plateNumber,
                reason: reason,
                alert_type: alertType
            })
        });
        
        if (res.success) {
            showToast(`Đã thêm ${plateNumber} vào watchlist`, "success");
            closeModal();
            loadWatchlist();
            loadStats();
        } else {
            showToast("Thêm thất bại: " + res.message, "error");
        }
    } catch (e) {
        showToast("Lỗi khi thêm: " + e.message, "error");
    }
}

// Close modals when clicking outside
window.onclick = function(event) {
    const addModal = document.getElementById("addWatchlistModal");
    const editModal = document.getElementById("editWatchlistModal");
    
    if (event.target == addModal) {
        closeModal();
    }
    if (event.target == editModal) {
        closeEditModal();
    }
};

// ==================== TAB SWITCHING ====================
function switchTab(tab) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
    document.querySelector(`.tab[onclick*="${tab}"]`)?.classList?.add("active");
    document.getElementById(tab + "-section")?.classList?.add("active");
    
    currentTab = tab;
    
    // Load data for active tab
    if (tab === "detection") loadDetections();
    if (tab === "watchlist") loadWatchlist();
    if (tab === "alerts") loadAlerts();
}

// ==================== THEME TOGGLE ====================
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    const btn = document.querySelector('.theme-toggle-btn');
    if (btn) {
        btn.textContent = newTheme === 'light' ? '🌙 Dark' : '☀️ Light';
    }
    
    showToast(`Đã chuyển sang ${newTheme === 'light' ? 'Light' : 'Dark'} mode`, 'info');
}

// ==================== MISC FUNCTIONS ====================
function exportData() {
    showToast("Tính năng Export đang phát triển", "info");
}

function showSettings() {
    showToast("Cài đặt đang phát triển", "info");
}

function importWatchlist() {
    showToast("Import đang phát triển", "info");
}

function exportWatchlist() {
    showToast("Export watchlist đang phát triển", "info");
}

// ==================== AUTO REFRESH ====================
function startAutoRefresh(interval = 30000) {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    autoRefreshInterval = setInterval(() => {
        console.log("Auto-refreshing stats...");
        loadStats();
        
        // Refresh current tab
        if (currentTab === 'detection' && currentFilter === 'all') {
            loadDetections();
        }
    }, interval);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// ==================== KEYBOARD SHORTCUTS ====================
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K: Focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('searchBox').focus();
    }
    
    // Ctrl/Cmd + R: Refresh
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        loadStats();
        if (currentTab === 'detection') loadDetections();
        if (currentTab === 'watchlist') loadWatchlist();
        if (currentTab === 'alerts') loadAlerts();
    }
    
    // Escape: Close modals
    if (e.key === 'Escape') {
        closeModal();
        closeEditModal();
    }
});

// ==================== INITIALIZATION ====================
document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 LPR Dashboard initialized");
    console.log("API Base:", API_BASE);
    
    // Load saved theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
        const btn = document.querySelector('.theme-toggle-btn');
        if (btn) {
            btn.textContent = savedTheme === 'light' ? '🌙 Dark' : '☀️ Light';
        }
    }
    
    // Initial load
    loadStats();
    loadDetections();
    
    // Set current date for advanced search
    const today = new Date().toISOString().split('T')[0];
    document.getElementById("dateTo").value = today;
    
    // Start auto-refresh
    startAutoRefresh(30000); // 30 seconds
    
    // Log shortcuts
    console.log("⌨️ Keyboard Shortcuts:");
    console.log("  Ctrl/Cmd + K: Focus search");
    console.log("  Ctrl/Cmd + R: Refresh");
    console.log("  Escape: Close modals");
    
    showToast("Dashboard đã sẵn sàng! 🚀", "success");
});

// Handle page visibility
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
        console.log("⏸️ Auto-refresh paused (tab hidden)");
    } else {
        startAutoRefresh();
        loadStats();
        console.log("▶️ Auto-refresh resumed");
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});