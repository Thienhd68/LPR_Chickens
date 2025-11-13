# Import thêm 'render_template'
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
import sys

# Import database manager
sys.path.append(os.path.dirname(__file__))
try:
    from database_manager import AdvancedLicensePlateDB
    db = AdvancedLicensePlateDB()
    print("✅ Database manager loaded successfully")
except ImportError as e:
    print(f"⚠️  Warning: Could not load database_manager: {e}")
    print("   API will run with basic functionality only")
    db = None

app = Flask(__name__)

# CRITICAL: Enable CORS for all routes
# Cấu hình này rất quan trọng để dashboard (từ server) có thể gọi API (cũng từ server)
CORS(app, resources={
    r"/api/*": {
        "origins": "*", 
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# ==================== HELPER FUNCTIONS ====================
def get_db_connection():
    """Create database connection"""
    db_path = 'license_plates.db'
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found: {db_path}")
        return None
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    """Convert SQLite Row to dictionary"""
    return dict(row) if hasattr(row, 'keys') else row

# ==================== WEB ROUTE (Phục vụ Dashboard) ====================
@app.route('/')
def index():
    """Phục vụ trang dashboard HTML (file templates/index.html)"""
    return render_template('index.html')

# ==================== API ENDPOINTS ====================
@app.route('/api')
def api_home():
    """API Home (Tài liệu) - Đã chuyển từ / sang /api"""
    return jsonify({
        'status': 'online',
        'message': 'Advanced License Plate Detection API v2.0',
        'database': 'connected' if os.path.exists('license_plates.db') else 'not found',
        'endpoints': {
            'GET /': 'Trang Dashboard',
            'GET /api': 'Tài liệu API (trang này)',
            'GET /api/stats': 'Get statistics',
            'GET /api/plates/recent': 'Get recent plates',
            'GET /api/plates/search?q=': 'Search plates',
            'GET /api/watchlist': 'Get watchlist',
            'GET /api/alerts': 'Get alerts',
        }
    })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'database': os.path.exists('license_plates.db'),
        'timestamp': datetime.now().isoformat()
    })

# ==================== PLATES ENDPOINTS ====================
@app.route('/api/plates/recent', methods=['GET'])
def get_recent_plates():
    """Get recent plates"""
    try:
        limit = request.args.get('limit', 20, type=int)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database not found. Please run the main program first to create database.',
                'data': []
            }), 200
        
        plates = conn.execute('''
            SELECT * FROM detected_plates 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(plates),
            'data': [dict(plate) for plate in plates]
        })
    except Exception as e:
        print(f"❌ Error in get_recent_plates: {e}")
        return jsonify({
            'success': False,
            'message': str(e),
            'data': []
        }), 200

@app.route('/api/plates/search', methods=['GET'])
def search_plates():
    """Search plates"""
    try:
        query = request.args.get('q', '')
        
        if not query:
            return jsonify({
                'success': False,
                'message': 'Please provide search query',
                'data': []
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database not found',
                'data': []
            }), 200
        
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
            'data': [dict(plate) for plate in plates]
        })
    except Exception as e:
        print(f"❌ Error in search_plates: {e}")
        return jsonify({
            'success': False,
            'message': str(e),
            'data': []
        }), 200

# ==================== STATS ENDPOINTS ====================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': True,
                'data': {
                    'total': 0, 'unique': 0, 'watchlist_count': 0,
                    'alerts_pending': 0, 'today': 0, 'top_plates': []
                }
            })
        
        stats = {}
        stats['total'] = conn.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
        stats['unique'] = conn.execute('SELECT COUNT(DISTINCT plate_number) FROM detected_plates').fetchone()[0]
        
        try:
            stats['watchlist_count'] = conn.execute('SELECT COUNT(*) FROM watchlist WHERE active = 1').fetchone()[0]
        except:
            stats['watchlist_count'] = 0
        
        try:
            stats['alerts_pending'] = conn.execute('SELECT COUNT(*) FROM alerts WHERE resolved = 0').fetchone()[0]
        except:
            stats['alerts_pending'] = 0
        
        stats['today'] = conn.execute('''
            SELECT COUNT(*) FROM detected_plates 
            WHERE DATE(timestamp) = DATE('now')
        ''').fetchone()[0]
        
        top = conn.execute('''
            SELECT plate_number, COUNT(*) as count 
            FROM detected_plates 
            GROUP BY plate_number 
            ORDER BY count DESC 
            LIMIT 5
        ''').fetchall()
        stats['top_plates'] = [{'plate': row[0], 'count': row[1]} for row in top]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        print(f"❌ Error in get_stats: {e}")
        return jsonify({
            'success': True,
            'data': {
                'total': 0, 'unique': 0, 'watchlist_count': 0,
                'alerts_pending': 0, 'today': 0, 'top_plates': []
            }
        })

@app.route('/api/stats/today', methods=['GET'])
def get_today_stats():
    """Get today's statistics"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': True, 'date': today, 'count': 0, 'data': []
            })
        
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
            'data': [dict(plate) for plate in plates]
        })
    except Exception as e:
        print(f"❌ Error in get_today_stats: {e}")
        return jsonify({
            'success': True,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'count': 0,
            'data': []
        })

# ==================== WATCHLIST ENDPOINTS ====================
@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    """Get watchlist"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': True, 'count': 0, 'data': []})
        
        try:
            watchlist = conn.execute('SELECT * FROM watchlist WHERE active = 1 ORDER BY added_date DESC').fetchall()
        except:
            conn.close()
            return jsonify({'success': True, 'count': 0, 'data': []})
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(watchlist),
            'data': [dict(item) for item in watchlist]
        })
    except Exception as e:
        print(f"❌ Error in get_watchlist: {e}")
        return jsonify({'success': True, 'count': 0, 'data': []})

@app.route('/api/watchlist', methods=['POST'])
def add_watchlist():
    """Add to watchlist"""
    try:
        data = request.get_json()
        
        if not data or 'plate_number' not in data:
            return jsonify({'success': False, 'message': 'Missing plate_number'}), 400
        
        if db:
            success, result = db.add_to_watchlist(
                data['plate_number'],
                data.get('reason', ''),
                data.get('alert_type', 'warning')
            )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Added to watchlist',
                    'watchlist_id': result
                })
            else:
                return jsonify({'success': False, 'message': result}), 400
        else:
            return jsonify({'success': False, 'message': 'Database manager not available'}), 500
    except Exception as e:
        print(f"❌ Error in add_watchlist: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/watchlist/<plate_number>', methods=['DELETE'])
def remove_watchlist(plate_number):
    """Remove from watchlist"""
    try:
        if db:
            success = db.remove_from_watchlist(plate_number)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': f'Removed {plate_number} from watchlist'
                })
            else:
                return jsonify({'success': False, 'message': 'Not found in watchlist'}), 404
        else:
            return jsonify({'success': False, 'message': 'Database manager not available'}), 500
    except Exception as e:
        print(f"❌ Error in remove_watchlist: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ALERTS ENDPOINTS ====================
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get alerts"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': True, 'count': 0, 'data': []})
        
        try:
            alerts = conn.execute('SELECT * FROM alerts WHERE resolved = 0 ORDER BY timestamp DESC').fetchall()
        except:
            conn.close()
            return jsonify({'success': True, 'count': 0, 'data': []})
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(alerts),
            'data': [dict(alert) for alert in alerts]
        })
    except Exception as e:
        print(f"❌ Error in get_alerts: {e}")
        return jsonify({'success': True, 'count': 0, 'data': []})

# ==================== IMAGE ENDPOINT ====================
@app.route('/api/image/<int:plate_id>', methods=['GET'])
def get_plate_image(plate_id):
    """Get plate image"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database not found'}), 404
        
        plate = conn.execute('SELECT image_path FROM detected_plates WHERE id = ?', (plate_id,)).fetchone()
        conn.close()
        
        if plate is None or plate['image_path'] is None:
            return jsonify({'success': False, 'message': 'Image not found'}), 404
        
        image_path = plate['image_path']
        
        if not os.path.exists(image_path):
            return jsonify({'success': False, 'message': 'Image file does not exist'}), 404
        
        return send_file(image_path, mimetype='image/jpeg')
    except Exception as e:
        print(f"❌ Error in get_plate_image: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== DELETE ENDPOINTS ====================
@app.route('/api/plates/<int:plate_id>', methods=['DELETE'])
def delete_plate(plate_id):
    """Delete a plate"""
    try:
        if db:
            reason = request.args.get('reason', 'User deleted')
            success, message = db.delete_plate(plate_id, reason)
            
            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message}), 404
        else:
            return jsonify({'success': False, 'message': 'Database manager not available'}), 500
    except Exception as e:
        print(f"❌ Error in delete_plate: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(error):
    # Trả về JSON cho các lỗi API
    if request.path.startswith('/api/'):
        return jsonify({
            'success': False,
            'message': 'Endpoint not found',
            'error': str(error)
        }), 404
    # Trả về trang HTML cho các lỗi khác (nếu có)
    return render_template('index.html'), 404 # Hoặc một trang 404.html riêng

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': 'Internal server error',
        'error': str(error)
    }), 500

# ==================== RUN SERVER ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 License Plate API Server v2.0 (Đã chuẩn hóa)")
    print("="*60)
    
    if os.path.exists('license_plates.db'):
        conn = sqlite3.connect('license_plates.db')
        count = conn.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
        conn.close()
        print(f"✅ Database: license_plates.db ({count} records)")
    else:
        print("⚠️  Database: Not found - Will be created when main program runs")
    
    print(f"🌐 Dashboard chạy tại: http://localhost:5000/")
    print(f"📡 API docs chạy tại: http://localhost:5000/api")
    print(f"🔍 Test endpoint: http://localhost:5000/api/health")
    print("="*60 + "\n")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )