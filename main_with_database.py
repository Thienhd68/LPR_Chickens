from PIL import Image
import cv2
import torch
import math 
import function.utils_rotate as utils_rotate
import function.helper as helper
import time
import os
import argparse
import json
from datetime import datetime
import sqlite3

# ===================== CẤU HÌNH DATABASE =====================
class LicensePlateDB:
    def __init__(self, db_path='license_plates.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Khởi tạo database và bảng"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                frame_number INTEGER,
                confidence REAL,
                image_path TEXT,
                source TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"✅ Database đã sẵn sàng: {self.db_path}")
    
    def save_plate(self, plate_number, frame_number, confidence=0.0, 
                   image_path=None, source='webcam'):
        """Lưu thông tin biển số vào database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO detected_plates 
            (plate_number, timestamp, frame_number, confidence, image_path, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (plate_number, timestamp, frame_number, confidence, image_path, source))
        
        conn.commit()
        plate_id = cursor.lastrowid
        conn.close()
        
        return plate_id
    
    def get_recent_plates(self, limit=10):
        """Lấy danh sách biển số gần nhất"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM detected_plates 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        plates = cursor.fetchall()
        conn.close()
        
        return plates
    
    def get_total_count(self):
        """Đếm tổng số biển số đã phát hiện"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM detected_plates')
        count = cursor.fetchone()[0]
        
        conn.close()
        return count

# ===================== CẤU HÌNH =====================
parser = argparse.ArgumentParser(description='License Plate Detection')
parser.add_argument('--source', type=str, default='0', help='Nguồn video: 0 (webcam), 1, 2... hoặc đường dẫn file video')
parser.add_argument('--save', action='store_true', help='Lưu video output')
parser.add_argument('--save-crops', action='store_true', help='Lưu ảnh biển số đã cắt')
args = parser.parse_args()

# Khởi tạo database
db = LicensePlateDB()

# Tạo thư mục lưu ảnh biển số
if args.save_crops:
    os.makedirs('detected_plates', exist_ok=True)
    print("📁 Thư mục 'detected_plates' đã sẵn sàng")

# Tải model nhận diện biển và OCR biển số
print("⏳ Đang tải models...")
yolo_LP_detect = torch.hub.load('yolov5', 'custom', path='model/LP_detector.pt', force_reload=True, source='local')
yolo_license_plate = torch.hub.load('yolov5', 'custom', path='model/LP_ocr.pt', force_reload=True, source='local')
yolo_license_plate.conf = 0.60
print("✅ Models đã tải xong!")

# ===================== MỞ NGUỒN VIDEO =====================
source = int(args.source) if args.source.isdigit() else args.source
cap = cv2.VideoCapture(source)

if not cap.isOpened():
    print(f"❌ Không mở được nguồn: {source}")
    exit()

if isinstance(source, int):
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    print(f"📹 Đang sử dụng Camera {source}")
else:
    print(f"🎥 Đang xử lý video: {source}")

# ===================== SETUP SAVE VIDEO =====================
out = None
if args.save:
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 20
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output_path = f'output_{time.strftime("%Y%m%d_%H%M%S")}.mp4'
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))
    print(f"💾 Sẽ lưu video vào: {output_path}")

# ===================== BIẾN ĐẾM FPS & TRACKING =====================
prev_frame_time = 0
new_frame_time = 0
frame_count = 0
detected_plates_history = {}  # Lưu lịch sử để tránh lưu trùng
DETECTION_COOLDOWN = 30  # Số frame chờ trước khi lưu lại cùng biển số

print("\n🚀 Bắt đầu xử lý...")
print("⌨️  Nhấn 'q' để thoát")
print("⌨️  Nhấn 'p' để tạm dừng/tiếp tục")
print("⌨️  Nhấn 's' để chụp ảnh màn hình")
print("⌨️  Nhấn 'd' để xem danh sách biển số đã lưu\n")

paused = False

# ===================== VÒNG LẶP CHÍNH =====================
while True:
    if not paused:
        ret, frame = cap.read()
        if not ret:
            print("✅ Video đã kết thúc hoặc lỗi đọc frame.")
            break
        
        frame_count += 1
        
        # Phát hiện biển số
        plates = yolo_LP_detect(frame, size=640)
        list_plates = plates.pandas().xyxy[0].values.tolist()
        
        detected_plates = []
        
        for plate in list_plates:
            flag = 0
            x = int(plate[0])
            y = int(plate[1])
            w = int(plate[2] - plate[0])
            h = int(plate[3] - plate[1])
            confidence = plate[4]
            
            # Vẽ khung biển số
            crop_img = frame[y:y+h, x:x+w]
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
            
            # Đọc biển số
            lp = ""
            for cc in range(0, 2):
                for ct in range(0, 2):
                    lp = helper.read_plate(yolo_license_plate, utils_rotate.deskew(crop_img, cc, ct))
                    if lp != "unknown":
                        detected_plates.append(lp)
                        
                        # Kiểm tra xem biển số này đã được lưu gần đây chưa
                        should_save = False
                        if lp not in detected_plates_history:
                            should_save = True
                        elif frame_count - detected_plates_history[lp] > DETECTION_COOLDOWN:
                            should_save = True
                        
                        # Lưu vào database nếu cần
                        if should_save:
                            image_path = None
                            if args.save_crops:
                                crop_filename = f'detected_plates/{lp}_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
                                cv2.imwrite(crop_filename, crop_img)
                                image_path = crop_filename
                            
                            plate_id = db.save_plate(lp, frame_count, confidence, image_path, str(source))
                            detected_plates_history[lp] = frame_count
                            print(f"💾 Đã lưu biển số: {lp} (ID: {plate_id})")
                        
                        # Vẽ background cho text
                        text_size = cv2.getTextSize(lp, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
                        cv2.rectangle(frame, (x, y-35), (x + text_size[0], y), (0, 0, 255), -1)
                        cv2.putText(frame, lp, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)
                        flag = 1
                        break
                if flag == 1:
                    break
        
        # Hiển thị FPS
        new_frame_time = time.time()
        fps = int(1 / (new_frame_time - prev_frame_time + 1e-6))
        prev_frame_time = new_frame_time
        
        # Vẽ bảng thông tin
        info_bg = frame.copy()
        cv2.rectangle(info_bg, (5, 5), (300, 150), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, info_bg, 0.3, 0)
        
        cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"Frame: {frame_count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        cv2.putText(frame, f"Plates: {len(detected_plates)}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        cv2.putText(frame, f"Total DB: {db.get_total_count()}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        
        # Lưu video nếu được bật
        if out is not None:
            out.write(frame)
    
    # Hiển thị video
    display_frame = frame.copy()
    if paused:
        cv2.putText(display_frame, "PAUSED - Press 'p' to continue", 
                    (frame.shape[1]//2 - 200, frame.shape[0]//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    
    cv2.imshow("License Plate Detection - Webcam", display_frame)
    
    # Xử lý phím bấm
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('q'):
        print("\n🛑 Dừng chương trình...")
        break
    elif key == ord('p'):
        paused = not paused
        if paused:
            print("⏸️  Tạm dừng")
        else:
            print("▶️  Tiếp tục")
    elif key == ord('s'):
        screenshot_path = f'screenshot_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
        cv2.imwrite(screenshot_path, frame)
        print(f"📸 Đã lưu ảnh: {screenshot_path}")
    elif key == ord('d'):
        print("\n" + "="*50)
        print("📋 10 BIỂN SỐ GẦN NHẤT:")
        recent = db.get_recent_plates(10)
        for i, plate_data in enumerate(recent, 1):
            print(f"{i}. {plate_data[1]} - {plate_data[2]} (Frame: {plate_data[3]})")
        print("="*50 + "\n")

# ===================== GIẢI PHÓNG TÀI NGUYÊN =====================
cap.release()
if out is not None:
    out.release()
    print(f"✅ Đã lưu video output!")
cv2.destroyAllWindows()

print(f"\n📊 THỐNG KÊ:")
print(f"   - Tổng số biển số đã lưu: {db.get_total_count()}")
print(f"   - Tổng số frame xử lý: {frame_count}")
print("👋 Chương trình kết thúc!")