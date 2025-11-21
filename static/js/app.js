// ==================== CONFIGURATION ====================
const API_BASE = window.location.origin || "http://localhost:5000";

let currentSourceType = 'webcam';
let currentTab = 'camera';
let detectionStatus = null;
let statusCheckInterval = null;

// ==================== UTILITY FUNCTIONS ====================

async function fetchJson(url, opts = {}) {
    try {
        const res = await fetch(url, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) {
        console.error("Fetch error:", url, err);
        throw err;
    }
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    toast.innerHTML = `<span style="font-size: 1.5em;">${icons[type] || '📢'}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString('vi-VN');
}

// ==================== CAMERA CONTROL ====================

function selectSourceType(type) {
    currentSourceType = type;
    document.querySelectorAll('.source-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelector(`[onclick*="${type}"]`).classList.add('active');
    document.querySelectorAll('.source-config').forEach(config => config.classList.remove('active'));
    document.getElementById(`config-${type}`).classList.add('active');
}

async function scanWebcams() {
    showToast('Đang quét camera...', 'info');
    try {
        const res = await fetchJson(API_BASE + '/api/cameras/available?max_check=5');
        const listDiv = document.getElementById('webcamList');
        listDiv.innerHTML = '';
        
        if (res.success && res.data && res.data.length > 0) {
            listDiv.innerHTML = '<h4>Camera tìm thấy:</h4>';
            res.data.forEach(cam => {
                const div = document.createElement('div');
                div.className = 'camera-item';
                div.innerHTML = `
                    <strong>📹 Camera ${cam.id}</strong>
                    <span>${cam.resolution}</span>
                    <button onclick="selectWebcam(${cam.id})" class="success">Chọn</button>
                `;
                listDiv.appendChild(div);
            });
            showToast(`Tìm thấy ${res.data.length} camera`, 'success');
        } else {
            listDiv.innerHTML = '<p>Không tìm thấy camera</p>';
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

function selectWebcam(id) {
    document.getElementById('webcamId').value = id;
    showToast(`Đã chọn Camera ${id}`, 'success');
}

function updatePhoneURL() {
    const ip = document.getElementById('phoneIP').value;
    document.getElementById('phoneURL').value = `http://${ip}:4747/video`;
}

function getSourceValue(type) {
    switch(type) {
        case 'webcam':
            return document.getElementById('webcamId').value;
        case 'phone':
            return document.getElementById('phoneURL').value;
        case 'video':
            return document.getElementById('videoFile').dataset.uploadedPath || '';
        case 'image':
            return document.getElementById('imageFile').dataset.uploadedPath || '';
        default:
            return '';
    }
}

async function testConnection() {
    const sourceValue = getSourceValue(currentSourceType);
    if (!sourceValue) {
        showToast('Vui lòng nhập thông tin camera', 'warning');
        return;
    }
    
    showToast('Đang test...', 'info');
    try {
        const res = await fetchJson(API_BASE + '/api/cameras/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_type: currentSourceType,
                source_value: sourceValue
            })
        });
        
        if (res.success) {
            showToast('✅ Kết nối thành công!', 'success');
        } else {
            showToast('❌ Thất bại: ' + res.message, 'error');
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

async function handleVideoUpload(input) {
    const file = input.files[0];
    if (!file) return;
    
    showToast('Đang upload...', 'info');
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch(API_BASE + '/api/upload/video', {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        
        if (result.success) {
            document.getElementById('videoFileName').textContent = `✅ ${result.data.filename}`;
            document.getElementById('videoFile').dataset.uploadedPath = result.data.filepath;
            showToast('Upload thành công!', 'success');
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

async function handleImageUpload(input) {
    const files = input.files;
    if (!files || files.length === 0) return;
    
    showToast(`Đang upload ${files.length} ảnh...`, 'info');
    
    for (let i = 0; i < files.length; i++) {
        const formData = new FormData();
        formData.append('file', files[i]);
        
        try {
            const res = await fetch(API_BASE + '/api/upload/image', {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            
            if (result.success && i === 0) {
                document.getElementById('imageFile').dataset.uploadedPath = result.data.filepath;
            }
        } catch (e) {
            console.error('Upload error:', e);
        }
    }
    
    document.getElementById('imageFileName').textContent = `✅ Đã upload ${files.length} ảnh`;
    showToast('Upload thành công!', 'success');
}

async function showInstructions(type) {
    try {
        const res = await fetchJson(API_BASE + `/api/cameras/instructions/${type}`);
        if (res.success) {
            document.getElementById('instructionsContent').textContent = res.data.instructions;
            document.getElementById('instructionsModal').classList.add('active');
        }
    } catch (e) {
        showToast('Lỗi', 'error');
    }
}

function closeInstructionsModal() {
    document.getElementById('instructionsModal').classList.remove('active');
}

// ==================== DETECTION CONTROL ====================

async function toggleDetection() {
    if (detectionStatus && detectionStatus.running) {
        await stopDetection();
    } else {
        await startDetection();
    }
}

async function startDetection() {
    const sourceValue = getSourceValue(currentSourceType);
    if (!sourceValue) {
        showToast('Vui lòng chọn camera!', 'warning');
        return;
    }
    
    showToast('Đang khởi động...', 'info');
    
    try {
        const res = await fetchJson(API_BASE + '/api/detection/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_type: currentSourceType,
                source_value: sourceValue,
                save_crops: document.getElementById('optSaveCrops').checked,
                save_video: document.getElementById('optSaveVideo').checked
            })
        });
        
        if (res.success) {
            showToast('✅ Detection đã khởi động!', 'success');
            updateDetectionStatus({ running: true, source_type: currentSourceType, source_value: sourceValue });
            startStatusPolling();
        } else {
            showToast('Không thể khởi động: ' + res.message, 'error');
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

async function stopDetection() {
    showToast('Đang dừng...', 'info');
    try {
        const res = await fetchJson(API_BASE + '/api/detection/stop', { method: 'POST' });
        if (res.success) {
            showToast('✅ Đã dừng!', 'success');
            updateDetectionStatus({ running: false });
            stopStatusPolling();
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

function updateDetectionStatus(status) {
    detectionStatus = status;
    const indicator = document.getElementById('statusIndicator');
    const statusInfo = document.getElementById('statusInfo');
    const btn = document.getElementById('btnStartStop');
    const liveIndicator = document.getElementById('liveIndicator');
    const liveImg = document.getElementById('liveStreamView');
    
    if (status.running) {
        if (liveImg) {
            liveImg.style.display = 'block';
            liveImg.src = API_BASE + "/video_feed?t=" + new Date().getTime();
        }
        
        indicator.innerHTML = `<span class="status-dot online"></span><span class="status-text">ĐANG CHẠY</span>`;
        statusInfo.innerHTML = `
            <p><strong>Nguồn:</strong> ${status.source_type}</p>
            <p><strong>Value:</strong> ${status.source_value}</p>
            ${status.start_time ? `<p><strong>Bắt đầu:</strong> ${formatDate(status.start_time)}</p>` : ''}
        `;
        btn.className = 'danger btn-large';
        btn.innerHTML = '⏹️ Dừng';
        liveIndicator.innerHTML = `<span class="live-dot"></span>LIVE`;
        liveIndicator.className = 'live-indicator online';
    } else {
        if (liveImg) liveImg.src = "../static/images/placeholder.png";
        indicator.innerHTML = `<span class="status-dot offline"></span><span class="status-text">OFFLINE</span>`;
        statusInfo.innerHTML = '<p>Chưa chạy</p>';
        btn.className = 'success btn-large';
        btn.innerHTML = '▶️ Bắt đầu';
        liveIndicator.innerHTML = `<span class="live-dot"></span>OFFLINE`;
        liveIndicator.className = 'live-indicator offline';
    }
}

function startStatusPolling() {
    if (statusCheckInterval) clearInterval(statusCheckInterval);
    statusCheckInterval = setInterval(async () => {
        try {
            const res = await fetchJson(API_BASE + '/api/detection/status');
            if (res.success) {
                updateDetectionStatus(res.data);
                if (res.data.running) loadStats();
            }
        } catch (e) {
            console.error('Status check error:', e);
        }
    }, 2000);
}

function stopStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

// ==================== DATA LOADING ====================

async function loadStats() {
    try {
        const res = await fetchJson(API_BASE + "/api/stats");
        if (res && res.success && res.data) {
            const d = res.data;
            document.getElementById('totalDetections').textContent = d.total || 0;
            document.getElementById('uniquePlates').textContent = d.unique || 0;
            document.getElementById('todayCount').textContent = d.today || 0;
            document.getElementById('watchlistCount').textContent = d.watchlist_count || 0;
            document.getElementById('alertsCount').textContent = d.alerts_pending || 0;
        }
    } catch (e) {
        console.error("loadStats error", e);
    }
}

async function loadDetections(limit = 50) {
    const container = document.getElementById("detectionContent");
    container.innerHTML = '<div class="loading">Đang tải...</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/plates/recent?limit=" + limit);
        container.innerHTML = "";
        
        if (res && res.success && res.data && res.count > 0) {
            const grid = document.createElement("div");
            grid.className = "plate-grid";
            res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
            container.appendChild(grid);
        } else {
            container.innerHTML = '<div class="no-data">Không có dữ liệu</div>';
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

function makePlateCard(plate) {
    const div = document.createElement("div");
    div.className = "plate-card" + (plate.is_watchlist ? " watchlist" : "");
    
    const imageHtml = plate.image_path 
        ? `<img src="${API_BASE}/api/image/${plate.id}" class="plate-image" alt="Plate" onerror="this.style.display='none'" loading="lazy">` 
        : "";
    
    const confidence = plate.confidence ? (plate.confidence * 100).toFixed(1) + "%" : "N/A";
    
    div.innerHTML = `
        ${plate.is_watchlist ? '<div class="watchlist-badge">⚠️ WATCHLIST</div>' : ""}
        <div class="plate-number ${plate.is_watchlist ? "watchlist" : ""}">${(plate.plate_number || "").toUpperCase()}</div>
        ${imageHtml}
        <div class="plate-info"><strong>🆔 ID:</strong><span>#${plate.id}</span></div>
        <div class="plate-info"><strong>🕐 Thời gian:</strong><span>${formatDate(plate.timestamp)}</span></div>
        <div class="plate-info"><strong>📊 Độ tin cậy:</strong><span>${confidence}</span></div>
        <div class="plate-info"><strong>📹 Nguồn:</strong><span>${plate.source || "N/A"}</span></div>
        <div class="plate-actions">
            ${plate.image_path ? `<button onclick="viewPlate(${plate.id})" class="info">🔎 Xem</button>` : ''}
            <button onclick="addToWatchlistQuick('${plate.plate_number}')" class="warning">➕ Watch</button>
        </div>
    `;
    return div;
}

function viewPlate(id) {
    window.open(API_BASE + "/api/image/" + id, "_blank");
}

async function searchPlates() {
    const query = document.getElementById('searchBox').value.trim();
    if (!query) {
        loadDetections();
        return;
    }
    
    showToast('Đang tìm kiếm...', 'info');
    try {
        const res = await fetchJson(API_BASE + `/api/plates/search?query=${encodeURIComponent(query)}`);
        const container = document.getElementById("detectionContent");
        container.innerHTML = "";
        
        if (res && res.success && res.data && res.data.length > 0) {
            const grid = document.createElement("div");
            grid.className = "plate-grid";
            res.data.forEach((p) => grid.appendChild(makePlateCard(p)));
            container.appendChild(grid);
            showToast(`Tìm thấy ${res.data.length} kết quả`, 'success');
        } else {
            container.innerHTML = '<div class="no-data">Không tìm thấy</div>';
        }
    } catch (e) {
        showToast('Lỗi: ' + e.message, 'error');
    }
}

// ==================== WATCHLIST ====================

async function loadWatchlist() {
    const container = document.getElementById("watchlistContent");
    container.innerHTML = '<div class="loading">Đang tải...</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist");
        container.innerHTML = "";
        
        if (res && res.success && res.data && res.count > 0) {
            const grid = document.createElement("div");
            grid.className = "plate-grid";
            res.data.forEach((item) => grid.appendChild(makeWatchlistCard(item)));
            container.appendChild(grid);
        } else {
            container.innerHTML = '<div class="no-data">Watchlist trống</div>';
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

function makeWatchlistCard(item) {
    const div = document.createElement("div");
    div.className = "plate-card watchlist-item";
    const alertIcons = { 'danger': '🚨', 'warning': '⚠️', 'info': 'ℹ️' };
    const icon = alertIcons[item.alert_type] || '⚠️';
    
    div.innerHTML = `
        <div class="watchlist-badge">${icon}</div>
        <div class="plate-number watchlist">${item.plate_number.toUpperCase()}</div>
        <div class="plate-info"><strong>📝 Lý do:</strong><span>${item.reason || "Không có"}</span></div>
        <div class="plate-info"><strong>🏷️ Loại:</strong><span>${icon} ${item.alert_type}</span></div>
        <div class="plate-info"><strong>📅 Thêm:</strong><span>${formatDate(item.added_date)}</span></div>
        <div class="plate-info"><strong>🔢 Phát hiện:</strong><span>${item.detection_count || 0} lần</span></div>
        <div class="plate-actions">
            <button onclick="editWatchlistItem('${item.plate_number}', \`${item.reason || ''}\`, '${item.alert_type}')" class="warning">✏️ Sửa</button>
            <button class="danger" onclick="deleteWatchlistItem('${item.plate_number}')">🗑️ Xóa</button>
        </div>
    `;
    return div;
}

function showAddWatchlistModal() {
    document.getElementById("wlPlateNumber").value = '';
    document.getElementById("wlReason").value = '';
    document.getElementById("addWatchlistModal").classList.add("active");
}

function addToWatchlistQuick(plateNumber) {
    document.getElementById("wlPlateNumber").value = plateNumber;
    showAddWatchlistModal();
}

async function addWatchlistSubmit(event) {
    event.preventDefault();
    const plateNumber = document.getElementById("wlPlateNumber").value.trim().toUpperCase();
    const reason = document.getElementById("wlReason").value.trim();
    const alertType = document.getElementById("wlAlertType").value;
    
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate_number: plateNumber, reason: reason, alert_type: alertType })
        });
        
        if (res.success) {
            showToast(`Đã thêm ${plateNumber}`, "success");
            closeModal();
            loadWatchlist();
            loadStats();
        } else {
            showToast("Thất bại: " + res.message, "error");
        }
    } catch (e) {
        showToast("Lỗi: " + e.message, "error");
    }
}

async function deleteWatchlistItem(plateNumber) {
    if (!confirm(`Xác nhận xóa "${plateNumber}"?`)) return;
    try {
        const res = await fetchJson(API_BASE + "/api/watchlist?plate_number=" + encodeURIComponent(plateNumber), {
            method: "DELETE",
        });
        if (res.success) {
            showToast("Đã xóa", "success");
            loadWatchlist();
            loadStats();
        }
    } catch (e) {
        showToast("Lỗi: " + e.message, "error");
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
        const res = await fetchJson(API_BASE + "/api/watchlist", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate_number: plateNumber, reason: reason, alert_type: alertType })
        });
        
        if (res.success) {
            showToast("Đã cập nhật", "success");
            closeEditModal();
            loadWatchlist();
        }
    } catch (e) {
        showToast("Lỗi: " + e.message, "error");
    }
}

async function importWatchlist() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.csv';
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const res = await fetch(API_BASE + "/api/watchlist/import", {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            if (result.success) {
                showToast(result.message, 'success');
                loadWatchlist();
                loadStats();
            } else {
                showToast("Import thất bại: " + result.message, 'error');
            }
        } catch (e) {
            showToast("Lỗi: " + e.message, 'error');
        }
    };
    input.click();
}

async function exportWatchlist() {
    window.location.href = API_BASE + "/api/watchlist/export?format=txt";
    showToast("Đang tải file ...", "success");
}

// ==================== ALERTS ====================

async function loadAlerts() {
    const container = document.getElementById("alertsContent");
    container.innerHTML = '<div class="loading">Đang tải...</div>';
    
    try {
        const res = await fetchJson(API_BASE + "/api/alerts");
        container.innerHTML = "";
        
        if (res && res.success && res.data && res.count > 0) {
            res.data.forEach(alert => {
                const div = document.createElement("div");
                div.className = "alert-card danger";
                
                const statusBadge = alert.resolved 
                    ? '<span style="color: var(--success)">✅ Đã xử lý</span>'
                    : '<span style="color: var(--danger)">⚠️ Chưa xử lý</span>';
                
                div.innerHTML = `
                    <div class="alert-content">
                        <h4>🚨 ${alert.plate_number}</h4>
                        <p><strong>Loại:</strong> ${alert.alert_type}</p>
                        <p>${alert.message}</p>
                        <p><strong>Trạng thái:</strong> ${statusBadge}</p>
                        ${alert.resolved_at ? `<p><strong>Xử lý lúc:</strong> ${formatDate(alert.resolved_at)}</p>` : ''}
                        <small>🕐 ${formatDate(alert.timestamp)}</small>
                    </div>
                    ${!alert.resolved ? `<button class="success" onclick="resolveAlert(${alert.id})">✅ Xử lý</button>` : ''}
                `;
                container.appendChild(div);
            });
        } else {
            container.innerHTML = '<div class="no-data">Không có cảnh báo</div>';
        }
    } catch (e) {
        container.innerHTML = `<div class="error">❌ Lỗi: ${e.message}</div>`;
    }
}

async function resolveAlert(id) {
    try {
        const res = await fetchJson(API_BASE + `/api/alerts/${id}/resolve`, {
            method: 'PUT',
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ resolved_by: 'dashboard_user' })
        });
        
        if (res.success) {
            showToast("Đã xử lý", "success");
            loadAlerts();
            loadStats();
        }
    } catch (e) {
        showToast("Lỗi: " + e.message, "error");
    }
}

// ==================== MODAL & TAB ====================

function closeModal() {
    document.getElementById("addWatchlistModal").classList.remove("active");
}

function closeEditModal() {
    document.getElementById("editWatchlistModal").classList.remove("active");
}

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
    document.querySelector(`.tab[onclick*="${tab}"]`)?.classList?.add("active");
    document.getElementById(tab + "-section")?.classList?.add("active");
    
    if (tab === "detection") loadDetections();
    if (tab === "watchlist") loadWatchlist();
    if (tab === "alerts") loadAlerts();
}