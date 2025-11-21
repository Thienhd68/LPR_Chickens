import sqlite3
from datetime import datetime, timedelta
import os
from difflib import SequenceMatcher
from contextlib import contextmanager
import json
import csv
from typing import Optional, Tuple, List, Dict


class AdvancedLicensePlateDB:
    """
    Quản lý Database cho hệ thống nhận diện biển số
    
    Chức năng chính:
    - Lưu trữ biển số phát hiện
    - Quản lý watchlist
    - Quản lý alerts
    - Soft delete (xóa mềm)
    - Tìm kiếm và phân tích
    """
    
    def __init__(self, db_path='license_plates.db'):
        """
        Khởi tạo database manager
        
        Args:
            db_path: Đường dẫn đến file database SQLite
        """
        self.db_path = db_path
        self.init_database()
        self.optimize_database()
    
    @contextmanager
    def get_connection(self):
        """
        Context manager để quản lý kết nối database an toàn
        Tự động commit khi thành công, rollback khi lỗi
        
        Usage:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Cho phép truy cập column bằng tên
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Khởi tạo các bảng trong database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Bảng chính: Biển số đã phát hiện
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detected_plates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    frame_number INTEGER,
                    confidence REAL DEFAULT 0.0,
                    image_path TEXT,
                    source TEXT DEFAULT 'webcam',
                    is_watchlist INTEGER DEFAULT 0,
                    alert_triggered INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bảng watchlist: Danh sách biển số theo dõi
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT UNIQUE NOT NULL,
                    reason TEXT,
                    alert_type TEXT DEFAULT 'warning',
                    added_date TEXT NOT NULL,
                    last_seen TEXT,
                    detection_count INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    metadata TEXT
                )
            ''')
            
            # Bảng alerts: Cảnh báo khi phát hiện watchlist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    alert_type TEXT DEFAULT 'warning',
                    message TEXT,
                    resolved INTEGER DEFAULT 0,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    notes TEXT
                )
            ''')
            
            # Bảng deleted_plates: Lưu các bản ghi đã xóa (soft delete)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deleted_plates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_id INTEGER,
                    plate_number TEXT,
                    timestamp TEXT,
                    deleted_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    deleted_reason TEXT,
                    deleted_by TEXT,
                    original_data TEXT
                )
            ''')
            
            print(f"✅ Database initialized: {self.db_path}")
    
    def optimize_database(self):
        """
        Tối ưu hóa database với các index và settings
        - WAL mode: Cho phép đọc/ghi đồng thời
        - Index: Tăng tốc truy vấn
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Performance optimizations
            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")
            
            # Tạo index để tăng tốc truy vấn
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_plate_number ON detected_plates(plate_number)",
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON detected_plates(timestamp DESC)",
                "CREATE INDEX IF NOT EXISTS idx_watchlist_plate ON watchlist(plate_number) WHERE active=1",
                "CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(resolved, timestamp DESC) WHERE resolved=0",
                "CREATE INDEX IF NOT EXISTS idx_detection_lookup ON detected_plates(plate_number, timestamp DESC)"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            print("✅ Database optimized with indexes")
    
    # ==================== DETECTION METHODS ====================
    
    def save_plate(self, plate_number: str, frame_number: int, confidence: float = 0.0,
                   image_path: Optional[str] = None, source: str = 'webcam') -> Tuple[int, bool]:
        """
        Lưu biển số vừa phát hiện vào database
        
        Args:
            plate_number: Số biển xe
            frame_number: Số frame trong video
            confidence: Độ tin cậy (0-1)
            image_path: Đường dẫn ảnh biển số
            source: Nguồn phát hiện (webcam, camera1, video...)
        
        Returns:
            Tuple[plate_id, is_watchlist]: ID bản ghi và có trong watchlist không
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Kiểm tra có trong watchlist không
            is_watchlist, watchlist_info = self.check_watchlist(plate_number)
            
            # Lưu vào bảng detected_plates
            cursor.execute('''
                INSERT INTO detected_plates 
                (plate_number, timestamp, frame_number, confidence, image_path, source, is_watchlist)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (plate_number, timestamp, frame_number, confidence, image_path, source, int(is_watchlist)))
            
            plate_id = cursor.lastrowid
            
            # Nếu trong watchlist, tạo alert và cập nhật stats
            if is_watchlist:
                alert_type = watchlist_info['alert_type']
                reason = watchlist_info['reason']
                
                # Tạo alert
                cursor.execute('''
                    INSERT INTO alerts (plate_number, timestamp, alert_type, message)
                    VALUES (?, ?, ?, ?)
                ''', (plate_number, timestamp, alert_type, 
                      f"🚨 Phát hiện biển số trong watchlist: {reason}"))
                
                # Cập nhật watchlist stats
                cursor.execute('''
                    UPDATE watchlist 
                    SET last_seen = ?, detection_count = detection_count + 1
                    WHERE plate_number = ?
                ''', (timestamp, plate_number))
                
                # Đánh dấu đã trigger alert
                cursor.execute('''
                    UPDATE detected_plates SET alert_triggered = 1 WHERE id = ?
                ''', (plate_id,))
            
            return plate_id, is_watchlist
        

    def get_jpeg(self):
        """Chuyển đổi frame hiện tại sang JPEG để stream"""
        with self.lock:
            if self.current_frame is None:
                return None

            # Encode sang JPEG
            ret, jpeg = cv2.imencode('.jpg', self.current_frame)
            if ret:
                return jpeg.tobytes()
            return None

    def stop(self):
        """Hàm để gọi từ bên ngoài khi muốn dừng"""
        self.stop_event.set()
        self.running = False
    
    # ==================== QUERY METHODS ====================
    
    def get_recent_plates(self, limit: int = 20) -> List[Dict]:
        """
        Lấy danh sách các biển số phát hiện gần đây
        
        Args:
            limit: Số lượng bản ghi cần lấy
        
        Returns:
            List[Dict]: Danh sách các bản ghi detected_plates
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM detected_plates
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            plates = cursor.fetchall()
            return [dict(row) for row in plates]
    
    def search_plates(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Tìm kiếm biển số theo pattern (ví dụ: LIKE)
        
        Args:
            query: Biển số cần tìm (hỗ trợ wildcard %)
            limit: Số lượng bản ghi
        
        Returns:
            List[Dict]: Danh sách các bản ghi
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Sử dụng UPPER() để tìm kiếm không phân biệt chữ hoa/chữ thường
            # Thêm '%' để tìm kiếm tương đối nếu người dùng không thêm
            search_query = f"%{query.upper()}%" if not ('%' in query or '_' in query) else query.upper()
            
            cursor.execute('''
                SELECT * FROM detected_plates
                WHERE plate_number LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (search_query, limit))
            plates = cursor.fetchall()
            return [dict(row) for row in plates]

    # ==================== WATCHLIST METHODS ====================
    
    def add_to_watchlist(self, plate_number: str, reason: str = '', 
                        alert_type: str = 'warning', 
                        metadata: Optional[Dict] = None) -> Tuple[bool, any]:
        """
        Thêm biển số vào watchlist
        
        Args:
            plate_number: Số biển xe
            reason: Lý do theo dõi
            alert_type: Loại cảnh báo (info, warning, danger)
            metadata: Thông tin bổ sung (dict)
        
        Returns:
            Tuple[success, result]: (True, watchlist_id) hoặc (False, error_message)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            metadata_json = json.dumps(metadata) if metadata else None
            
            try:
                cursor.execute('''
                    INSERT INTO watchlist (plate_number, reason, alert_type, added_date, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (plate_number.upper(), reason, alert_type, timestamp, metadata_json))
                
                watchlist_id = cursor.lastrowid
                return True, watchlist_id
            except sqlite3.IntegrityError:
                return False, "Biển số đã có trong watchlist"
    
    def update_watchlist(self, plate_number: str, reason: Optional[str] = None,
                        alert_type: Optional[str] = None, 
                        active: Optional[bool] = None) -> Tuple[bool, str]:
        """
        Cập nhật thông tin watchlist
        
        Args:
            plate_number: Số biển xe
            reason: Lý do mới (None = không đổi)
            alert_type: Loại cảnh báo mới (None = không đổi)
            active: Trạng thái active (None = không đổi)
        
        Returns:
            Tuple[success, message]
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if reason is not None:
                updates.append("reason = ?")
                params.append(reason)
            
            if alert_type is not None:
                updates.append("alert_type = ?")
                params.append(alert_type)
            
            if active is not None:
                updates.append("active = ?")
                params.append(int(active))
            
            if not updates:
                return False, "Không có gì để cập nhật"
            
            params.append(plate_number.upper())
            query = f"UPDATE watchlist SET {', '.join(updates)} WHERE plate_number = ?"
            
            cursor.execute(query, params)
            
            if cursor.rowcount > 0:
                return True, "Cập nhật thành công"
            return False, "Không tìm thấy biển số trong watchlist"
    
    def remove_from_watchlist(self, plate_number: str) -> bool:
        """
        Xóa biển số khỏi watchlist (soft delete)
        
        Args:
            plate_number: Số biển xe
        
        Returns:
            bool: True nếu xóa thành công
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE watchlist SET active = 0 WHERE plate_number = ?', 
                          (plate_number.upper(),))
            return cursor.rowcount > 0
    
    def get_watchlist(self, active_only: bool = True, limit: Optional[int] = None) -> List[Dict]:
        """
        Lấy danh sách watchlist
        
        Args:
            active_only: Chỉ lấy các item active
            limit: Giới hạn số lượng (None = all)
        
        Returns:
            List[Dict]: Danh sách watchlist
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM watchlist'
            params = []
            
            if active_only:
                query += ' WHERE active = 1'
            
            query += ' ORDER BY detection_count DESC, added_date DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor.execute(query, params)
            watchlist = cursor.fetchall()
            
            return [dict(row) for row in watchlist]
    
    def check_watchlist(self, plate_number: str) -> Tuple[bool, Optional[Dict]]:
        """
        Kiểm tra biển số có trong watchlist không
        
        Args:
            plate_number: Số biển xe
        
        Returns:
            Tuple[is_in_watchlist, watchlist_info]
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM watchlist WHERE plate_number = ? AND active = 1', 
                (plate_number.upper(),)
            )
            result = cursor.fetchone()
            
            if result:
                return True, dict(result)
            return False, None
    
    def import_watchlist_from_file(self, filepath: str, 
                                   default_reason: str = "Import từ file",
                                   default_alert_type: str = "warning") -> Dict:
        """
        Import watchlist từ file text hoặc CSV
        
        Args:
            filepath: Đường dẫn file
            default_reason: Lý do mặc định
            default_alert_type: Loại cảnh báo mặc định
        
        Returns:
            Dict: {success: int, failed: int, errors: List}
        """
        result = {'success': 0, 'failed': 0, 'errors': []}
        
        if not os.path.exists(filepath):
            result['errors'].append(f"File không tồn tại: {filepath}")
            return result
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Phát hiện format: CSV hoặc text thuần
                first_line = f.readline().strip()
                f.seek(0)  # Reset về đầu file
                
                if ',' in first_line and not first_line.startswith('#'):
                    # CSV format: plate_number,reason,alert_type
                    reader = csv.DictReader(f)
                    for row in reader:
                        plate = row.get('plate_number', '').strip().upper()
                        if not plate:
                            continue
                        
                        reason = row.get('reason', default_reason)
                        alert_type = row.get('alert_type', default_alert_type)
                        
                        success, _ = self.add_to_watchlist(plate, reason, alert_type)
                        if success:
                            result['success'] += 1
                        else:
                            result['failed'] += 1
                            result['errors'].append(f"{plate} đã tồn tại")
                else:
                    # Text thuần: mỗi dòng một biển số
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        plate = line.upper()
                        success, _ = self.add_to_watchlist(plate, default_reason, default_alert_type)
                        
                        if success:
                            result['success'] += 1
                        else:
                            result['failed'] += 1
                            result['errors'].append(f"{plate} đã tồn tại")
        
        except Exception as e:
            result['errors'].append(f"Lỗi đọc file: {str(e)}")
        
        return result
    
    def export_watchlist_to_file(self, filepath: str, format: str = 'csv') -> Tuple[bool, str]:
        """
        Export watchlist ra file
        
        Args:
            filepath: Đường dẫn file output
            format: 'csv' hoặc 'txt'
        
        Returns:
            Tuple[success, message]
        """
        try:
            watchlist = self.get_watchlist(active_only=True)
            
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                if format == 'csv':
                    writer = csv.DictWriter(f, fieldnames=['plate_number', 'reason', 'alert_type', 'added_date', 'detection_count'])
                    writer.writeheader()
                    for item in watchlist:
                        writer.writerow({
                            'plate_number': item['plate_number'],
                            'reason': item['reason'] or '',
                            'alert_type': item['alert_type'],
                            'added_date': item['added_date'],
                            'detection_count': item['detection_count']
                        })
                else:  # txt
                    f.write("# Watchlist Export - " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
                    for item in watchlist:
                        f.write(f"{item['plate_number']}\n")
            
            return True, f"Đã export {len(watchlist)} biển số"
        except Exception as e:
            return False, f"Lỗi export: {str(e)}"
    
    # ==================== ALERT METHODS ====================
    
    def get_alerts(self, unresolved_only: bool = True, limit: int = 100) -> List[Dict]:
        """Lấy danh sách alerts"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM alerts'
            params = []
            
            if unresolved_only:
                query += ' WHERE resolved = 0'
            
            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            alerts = cursor.fetchall()
            
            return [dict(row) for row in alerts]
    
    def resolve_alert(self, alert_id: int, resolved_by: str = 'system', notes: str = '') -> bool:
        """Đánh dấu alert đã xử lý"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                UPDATE alerts 
                SET resolved = 1, resolved_at = ?, resolved_by = ?, notes = ?
                WHERE id = ?
            ''', (timestamp, resolved_by, notes, alert_id))
            
            return cursor.rowcount > 0
    
    # ==================== STATISTICS ====================
    def get_total_count(self) -> int:
        """
        Lấy tổng số lượng biển số đã phát hiện trong database
        Hàm này giúp UI lấy số liệu nhanh mà không cần gọi get_statistics
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()
                return result[0] if result else 0
        except Exception as e:
            print(f"Error getting total count: {e}")
            return 0
    
    def get_statistics(self, detailed: bool = False) -> Dict:
        """
        Lấy thống kê tổng quan
        
        Args:
            detailed: Có lấy thống kê chi tiết không
        
        Returns:
            Dict: Thống kê
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            
            # Thống kê cơ bản
            stats['total'] = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
            stats['unique'] = cursor.execute('SELECT COUNT(DISTINCT plate_number) FROM detected_plates').fetchone()[0]
            stats['watchlist_count'] = cursor.execute('SELECT COUNT(*) FROM watchlist WHERE active = 1').fetchone()[0]
            stats['alerts_pending'] = cursor.execute('SELECT COUNT(*) FROM alerts WHERE resolved = 0').fetchone()[0]
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
            
            if detailed:
                stats['avg_confidence'] = cursor.execute(
                    'SELECT AVG(confidence) FROM detected_plates'
                ).fetchone()[0] or 0
            
            return stats
    
    # ==================== CLEANUP ====================
    
    def cleanup_old_records(self, days: int = 30, keep_watchlist: bool = True) -> int:
        """
        Xóa các bản ghi cũ
        
        Args:
            days: Xóa bản ghi cũ hơn X ngày
            keep_watchlist: Giữ lại bản ghi có trong watchlist
        
        Returns:
            int: Số bản ghi đã xóa
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
            if keep_watchlist:
                cursor.execute('''
                    DELETE FROM detected_plates 
                    WHERE timestamp < ? AND is_watchlist = 0
                ''', (cutoff,))
            else:
                cursor.execute('DELETE FROM detected_plates WHERE timestamp < ?', (cutoff,))
            
            deleted_count = cursor.rowcount
            cursor.execute('VACUUM')  # Thu hồi không gian
            
            return deleted_count


# ==================== TESTING ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("📊 Testing Database Manager")
    print("="*60)
    
    db = AdvancedLicensePlateDB('test_lpr.db')
    
    # Test 1: Save plate
    print("\n1️⃣ Test: Save Plate")
    plate_id, is_wl = db.save_plate("29A-12345", 100, 0.95, "test.jpg", "camera1")
    print(f"✅ Saved: ID={plate_id}, Watchlist={is_wl}")
    
    # Test 2: Add to watchlist
    print("\n2️⃣ Test: Add to Watchlist")
    success, result = db.add_to_watchlist("51B-99999", "Test vehicle", "danger")
    print(f"✅ Add watchlist: {result}")
    
    # Test 3: Check watchlist
    print("\n3️⃣ Test: Check Watchlist")
    is_in, info = db.check_watchlist("51B-99999")
    print(f"✅ Check: is_in={is_in}, info={info}")
    
    # Test 4: Statistics
    print("\n4️⃣ Test: Statistics")
    stats = db.get_statistics(detailed=True)
    print(f"✅ Stats: {json.dumps(stats, indent=2, ensure_ascii=False)}")
    
    print("\n✅ All tests passed!")