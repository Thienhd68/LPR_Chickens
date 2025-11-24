"""
Config Module - Simplified Version
Chỉ giữ lại 4 loại camera: Webcam, Phone, Video, Image
"""
import os
from pathlib import Path

class Config:
    """Cấu hình hệ thống LPR - Phiên bản đơn giản"""
    
    # ==================== FLASK CONFIG ====================
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'lpr-secret-key-2024'
    DEBUG = True
    
    # ==================== DATABASE CONFIG ====================
    DATABASE_PATH = 'license_plates.db'
    
    # ==================== FOLDER CONFIG ====================
    DETECTED_PLATES_FOLDER = 'detected_plates'
    UPLOAD_FOLDER = 'uploads'
    LOG_FOLDER = 'logs'
    VIDEO_FOLDER = 'videos'
    IMAGE_FOLDER = 'images'
    
    # ==================== DETECTION CONFIG ====================
    DETECTION_COOLDOWN = 60  # frames
    YOLO_CONFIDENCE = 0.50
    OCR_MAX_RETRIES = 4
    
    # ==================== MODEL CONFIG ====================
    LP_DETECTOR_MODEL = 'model/LP_detector_nano_61.pt'
    LP_OCR_MODEL = 'model/LP_ocr_nano_62.pt'
    
    # ==================== VIDEO/CAMERA CONFIG ====================
    DEFAULT_VIDEO_WIDTH = 1280
    DEFAULT_VIDEO_HEIGHT = 720
    DEFAULT_FPS = 30
    CAMERA_TIMEOUT = 5
    FRAME_SKIP = 3
    ENABLE_PREVIEW = False  # Tắt preview window để chạy headless
    
    # ==================== CAMERA TYPES (CHỈ 4 LOẠI) ====================
    CAMERA_TYPES = {
        'webcam': 'Webcam/USB Camera',
        'phone': 'Phone Camera (DroidCam)',
        'video': 'Video File',
        'image': 'Image/Folder'
    }
    
    # ==================== WATCHLIST CONFIG ====================
    WATCHLIST_FILE = 'watchlist.txt'
    ALLOWED_ALERT_TYPES = ['info', 'warning', 'danger']
    
    # ==================== ALERT CONFIG ====================
    ALERT_SOUND_ENABLED = True
    ALERT_DISPLAY_FRAMES = 100
    AUTO_PAUSE_ON_ALERT = False
    
    # ==================== FILE UPLOAD CONFIG ====================
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'bmp'}
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
    
    # ==================== LOGGING CONFIG ====================
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/lpr_system.log'
    
    # ==================== STATE FILE ====================
    STATE_FILE = 'detection_state.json'
    
    @staticmethod
    def init_app(app=None):
        """Khởi tạo folders"""
        folders = [
            Config.DETECTED_PLATES_FOLDER,
            Config.UPLOAD_FOLDER,
            Config.LOG_FOLDER,
            Config.VIDEO_FOLDER,
            Config.IMAGE_FOLDER
        ]
        
        for folder in folders:
            Path(folder).mkdir(parents=True, exist_ok=True)
        
        # Tạo watchlist file
        if not os.path.exists(Config.WATCHLIST_FILE):
            with open(Config.WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                f.write("# Watchlist\n")
        
        # Tạo state file
        if not os.path.exists(Config.STATE_FILE):
            import json
            with open(Config.STATE_FILE, 'w') as f:
                json.dump({'running': False}, f)
        
        if app:
            app.config.from_object(Config)
    
    @staticmethod
    def validate_camera_source(source_type, source_value):
        """Validate camera source"""
        if source_type == 'webcam':
            try:
                camera_id = int(source_value)
                if camera_id < 0:
                    return False, "Camera ID phải >= 0"
                return True, "OK"
            except ValueError:
                return False, "Camera ID phải là số"
        
        elif source_type == 'phone':
            if not source_value.startswith(('http://', 'https://')):
                return False, "URL phải bắt đầu bằng http:// hoặc https://"
            return True, "OK"
        
        elif source_type == 'video':
            if not os.path.exists(source_value):
                return False, f"File không tồn tại: {source_value}"
            ext = source_value.split('.')[-1].lower()
            if ext not in Config.ALLOWED_VIDEO_EXTENSIONS:
                return False, f"Extension không hợp lệ"
            return True, "OK"
        
        elif source_type == 'image':
            if not os.path.exists(source_value):
                return False, f"File/Folder không tồn tại"
            return True, "OK"
        
        else:
            return False, f"Loại nguồn không hỗ trợ: {source_type}"
    
    @staticmethod
    def allowed_file(filename, file_type='video'):
        """Kiểm tra file extension"""
        if '.' not in filename:
            return False
        
        ext = filename.rsplit('.', 1)[1].lower()
        
        if file_type == 'video':
            return ext in Config.ALLOWED_VIDEO_EXTENSIONS
        elif file_type == 'image':
            return ext in Config.ALLOWED_IMAGE_EXTENSIONS
        else:
            return False


# ==================== CAMERA INSTRUCTIONS ====================

CAMERA_SETUP_INSTRUCTIONS = {
    'webcam': """
    📹 WEBCAM / USB CAMERA
    
    1. Cắm camera USB vào máy tính
    2. Camera ID thường là:
       - Camera đầu tiên: 0
       - Camera thứ hai: 1
       - Camera thứ ba: 2
    3. Click "Quét Camera" để tìm tự động
    4. Chọn camera và click "Test"
    """,
    
    'phone': """
    📱 PHONE CAMERA (DroidCam)
    
    1. Tải app "DroidCam" trên điện thoại
       - Android: Google Play Store
       - iOS: App Store
    
    2. Mở app, chọn "Browser IP Cam"
    
    3. Lấy URL hiển thị trong app
       Format: http://192.168.1.XXX:4747/video
    
    4. Paste URL vào ô input
    
    ⚠️ LƯU Ý:
    - Điện thoại và máy tính phải cùng WiFi
    - Tắt firewall nếu không kết nối được
    """,
    
    'video': """
    🎬 VIDEO FILE
    
    1. Click "📤 Chọn file video"
    2. Chọn file video từ máy tính
    3. Hệ thống sẽ tự động upload
    
    Supported formats:
    - MP4, AVI, MOV, MKV
    - Max size: 500MB
    """,
    
    'image': """
    🖼️ IMAGE / FOLDER
    
    Cách 1: Single Image
    1. Click "📤 Chọn ảnh"
    2. Chọn 1 ảnh chứa biển số
    
    Cách 2: Multiple Images
    1. Click "📤 Chọn ảnh"
    2. Chọn nhiều ảnh cùng lúc (Ctrl + Click)
    3. Hệ thống sẽ xử lý tuần tự
    
    Supported formats:
    - JPG, JPEG, PNG, BMP
    """
}