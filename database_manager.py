import sqlite3
from datetime import datetime, timedelta
import os
from difflib import SequenceMatcher
from contextlib import contextmanager
import json

class AdvancedLicensePlateDB:
    """Advanced License Plate Database Manager with Optimization"""
    
    def __init__(self, db_path='license_plates.db'):
        self.db_path = db_path
        self.init_database()
        self.optimize_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with optimized schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Main plates table with indexes
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
            
            # Watchlist table
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
            
            # Alerts table with enhanced fields
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
            
            # Deleted plates (soft delete)
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
        """Apply SQLite optimization settings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Performance optimizations
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
            
            # Create indexes for fast queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_plate_number 
                ON detected_plates(plate_number)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON detected_plates(timestamp DESC)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_watchlist_plate 
                ON watchlist(plate_number) WHERE active=1
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_alerts_unresolved 
                ON alerts(resolved, timestamp DESC) WHERE resolved=0
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_detection_lookup 
                ON detected_plates(plate_number, timestamp DESC)
            ''')
            
            print("✅ Database optimized with indexes")
    
    # ==================== SAVE & DETECTION ====================
    def save_plate(self, plate_number, frame_number, confidence=0.0, 
                   image_path=None, source='webcam'):
        """Save detected plate with watchlist check"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Check watchlist
            is_watchlist, watchlist_info = self.check_watchlist(plate_number)
            
            cursor.execute('''
                INSERT INTO detected_plates 
                (plate_number, timestamp, frame_number, confidence, image_path, source, is_watchlist)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (plate_number, timestamp, frame_number, confidence, image_path, source, int(is_watchlist)))
            
            plate_id = cursor.lastrowid
            
            # Trigger alert if in watchlist
            if is_watchlist:
                alert_type = watchlist_info['alert_type']
                reason = watchlist_info['reason']
                
                cursor.execute('''
                    INSERT INTO alerts (plate_number, timestamp, alert_type, message)
                    VALUES (?, ?, ?, ?)
                ''', (plate_number, timestamp, alert_type, 
                      f"🚨 Phát hiện biển số watchlist: {reason}"))
                
                # Update watchlist stats
                cursor.execute('''
                    UPDATE watchlist 
                    SET last_seen = ?, detection_count = detection_count + 1
                    WHERE plate_number = ?
                ''', (timestamp, plate_number))
                
                cursor.execute('''
                    UPDATE detected_plates SET alert_triggered = 1 WHERE id = ?
                ''', (plate_id,))
            
            return plate_id, is_watchlist
    
    def batch_save_plates(self, plates_data):
        """Batch insert for high-performance bulk operations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            data = [
                (p['plate_number'], timestamp, p.get('frame_number', 0), 
                 p.get('confidence', 0.0), p.get('image_path'), p.get('source', 'webcam'), 0)
                for p in plates_data
            ]
            
            cursor.executemany('''
                INSERT INTO detected_plates 
                (plate_number, timestamp, frame_number, confidence, image_path, source, is_watchlist)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', data)
            
            return cursor.rowcount
    
    # ==================== WATCHLIST MANAGEMENT ====================
    def add_to_watchlist(self, plate_number, reason='', alert_type='warning', metadata=None):
        """Add plate to watchlist with metadata support"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            metadata_json = json.dumps(metadata) if metadata else None
            
            try:
                cursor.execute('''
                    INSERT INTO watchlist (plate_number, reason, alert_type, added_date, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (plate_number, reason, alert_type, timestamp, metadata_json))
                
                watchlist_id = cursor.lastrowid
                return True, watchlist_id
            except sqlite3.IntegrityError:
                return False, "Biển số đã có trong watchlist"
    
    def update_watchlist(self, plate_number, reason=None, alert_type=None, active=None):
        """Update existing watchlist entry"""
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
                return False, "No fields to update"
            
            params.append(plate_number)
            query = f"UPDATE watchlist SET {', '.join(updates)} WHERE plate_number = ?"
            
            cursor.execute(query, params)
            
            if cursor.rowcount > 0:
                return True, "Updated successfully"
            return False, "Plate not found in watchlist"
    
    def remove_from_watchlist(self, plate_number):
        """Remove from watchlist (soft delete by setting active=0)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('UPDATE watchlist SET active = 0 WHERE plate_number = ?', (plate_number,))
            deleted = cursor.rowcount
            
            return deleted > 0
    
    def get_watchlist(self, active_only=True, limit=None):
        """Get watchlist with optional filters"""
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
    
    def check_watchlist(self, plate_number):
        """Fast watchlist check with caching potential"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT * FROM watchlist WHERE plate_number = ? AND active = 1', 
                (plate_number,)
            )
            result = cursor.fetchone()
            
            if result:
                return True, dict(result)
            return False, None
    
    # ==================== SEARCH & SIMILARITY ====================
    def search_plates(self, query, limit=50):
        """Advanced search with partial matching"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM detected_plates 
                WHERE plate_number LIKE ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (f'%{query}%', limit))
            
            plates = cursor.fetchall()
            return [dict(row) for row in plates]
    
    def find_similar_plates(self, plate_number, threshold=0.75, limit=10):
        """Find similar plates using fuzzy matching"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT DISTINCT plate_number FROM detected_plates')
            all_plates = cursor.fetchall()
            
            similar_plates = []
            
            for row in all_plates:
                existing_plate = row['plate_number']
                similarity = SequenceMatcher(None, plate_number.upper(), existing_plate.upper()).ratio()
                
                if similarity >= threshold and existing_plate != plate_number:
                    similar_plates.append({
                        'plate_number': existing_plate,
                        'similarity': round(similarity * 100, 2)
                    })
            
            return sorted(similar_plates, key=lambda x: x['similarity'], reverse=True)[:limit]
    
    def find_duplicates(self, time_window_minutes=5):
        """Find duplicate detections within time window"""
        with self.get_connection() as conn:
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
            return [dict(row) for row in duplicates]
    
    # ==================== DELETE & CLEANUP ====================
    def delete_plate(self, plate_id, reason='', deleted_by='system'):
        """Soft delete with backup"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get original data
            cursor.execute('SELECT * FROM detected_plates WHERE id = ?', (plate_id,))
            plate_data = cursor.fetchone()
            
            if not plate_data:
                return False, "Không tìm thấy biển số"
            
            # Backup to deleted_plates
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            original_json = json.dumps(dict(plate_data))
            
            cursor.execute('''
                INSERT INTO deleted_plates 
                (original_id, plate_number, timestamp, deleted_reason, deleted_by, original_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (plate_data['id'], plate_data['plate_number'], plate_data['timestamp'], 
                  reason, deleted_by, original_json))
            
            # Delete image if exists
            if plate_data['image_path'] and os.path.exists(plate_data['image_path']):
                try:
                    os.remove(plate_data['image_path'])
                except:
                    pass
            
            # Delete record
            cursor.execute('DELETE FROM detected_plates WHERE id = ?', (plate_id,))
            
            return True, "Đã xóa thành công"
    
    def cleanup_old_records(self, days=30, keep_watchlist=True):
        """Archive/delete old records for performance"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
            if keep_watchlist:
                cursor.execute('''
                    DELETE FROM detected_plates 
                    WHERE timestamp < ? AND is_watchlist = 0
                ''', (cutoff,))
            else:
                cursor.execute('''
                    DELETE FROM detected_plates 
                    WHERE timestamp < ?
                ''', (cutoff,))
            
            deleted_count = cursor.rowcount
            
            # Vacuum to reclaim space
            cursor.execute('VACUUM')
            
            return deleted_count
    
    def bulk_delete_low_confidence(self, min_confidence=0.5):
        """Delete low confidence detections"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM detected_plates WHERE confidence < ?
            ''', (min_confidence,))
            
            return cursor.rowcount
    
    # ==================== ALERTS ====================
    def get_alerts(self, unresolved_only=True, limit=100):
        """Get alerts with filters"""
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
    
    def resolve_alert(self, alert_id, resolved_by='system', notes=''):
        """Mark alert as resolved"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                UPDATE alerts 
                SET resolved = 1, resolved_at = ?, resolved_by = ?, notes = ?
                WHERE id = ?
            ''', (timestamp, resolved_by, notes, alert_id))
            
            return cursor.rowcount > 0
    
    def resolve_all_alerts(self):
        """Resolve all pending alerts"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                UPDATE alerts 
                SET resolved = 1, resolved_at = ?
                WHERE resolved = 0
            ''', (timestamp,))
            
            return cursor.rowcount
    
    # ==================== STATISTICS ====================
    def get_statistics(self, detailed=False):
        """Get comprehensive statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Basic counts
            stats['total'] = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
            stats['unique'] = cursor.execute('SELECT COUNT(DISTINCT plate_number) FROM detected_plates').fetchone()[0]
            stats['watchlist_count'] = cursor.execute('SELECT COUNT(*) FROM watchlist WHERE active = 1').fetchone()[0]
            stats['alerts_pending'] = cursor.execute('SELECT COUNT(*) FROM alerts WHERE resolved = 0').fetchone()[0]
            
            # Today's stats
            stats['today'] = cursor.execute('''
                SELECT COUNT(*) FROM detected_plates 
                WHERE DATE(timestamp) = DATE('now')
            ''').fetchone()[0]
            
            # Top plates
            cursor.execute('''
                SELECT plate_number, COUNT(*) as count 
                FROM detected_plates 
                GROUP BY plate_number 
                ORDER BY count DESC 
                LIMIT 5
            ''')
            stats['top_plates'] = [{'plate': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            if detailed:
                # Average confidence
                stats['avg_confidence'] = cursor.execute('''
                    SELECT AVG(confidence) FROM detected_plates
                ''').fetchone()[0] or 0
                
                # Detection by source
                cursor.execute('''
                    SELECT source, COUNT(*) as count 
                    FROM detected_plates 
                    GROUP BY source
                ''')
                stats['by_source'] = [{'source': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            return stats
    
    def get_total_count(self):
        """Fast total count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            count = cursor.execute('SELECT COUNT(*) FROM detected_plates').fetchone()[0]
            return count
    
    def get_recent_plates(self, limit=20, offset=0):
        """Get recent plates with pagination"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM detected_plates 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            plates = cursor.fetchall()
            return [dict(row) for row in plates]
    
    # ==================== ANALYTICS ====================
    def get_hourly_stats(self, date=None):
        """Get detections grouped by hour"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM detected_plates
                WHERE DATE(timestamp) = ?
                GROUP BY hour
                ORDER BY hour
            ''', (date,))
            
            return [{'hour': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    def get_database_size(self):
        """Get database file size in MB"""
        if os.path.exists(self.db_path):
            size_bytes = os.path.getsize(self.db_path)
            size_mb = size_bytes / (1024 * 1024)
            return round(size_mb, 2)
        return 0


# ==================== TESTING ====================
if __name__ == '__main__':
    db = AdvancedLicensePlateDB('test_lpr.db')
    
    print("\n📊 Testing Database Manager...")
    
    # Test save
    plate_id, is_watchlist = db.save_plate("29A-12345", 100, 0.95, "test.jpg", "camera1")
    print(f"✅ Saved plate: ID={plate_id}, Watchlist={is_watchlist}")
    
    # Test watchlist
    success, result = db.add_to_watchlist("51B-99999", "Test watchlist", "danger")
    print(f"✅ Added to watchlist: {result}")
    
    # Test stats
    stats = db.get_statistics(detailed=True)
    print(f"✅ Statistics: {stats}")
    
    print("\n✅ All tests passed!")