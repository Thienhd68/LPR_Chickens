from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)  # Cho phép frontend truy cập từ domain khác

DB_PATH = 'license_plates.db'

# ===================== HELPER FUNCTIONS =====================
def get_db_connection():
    """Tạo kết nối database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Trả về dict thay vì tuple
    return conn

def dict_from_row(row):
    """Chuyển SQLite Row thành dictionary"""
    return {
        'id': row['id'],
        'plate_number': row['plate_number'],
        'timestamp': row['timestamp'],
        'frame_number': row['frame_number'],
        'confidence': row['confidence'],
        'image_path': row['image_path'],
        'source': row['source']
    }

# ===================== API ENDPOINTS =====================

@app.route('/')
def home():
    """Trang chủ API"""
    return jsonify({
        'message': 'License Plate Detection API',
        'version': '1.0',
        'endpoints': {
            'GET /api/plates': 'Lấy danh sách tất cả biển số',
            'GET /api/plates/recent?limit=10': 'Lấy biển số gần nhất',
            'GET /api/plates/<id>': 'Lấy thông tin 1 biển số',
            'GET /api/plates/search?q=29A': 'Tìm kiếm biển số',
            'GET /api/stats': 'Thống kê tổng quan',
            'GET /api/stats/today': 'Thống kê hôm nay',
            'GET /api/image/<id>': 'Lấy ảnh biển số',
            'DELETE /api/plates/<id>': 'Xóa 1 biển số',
            'DELETE /api/plates/all': 'Xóa tất cả (cẩn thận!)'
        }
    })

@app.route('/api/plates', methods=['GET'])
def get_all_plates():
    """Lấy tất cả biển số (có phân trang)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Đếm tổng số
    total = conn.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
    
    # Lấy dữ liệu
    plates = conn.execute('''
        SELECT * FROM detected_plates 
        ORDER BY timestamp DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'data': [dict_from_row(plate) for plate in plates]
    })

@app.route('/api/plates/recent', methods=['GET'])
def get_recent_plates():
    """Lấy biển số gần nhất"""
    limit = request.args.get('limit', 10, type=int)
    
    conn = get_db_connection()
    plates = conn.execute('''
        SELECT * FROM detected_plates 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'count': len(plates),
        'data': [dict_from_row(plate) for plate in plates]
    })

@app.route('/api/plates/<int:plate_id>', methods=['GET'])
def get_plate_by_id(plate_id):
    """Lấy thông tin 1 biển số theo ID"""
    conn = get_db_connection()
    plate = conn.execute('SELECT * FROM detected_plates WHERE id = ?', (plate_id,)).fetchone()
    conn.close()
    
    if plate is None:
        return jsonify({'success': False, 'message': 'Không tìm thấy biển số'}), 404
    
    return jsonify({
        'success': True,
        'data': dict_from_row(plate)
    })

@app.route('/api/plates/search', methods=['GET'])
def search_plates():
    """Tìm kiếm biển số"""
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'success': False, 'message': 'Vui lòng nhập từ khóa tìm kiếm'}), 400
    
    conn = get_db_connection()
    plates = conn.execute('''
        SELECT * FROM detected_plates 
        WHERE plate_number LIKE ? 
        ORDER BY timestamp DESC
    ''', (f'%{query}%',)).fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'query': query,
        'count': len(plates),
        'data': [dict_from_row(plate) for plate in plates]
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Thống kê tổng quan"""
    conn = get_db_connection()
    
    total = conn.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
    unique = conn.execute('SELECT COUNT(DISTINCT plate_number) FROM detected_plates').fetchone()[0]
    
    # Top 5 biển số xuất hiện nhiều nhất
    top_plates = conn.execute('''
        SELECT plate_number, COUNT(*) as count 
        FROM detected_plates 
        GROUP BY plate_number 
        ORDER BY count DESC 
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'data': {
            'total_detections': total,
            'unique_plates': unique,
            'top_plates': [{'plate': row[0], 'count': row[1]} for row in top_plates]
        }
    })

@app.route('/api/stats/today', methods=['GET'])
def get_today_stats():
    """Thống kê hôm nay"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    
    count = conn.execute('''
        SELECT COUNT(*) FROM detected_plates 
        WHERE DATE(timestamp) = ?
    ''', (today,)).fetchone()[0]
    
    plates = conn.execute('''
        SELECT * FROM detected_plates 
        WHERE DATE(timestamp) = ?
        ORDER BY timestamp DESC
    ''', (today,)).fetchall()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'date': today,
        'count': count,
        'data': [dict_from_row(plate) for plate in plates]
    })

@app.route('/api/image/<int:plate_id>', methods=['GET'])
def get_plate_image(plate_id):
    """Lấy ảnh biển số"""
    conn = get_db_connection()
    plate = conn.execute('SELECT image_path FROM detected_plates WHERE id = ?', (plate_id,)).fetchone()
    conn.close()
    
    if plate is None or plate['image_path'] is None:
        return jsonify({'success': False, 'message': 'Không tìm thấy ảnh'}), 404
    
    image_path = plate['image_path']
    
    if not os.path.exists(image_path):
        return jsonify({'success': False, 'message': 'File ảnh không tồn tại'}), 404
    
    return send_file(image_path, mimetype='image/jpeg')

@app.route('/api/plates/<int:plate_id>', methods=['DELETE'])
def delete_plate(plate_id):
    """Xóa 1 biển số"""
    conn = get_db_connection()
    
    # Lấy thông tin ảnh trước khi xóa
    plate = conn.execute('SELECT image_path FROM detected_plates WHERE id = ?', (plate_id,)).fetchone()
    
    if plate is None:
        conn.close()
        return jsonify({'success': False, 'message': 'Không tìm thấy biển số'}), 404
    
    # Xóa file ảnh nếu có
    if plate['image_path'] and os.path.exists(plate['image_path']):
        os.remove(plate['image_path'])
    
    # Xóa record trong database
    conn.execute('DELETE FROM detected_plates WHERE id = ?', (plate_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f'Đã xóa biển số ID {plate_id}'
    })

@app.route('/api/plates/all', methods=['DELETE'])
def delete_all_plates():
    """Xóa tất cả biển số (CẨN THẬN!)"""
    # Yêu cầu xác nhận qua header
    confirm = request.headers.get('X-Confirm-Delete')
    
    if confirm != 'YES_DELETE_ALL':
        return jsonify({
            'success': False, 
            'message': 'Vui lòng thêm header X-Confirm-Delete: YES_DELETE_ALL để xác nhận'
        }), 400
    
    conn = get_db_connection()
    
    # Xóa tất cả ảnh
    plates = conn.execute('SELECT image_path FROM detected_plates WHERE image_path IS NOT NULL').fetchall()
    for plate in plates:
        if os.path.exists(plate['image_path']):
            os.remove(plate['image_path'])
    
    # Xóa tất cả records
    conn.execute('DELETE FROM detected_plates')
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Đã xóa tất cả biển số'
    })

# ===================== CHẠY SERVER =====================
if __name__ == '__main__':
    # Kiểm tra database có tồn tại không
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Cảnh báo: Database {DB_PATH} không tồn tại!")
        print("   Vui lòng chạy chương trình chính trước để tạo database.")
    
    print("\n🚀 License Plate API Server")
    print("="*50)
    print("📡 API đang chạy tại: http://localhost:5000")
    print("📚 Xem danh sách endpoints tại: http://localhost:5000")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)