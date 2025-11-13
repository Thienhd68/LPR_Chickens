import sqlite3
from datetime import datetime
import os
from difflib import SequenceMatcher

class AdvancedLicensePlateDB:
    def __init__(self, db_path='license_plates.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Khởi tạo database với các bảng mở rộng"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Bảng biển số đã phát hiện
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                frame_number INTEGER,
                confidence REAL,
                image_path TEXT,
                source TEXT,
                is_watchlist INTEGER DEFAULT 0,
                alert_triggered INTEGER DEFAULT 0
            )
        ''')
        
        # Bảng danh sách theo dõi (watchlist)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT UNIQUE NOT NULL,
                reason TEXT,
                alert_type TEXT DEFAULT 'warning',
                added_date TEXT NOT NULL,
                last_seen TEXT,
                detection_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # Bảng cảnh báo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                alert_type TEXT,
                message TEXT,
                resolved INTEGER DEFAULT 0
            )
        ''')
        
        # Bảng lịch sử xóa (để khôi phục)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deleted_plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_id INTEGER,
                plate_number TEXT,
                timestamp TEXT,
                deleted_date TEXT,
                deleted_reason TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"✅ Database nâng cao đã sẵn sàng: {self.db_path}")
    
    # ==================== CHỨC NĂNG LƯU BIỂN SỐ ====================
    def save_plate(self, plate_number, frame_number, confidence=0.0, 
                   image_path=None, source='webcam'):
        """Lưu biển số và kiểm tra watchlist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Kiểm tra xem có trong watchlist không
        is_watchlist, watchlist_info = self.check_watchlist(plate_number)
        
        cursor.execute('''
            INSERT INTO detected_plates 
            (plate_number, timestamp, frame_number, confidence, image_path, source, is_watchlist)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (plate_number, timestamp, frame_number, confidence, image_path, source, int(is_watchlist)))
        
        plate_id = cursor.lastrowid
        
        # Nếu trong watchlist, tạo cảnh báo
        if is_watchlist:
            alert_type = watchlist_info['alert_type']
            reason = watchlist_info['reason']
            
            cursor.execute('''
                INSERT INTO alerts (plate_number, timestamp, alert_type, message)
                VALUES (?, ?, ?, ?)
            ''', (plate_number, timestamp, alert_type, 
                  f"Phát hiện biển số trong danh sách theo dõi: {reason}"))
            
            # Cập nhật watchlist
            cursor.execute('''
                UPDATE watchlist 
                SET last_seen = ?, detection_count = detection_count + 1
                WHERE plate_number = ?
            ''', (timestamp, plate_number))
            
            # Đánh dấu đã kích hoạt cảnh báo
            cursor.execute('''
                UPDATE detected_plates SET alert_triggered = 1 WHERE id = ?
            ''', (plate_id,))
        
        conn.commit()
        conn.close()
        
        return plate_id, is_watchlist
    
    # ==================== WATCHLIST ====================
    def add_to_watchlist(self, plate_number, reason='', alert_type='warning'):
        """Thêm biển số vào danh sách theo dõi"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            cursor.execute('''
                INSERT INTO watchlist (plate_number, reason, alert_type, added_date)
                VALUES (?, ?, ?, ?)
            ''', (plate_number, reason, alert_type, timestamp))
            conn.commit()
            watchlist_id = cursor.lastrowid
            conn.close()
            return True, watchlist_id
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Biển số đã có trong watchlist"
    
    def remove_from_watchlist(self, plate_number):
        """Xóa biển số khỏi watchlist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM watchlist WHERE plate_number = ?', (plate_number,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted > 0
    
    def get_watchlist(self, active_only=True):
        """Lấy danh sách watchlist"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('SELECT * FROM watchlist WHERE active = 1 ORDER BY added_date DESC')
        else:
            cursor.execute('SELECT * FROM watchlist ORDER BY added_date DESC')
        
        watchlist = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in watchlist]
    
    def check_watchlist(self, plate_number):
        """Kiểm tra biển số có trong watchlist không"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM watchlist WHERE plate_number = ? AND active = 1', (plate_number,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return True, dict(result)
        return False, None
    
    # ==================== SO SÁNH BIỂN SỐ ====================
    def find_similar_plates(self, plate_number, threshold=0.8):
        """Tìm biển số tương tự (fuzzy matching)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT plate_number FROM detected_plates')
        all_plates = cursor.fetchall()
        conn.close()
        
        similar_plates = []
        
        for row in all_plates:
            existing_plate = row['plate_number']
            similarity = self.calculate_similarity(plate_number, existing_plate)
            
            if similarity >= threshold and existing_plate != plate_number:
                similar_plates.append({
                    'plate_number': existing_plate,
                    'similarity': similarity
                })
        
        return sorted(similar_plates, key=lambda x: x['similarity'], reverse=True)
    
    def calculate_similarity(self, str1, str2):
        """Tính độ tương đồng giữa 2 chuỗi (0-1)"""
        return SequenceMatcher(None, str1.upper(), str2.upper()).ratio()
    
    def find_duplicates(self, time_window_minutes=5):
        """Tìm biển số trùng lặp trong khoảng thời gian"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT plate_number, COUNT(*) as count, 
                   MIN(timestamp) as first_seen, 
                   MAX(timestamp) as last_seen
            FROM detected_plates
            WHERE timestamp >= datetime('now', '-' || ? || ' minutes')
            GROUP BY plate_number
            HAVING count > 1
            ORDER BY count DESC
        ''', (time_window_minutes,))
        
        duplicates = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in duplicates]
    
    # ==================== XÓA THÔNG MINH ====================
    def delete_plate(self, plate_id, reason=''):
        """Xóa biển số với lý do và backup"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Lấy thông tin trước khi xóa
        cursor.execute('SELECT * FROM detected_plates WHERE id = ?', (plate_id,))
        plate_data = cursor.fetchone()
        
        if not plate_data:
            conn.close()
            return False, "Không tìm thấy biển số"
        
        # Backup vào bảng deleted
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO deleted_plates 
            (original_id, plate_number, timestamp, deleted_date, deleted_reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (plate_data[0], plate_data[1], plate_data[2], timestamp, reason))
        
        # Xóa file ảnh nếu có
        if plate_data[5] and os.path.exists(plate_data[5]):
            os.remove(plate_data[5])
        
        # Xóa record
        cursor.execute('DELETE FROM detected_plates WHERE id = ?', (plate_id,))
        
        conn.commit()
        conn.close()
        
        return True, "Đã xóa thành công"
    
    def delete_by_plate_number(self, plate_number, keep_latest=True):
        """Xóa tất cả records của 1 biển số (có tùy chọn giữ lại bản mới nhất)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if keep_latest:
            # Giữ lại record mới nhất
            cursor.execute('''
                DELETE FROM detected_plates 
                WHERE plate_number = ? AND id NOT IN (
                    SELECT id FROM detected_plates 
                    WHERE plate_number = ?
                    ORDER BY timestamp DESC 
                    LIMIT 1
                )
            ''', (plate_number, plate_number))
        else:
            # Xóa tất cả
            cursor.execute('DELETE FROM detected_plates WHERE plate_number = ?', (plate_number,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def delete_old_records(self, days=30):
        """Xóa records cũ hơn X ngày"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM detected_plates 
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def bulk_delete_by_confidence(self, min_confidence=0.5):
        """Xóa hàng loạt theo độ tin cậy thấp"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM detected_plates WHERE confidence < ?
        ''', (min_confidence,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    # ==================== KHÔI PHỤC ====================
    def restore_deleted_plate(self, deleted_id):
        """Khôi phục biển số đã xóa"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM deleted_plates WHERE id = ?', (deleted_id,))
        deleted_data = cursor.fetchone()
        
        if not deleted_data:
            conn.close()
            return False, "Không tìm thấy bản ghi đã xóa"
        
        # Khôi phục vào bảng chính (không có ảnh)
        cursor.execute('''
            INSERT INTO detected_plates 
            (plate_number, timestamp, frame_number, confidence, source)
            VALUES (?, ?, 0, 0.0, 'restored')
        ''', (deleted_data[2], deleted_data[3]))
        
        # Xóa khỏi bảng deleted
        cursor.execute('DELETE FROM deleted_plates WHERE id = ?', (deleted_id,))
        
        conn.commit()
        conn.close()
        
        return True, "Khôi phục thành công"
    
    # ==================== CẢNH BÁO ====================
    def get_alerts(self, unresolved_only=True):
        """Lấy danh sách cảnh báo"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if unresolved_only:
            cursor.execute('SELECT * FROM alerts WHERE resolved = 0 ORDER BY timestamp DESC')
        else:
            cursor.execute('SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 100')
        
        alerts = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in alerts]
    
    def resolve_alert(self, alert_id):
        """Đánh dấu cảnh báo đã xử lý"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE alerts SET resolved = 1 WHERE id = ?', (alert_id,))
        conn.commit()
        conn.close()
    
    # ==================== THỐNG KÊ ====================
    def get_statistics(self):
        """Lấy thống kê chi tiết"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Tổng số
        stats['total'] = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
        stats['unique'] = cursor.execute('SELECT COUNT(DISTINCT plate_number) FROM detected_plates').fetchone()[0]
        stats['watchlist_count'] = cursor.execute('SELECT COUNT(*) FROM watchlist WHERE active = 1').fetchone()[0]
        stats['alerts_pending'] = cursor.execute('SELECT COUNT(*) FROM alerts WHERE resolved = 0').fetchone()[0]
        
        # Hôm nay
        stats['today'] = cursor.execute('''
            SELECT COUNT(*) FROM detected_plates 
            WHERE DATE(timestamp) = DATE('now')
        ''').fetchone()[0]
        
        # Top biển số
        cursor.execute('''
            SELECT plate_number, COUNT(*) as count 
            FROM detected_plates 
            GROUP BY plate_number 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        stats['top_plates'] = [{'plate': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        conn.close()
        return stats
    
    def get_total_count(self):
        """Đếm tổng số biển số"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        count = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
        conn.close()
        return count
    
    def get_recent_plates(self, limit=10):
        """Lấy biển số gần nhất"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM detected_plates 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        plates = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in plates]