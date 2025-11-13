import os

class Config:
    """Cấu hình ứng dụng"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DEBUG = True
    
    # Database
    DATABASE_PATH = 'license_plates.db'
    
    # Upload folders
    DETECTED_PLATES_FOLDER = 'detected_plates'
    UPLOAD_FOLDER = 'uploads'
    
    # API
    API_PREFIX = '/api'
    CORS_ORIGINS = '*'  # Trong production nên chỉ định cụ thể
    
    # Detection
    DETECTION_COOLDOWN = 30  # frames
    YOLO_CONFIDENCE = 0.60
    
    # Models
    LP_DETECTOR_MODEL = 'model/LP_detector.pt'
    LP_OCR_MODEL = 'model/LP_ocr.pt'
    
    # Video
    DEFAULT_VIDEO_WIDTH = 1280
    DEFAULT_VIDEO_HEIGHT = 720
    DEFAULT_FPS = 20
    
    # Watchlist
    WATCHLIST_FILE = 'watchlist.txt'
    
    @staticmethod
    def init_app(app):
        """Khởi tạo các thư mục cần thiết"""
        os.makedirs(Config.DETECTED_PLATES_FOLDER, exist_ok=True)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)