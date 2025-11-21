"""
Flask API Server - Cung cấp API & Frontend Dashboard
"""

from flask import Flask, render_template, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime, time
import sys
import logging
import threading
import argparse
from werkzeug.utils import secure_filename
from flask import Response 

# Import modules
from config import Config, CAMERA_SETUP_INSTRUCTIONS
from database_manager import AdvancedLicensePlateDB
from camera_manager import list_available_cameras, test_camera_source
from main_advanced import LicensePlateDetector

# ==================== SETUP LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== INIT FLASK ====================

app = Flask(__name__)
Config.init_app(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Load database
db = None
try:
    db = AdvancedLicensePlateDB(Config.DATABASE_PATH)
    logger.info("✅ Database loaded")
except Exception as e:
    logger.error(f"❌ Database error: {e}")

# ==================== GLOBAL VARIABLES ====================

global_detector = None
detector_thread = None

# ==================== HELPER FUNCTIONS ====================

def success_response(data=None, message="Success", **kwargs):
    """Response thành công"""
    response = {'success': True, 'message': message}
    if data is not None:
        response['data'] = data
    response.update(kwargs)
    return jsonify(response)

def error_response(message="Error", status=400, **kwargs):
    """Response lỗi"""
    response = {'success': False, 'message': message}
    response.update(kwargs)
    return jsonify(response), status

def read_state_file():
    """Đọc trạng thái detection từ file JSON"""
    try:
        if os.path.exists(Config.STATE_FILE):
            with open(Config.STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            'running': False,
            'source_type': None,
            'source_value': None,
            'start_time': None,
            'frames_processed': 0,
            'detections_count': 0
        }
    except Exception as e:
        logger.error(f"❌ Error reading state: {e}")
        return {'running': False}

def write_state_file(state):
    """Ghi trạng thái detection vào file JSON"""
    try:
        with open(Config.STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"❌ Error writing state: {e}")
        return False

def generate_frames():
    """Hàm generator để stream video MJPEG"""
    global global_detector

    while True:
        if global_detector and global_detector.running:
            frame_bytes = global_detector.get_jpeg()
            
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                # Nếu chưa có frame, chờ một chút
                time.sleep(0.1)
        else:
            # Detection đã dừng
            break

# ==================== WEB ROUTES ====================

@app.route('/')
def index():
    """Serve dashboard HTML"""
    return render_template('index.html')

@app.route('/videos/<path:filename>')
def serve_video_file(filename):
    """Route để trình duyệt truy cập file video"""
    return send_from_directory(Config.VIDEO_FOLDER, filename)

# ==================== CAMERA CONTROL APIs ====================

@app.route('/api/cameras/available', methods=['GET'])
def get_available_cameras_api():
    """Quét danh sách webcam khả dụng"""
    try:
        max_check = request.args.get('max_check', 5, type=int)
        cameras = list_available_cameras(max_check)
        
        return success_response(
            data=cameras,
            count=len(cameras),
            message=f"Tìm thấy {len(cameras)} camera"
        )
    except Exception as e:
        logger.error(f"❌ Error scanning cameras: {e}")
        return error_response(str(e), 500)

@app.route('/api/cameras/test', methods=['POST'])
def test_camera():
    """Test kết nối camera"""
    try:
        data = request.get_json() or {}
        
        source_type = data.get('source_type')
        source_value = data.get('source_value')
        
        if not source_type or source_value is None:
            return error_response("Thiếu source_type hoặc source_value", 400)
        
        # Test connection
        success, message, info = test_camera_source(source_type, str(source_value))
        
        if success:
            return success_response(data=info, message=message)
        else:
            return error_response(message, 400)
    
    except Exception as e:
        logger.error(f"❌ Error testing camera: {e}")
        return error_response(str(e), 500)

@app.route('/api/cameras/instructions/<source_type>', methods=['GET'])
def get_camera_instructions(source_type):
    """Lấy hướng dẫn setup camera"""
    try:
        if source_type not in CAMERA_SETUP_INSTRUCTIONS:
            return error_response(f"Unknown camera type: {source_type}", 404)
        
        return success_response(
            data={
                'source_type': source_type,
                'instructions': CAMERA_SETUP_INSTRUCTIONS[source_type]
            }
        )
    except Exception as e:
        return error_response(str(e), 500)

# ==================== DETECTION CONTROL APIs ====================

@app.route('/api/detection/status', methods=['GET'])
def get_detection_status():
    """Lấy trạng thái detection hiện tại"""
    try:
        state = read_state_file()
        return success_response(data=state)
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/detection/start', methods=['POST'])
def start_detection():
    global global_detector, detector_thread

    try:
        # FIX: Sửa typo "ruuning" → "running"
        if global_detector and global_detector.running:
            global_detector.stop()

        data = request.get_json() or {}
        
        source_type = data.get('source_type', 'webcam')
        source_value = data.get('source_value', 0)

        # Giả lập tham số args
        class Args:
            source_type = data.get('source_type')
            source_value = str(data.get('source_value'))
            save = False
            save_crops = data.get('save_crops', True)
            watchlist = None

        args = Args()

        # Khởi tạo detector
        global_detector = LicensePlateDetector(args)

        # Mở camera
        if global_detector.open_camera(args.source_type, args.source_value):
            # Chạy detector trong Thread riêng
            detector_thread = threading.Thread(target=global_detector.run)
            detector_thread.daemon = True
            detector_thread.start()

            logger.info(f"✅ Detection thread started: {source_type}={source_value}")

            # Update state file
            state = {
                'running': True,
                'source_type': source_type,
                'source_value': str(source_value),
                'start_time': datetime.now().isoformat()
            }
            write_state_file(state)

            return success_response(message="Detection đã bắt đầu", data=state)
        else:
            return error_response("Không thể mở camera source", 400)
        
    except Exception as e:
        logger.error(f"❌ Error starting detection: {e}")
        return error_response(str(e), 500)

@app.route('/api/detection/stop', methods=['POST'])
def stop_detection():
    """Dừng detection"""
    global global_detector
    try:
        if global_detector:
            global_detector.stop()
            global_detector = None

        state = read_state_file()
        state['running'] = False
        write_state_file(state)

        return success_response(message="Detection đã dừng")
    
    except Exception as e:
        logger.error(f"❌ Error stopping detection: {e}")
        return error_response(str(e), 500)

@app.route('/video_feed')
def video_feed():
    """"Route trả về luồng video MJPEG"""
    logger.info("video_feed route called")
    global global_detector
    if not global_detector:
        logger.warning("⚠️  global_detector is None")
        return error_response("Detection not running", 400)
    
    if not global_detector.running:
        logger.warning("⚠️  global_detector.running is False")
        return error_response("Detection not running", 400)
    
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ==================== FILE UPLOAD APIs ====================

@app.route('/api/upload/video', methods=['POST'])
def upload_video():
    """Upload video file"""
    try:
        if 'file' not in request.files:
            return error_response('Không có file', 400)
        
        file = request.files['file']
        
        if file.filename == '':
            return error_response('Chưa chọn file', 400)
        
        if not Config.allowed_file(file.filename, 'video'):
            return error_response(f'File type không hỗ trợ', 400)
        
        # Save file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(Config.VIDEO_FOLDER, filename)
        
        file.save(filepath)
        logger.info(f"✅ Video uploaded: {filename}")
        
        return success_response(
            message=f"Upload: {filename}",
            data={
                'filename': filename,
                'filepath': filepath,
                'size': os.path.getsize(filepath)
            }
        )
    
    except Exception as e:
        logger.error(f"❌ Error uploading video: {e}")
        return error_response(str(e), 500)

@app.route('/api/upload/image', methods=['POST'])
def upload_image():
    """Upload image file"""
    try:
        if 'file' not in request.files:
            return error_response('Không có file', 400)
        
        file = request.files['file']
        
        if file.filename == '':
            return error_response('Chưa chọn file', 400)
        
        if not Config.allowed_file(file.filename, 'image'):
            return error_response(f'File type không hỗ trợ', 400)
        
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(Config.IMAGE_FOLDER, filename)
        
        file.save(filepath)
        logger.info(f"✅ Image uploaded: {filename}")
        
        return success_response(
            message=f"Upload: {filename}",
            data={
                'filename': filename,
                'filepath': filepath,
                'size': os.path.getsize(filepath)
            }
        )
    
    except Exception as e:
        logger.error(f"❌ Error uploading image: {e}")
        return error_response(str(e), 500)

# ==================== DATA QUERY APIs ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Lấy thống kê chung"""
    try:
        if not db:
            return success_response(data={
                'total': 0, 'unique': 0, 'watchlist_count': 0,
                'alerts_pending': 0, 'today': 0, 'top_plates': []
            })
        
        stats = db.get_statistics(detailed=False)
        return success_response(data=stats)
    except Exception as e:
        logger.error(f"❌ Error in get_stats: {e}")
        return success_response(data={
            'total': 0, 'unique': 0, 'watchlist_count': 0,
            'alerts_pending': 0, 'today': 0, 'top_plates': []
        })

@app.route('/api/plates/recent', methods=['GET'])
def get_recent_plates():
    """Lấy biển số gần đây"""
    try:
        limit = request.args.get('limit', 20, type=int)
        
        if not db:
            return success_response(data=[], count=0)
        
        plates = db.get_recent_plates(limit=limit)
        return success_response(data=plates, count=len(plates))
    except Exception as e:
        logger.error(f"❌ Error in get_recent_plates: {e}")
        return error_response(str(e), 500)

@app.route('/api/plates/search', methods=['GET'])
def search_plates():
    """Tìm kiếm biển số"""
    try:
        query = request.args.get('query', '').strip()
        limit = request.args.get('limit', 50, type=int)
        
        if not query:
            return error_response('Query is required', 400)
        
        if not db:
            return success_response(data=[], count=0)
        
        plates = db.search_plates(query, limit=limit)
        return success_response(data=plates, count=len(plates))
    except Exception as e:
        logger.error(f"❌ Error in search_plates: {e}")
        return error_response(str(e), 500)

@app.route('/api/image/<int:plate_id>')
def get_plate_image(plate_id):
    """Trả về ảnh biển số theo ID"""
    try:
        if not db:
            return error_response('Database not available', 503)
        
        # Lấy thông tin plate từ DB
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_path FROM detected_plates WHERE id = ?', (plate_id,))
            result = cursor.fetchone()
            
            if result and result['image_path'] and os.path.exists(result['image_path']):
                return send_file(result['image_path'], mimetype='image/jpeg')
            else:
                # Trả về placeholder nếu không có ảnh
                placeholder_path = 'static/images/placeholder.png'
                if os.path.exists(placeholder_path):
                    return send_file(placeholder_path, mimetype='image/png')
                else:
                    return error_response('Image not found', 404)
    except Exception as e:
        logger.error(f"Error getting image: {e}")
        return error_response(str(e), 500)

# ==================== WATCHLIST APIs ====================

@app.route('/api/watchlist', methods=['GET', 'POST', 'PUT', 'DELETE'])
def handle_watchlist():
    """Quản lý watchlist - GET/POST/PUT/DELETE"""
    try:
        if not db:
            return error_response('Database not available', 503)
        
        if request.method == 'GET':
            # Lấy watchlist
            watchlist = db.get_watchlist(active_only=True)
            return success_response(data=watchlist, count=len(watchlist))
        
        elif request.method == 'POST':
            # Thêm vào watchlist
            data = request.get_json() or {}
            plate = data.get('plate_number', '').upper().strip()
            reason = data.get('reason', '')
            alert_type = data.get('alert_type', 'warning')
            
            if not plate:
                return error_response('plate_number required', 400)
            
            success, msg = db.add_to_watchlist(plate, reason, alert_type)
            if success:
                logger.info(f"✅ Added to watchlist: {plate}")
                return success_response(message=f"Added {plate} to watchlist")
            else:
                return error_response(msg, 400)
        
        elif request.method == 'PUT':
            # Cập nhật watchlist
            data = request.get_json() or {}
            plate = data.get('plate_number', '').upper().strip()
            
            if not plate:
                return error_response('plate_number required', 400)
            
            success, msg = db.update_watchlist(
                plate, 
                reason=data.get('reason'),
                alert_type=data.get('alert_type'),
                active=data.get('active')
            )
            
            if success:
                logger.info(f"✅ Updated watchlist: {plate}")
                return success_response(message=msg)
            else:
                return error_response(msg, 400)
        
        elif request.method == 'DELETE':
            # Xóa khỏi watchlist
            plate = request.args.get('plate_number', '').upper().strip()
            
            if not plate:
                return error_response('plate_number required', 400)
            
            success = db.remove_from_watchlist(plate)
            if success:
                logger.info(f"✅ Removed from watchlist: {plate}")
                return success_response(message=f"Removed {plate}")
            else:
                return error_response('Not found', 404)
    
    except Exception as e:
        logger.error(f"❌ Watchlist error: {e}")
        return error_response(str(e), 500)

@app.route('/api/watchlist/import', methods=['POST'])
def import_watchlist():
    """Import watchlist từ file"""
    try:
        if 'file' not in request.files:
            return error_response('Không có file', 400)
        
        file = request.files['file']
        
        if file.filename == '':
            return error_response('Chưa chọn file', 400)
        
        # Save temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.txt') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        # Import from file
        result = db.import_watchlist_from_file(tmp_path)
        
        # Clean up
        os.remove(tmp_path)
        
        if result['success'] > 0:
            return success_response(
                message=f"Import thành công {result['success']} biển số",
                data=result
            )
        else:
            return error_response('Import thất bại', 400)
    
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return error_response(str(e), 500)

@app.route('/api/watchlist/export', methods=['GET'])
def export_watchlist():
    """Export watchlist ra CSV"""
    try:
        format = request.args.get('format', 'csv')
        
        # Create temp file
        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f'.{format}')
        tmp_path = tmp.name
        tmp.close()
        
        # Export
        success, message = db.export_watchlist_to_file(tmp_path, format=format)
        
        if success:
            return send_file(
                tmp_path,
                as_attachment=True,
                download_name=f'watchlist_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{format}',
                mimetype='text/csv' if format == 'csv' else 'text/plain'
            )
        else:
            return error_response(message, 500)
    
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        return error_response(str(e), 500)

# ==================== ALERTS APIs ====================

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Lấy alerts chưa xử lý"""
    try:
        if not db:
            return success_response(data=[], count=0)
        
        alerts = db.get_alerts(unresolved_only=False)  # Changed to False to show all alerts
        return success_response(data=alerts, count=len(alerts))
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['PUT'])
def resolve_alert(alert_id):
    """Giải quyết alert"""
    try:
        if not db:
            return error_response('Database not available', 503)
        
        data = request.get_json() or {}
        resolved_by = data.get('resolved_by', 'dashboard')
        notes = data.get('notes', '')
        
        success = db.resolve_alert(alert_id, resolved_by, notes)
        
        if success:
            logger.info(f"✅ Alert resolved: {alert_id}")
            return success_response(message='Alert resolved')
        else:
            return error_response('Alert not found', 404)
    except Exception as e:
        return error_response(str(e), 500)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return error_response('Endpoint not found', 404)
    return render_template('index.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ Internal error: {error}")
    return error_response('Internal server error', 500)

# ==================== RUN ====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 LPR API Server v1.0")
    print("="*60)
    
    if os.path.exists(Config.DATABASE_PATH):
        try:
            conn = sqlite3.connect(Config.DATABASE_PATH)
            count = conn.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
            conn.close()
            print(f"✅ Database: {Config.DATABASE_PATH} ({count} records)")
        except:
            print(f"⚠️  Database: {Config.DATABASE_PATH}")
    else:
        print(f"✅ Database will be created on first run")
    
    print(f"🌐 Dashboard: http://localhost:5000/")
    print(f"📡 API: http://localhost:5000/api/")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)