from PIL import Image
import cv2
import torch
import math 
import function.utils_rotate as utils_rotate
import function.helper as helper
import time
import os
import argparse
from database_manager import AdvancedLicensePlateDB

# ===================== CẤU HÌNH =====================
parser = argparse.ArgumentParser(description='Advanced License Plate Detection')
parser.add_argument('--source', type=str, default='0', help='Nguồn video')
parser.add_argument('--save', action='store_true', help='Lưu video output')
parser.add_argument('--save-crops', action='store_true', help='Lưu ảnh biển số')
parser.add_argument('--watchlist', type=str, help='File watchlist (1 biển số/dòng)')
args = parser.parse_args()

# Khởi tạo database nâng cao
db = AdvancedLicensePlateDB()

# Tạo thư mục lưu ảnh
if args.save_crops:
    os.makedirs('detected_plates', exist_ok=True)
    print("📁 Thư mục 'detected_plates' đã sẵn sàng")

# Load watchlist từ file nếu có
if args.watchlist and os.path.exists(args.watchlist):
    print(f"📋 Đang tải watchlist từ {args.watchlist}...")
    with open(args.watchlist, 'r', encoding='utf-8') as f:
        for line in f:
            plate = line.strip()
            if plate:
                success, _ = db.add_to_watchlist(plate, "Từ file watchlist", "warning")
                if success:
                    print(f"   ✅ Đã thêm: {plate}")

# Tải models
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

# ===================== BIẾN TRACKING =====================
prev_frame_time = 0
new_frame_time = 0
frame_count = 0
detected_plates_history = {}
DETECTION_COOLDOWN = 30

# Biến cho cảnh báo
alert_sound_enabled = True
alert_frames = {}  # Lưu frame hiển thị cảnh báo

print("\n🚀 Bắt đầu xử lý...")
print("⌨️  Nhấn 'q' để thoát")
print("⌨️  Nhấn 'p' để tạm dừng/tiếp tục")
print("⌨️  Nhấn 's' để chụp ảnh màn hình")
print("⌨️  Nhấn 'd' để xem danh sách 10 biển số gần nhất")
print("⌨️  Nhấn 'w' để xem watchlist")
print("⌨️  Nhấn 'a' để thêm biển số vào watchlist")
print("⌨️  Nhấn 'm' để bật/tắt âm thanh cảnh báo\n")

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
        current_alerts = []
        
        for plate in list_plates:
            flag = 0
            x = int(plate[0])
            y = int(plate[1])
            w = int(plate[2] - plate[0])
            h = int(plate[3] - plate[1])
            confidence = plate[4]
            
            # Vẽ khung biển số
            crop_img = frame[y:y+h, x:x+w]
            
            # Đọc biển số
            lp = ""
            for cc in range(0, 2):
                for ct in range(0, 2):
                    lp = helper.read_plate(yolo_license_plate, utils_rotate.deskew(crop_img, cc, ct))
                    if lp != "unknown":
                        detected_plates.append(lp)
                        
                        # Kiểm tra có trong watchlist không
                        is_watchlist, watchlist_info = db.check_watchlist(lp)
                        
                        # Chọn màu khung
                        box_color = (0, 0, 255) if is_watchlist else (0, 255, 0)
                        cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 3)
                        
                        # Kiểm tra nên lưu không
                        should_save = False
                        if lp not in detected_plates_history:
                            should_save = True
                        elif frame_count - detected_plates_history[lp] > DETECTION_COOLDOWN:
                            should_save = True
                        
                        # Lưu vào database
                        if should_save:
                            image_path = None
                            if args.save_crops:
                                crop_filename = f'detected_plates/{lp}_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
                                cv2.imwrite(crop_filename, crop_img)
                                image_path = crop_filename
                            
                            plate_id, triggered_alert = db.save_plate(
                                lp, frame_count, confidence, image_path, str(source)
                            )
                            detected_plates_history[lp] = frame_count
                            
                            if triggered_alert:
                                print(f"🚨 CẢNH BÁO: Phát hiện biển số trong watchlist: {lp}")
                                current_alerts.append({
                                    'plate': lp,
                                    'reason': watchlist_info['reason'],
                                    'type': watchlist_info['alert_type']
                                })
                                alert_frames[lp] = frame_count + 100  # Hiển thị cảnh báo 100 frames
                            else:
                                print(f"💾 Đã lưu biển số: {lp} (ID: {plate_id})")
                        
                        # Vẽ text biển số
                        text_bg_color = (0, 0, 255) if is_watchlist else (0, 255, 0)
                        text_size = cv2.getTextSize(lp, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
                        cv2.rectangle(frame, (x, y-35), (x + text_size[0] + 10, y), text_bg_color, -1)
                        
                        # Thêm icon cảnh báo nếu trong watchlist
                        display_text = f"⚠️ {lp}" if is_watchlist else lp
                        cv2.putText(frame, display_text, (x, y-10), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)
                        
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
        cv2.rectangle(info_bg, (5, 5), (350, 180), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, info_bg, 0.3, 0)
        
        cv2.putText(frame, f"FPS: {fps}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"Frame: {frame_count}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        cv2.putText(frame, f"Detected: {len(detected_plates)}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        cv2.putText(frame, f"Total DB: {db.get_total_count()}", (10, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        
        # Hiển thị số watchlist
        watchlist_count = db.get_statistics()['watchlist_count']
        cv2.putText(frame, f"Watchlist: {watchlist_count}", (10, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,255), 2)
        
        # Hiển thị cảnh báo active
        alert_y = 220
        for plate, end_frame in list(alert_frames.items()):
            if frame_count < end_frame:
                # Vẽ banner cảnh báo
                cv2.rectangle(frame, (0, alert_y-30), (frame.shape[1], alert_y+10), (0, 0, 255), -1)
                cv2.putText(frame, f"!!! CANH BAO: {plate} trong danh sach theo doi !!!", 
                           (20, alert_y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3)
                alert_y += 50
            else:
                del alert_frames[plate]
        
        # Lưu video
        if out is not None:
            out.write(frame)
    
    # Hiển thị video
    display_frame = frame.copy()
    if paused:
        cv2.putText(display_frame, "PAUSED - Press 'p' to continue", 
                    (frame.shape[1]//2 - 250, frame.shape[0]//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
    
    cv2.imshow("Advanced License Plate Detection", display_frame)
    
    # Xử lý phím bấm
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('q'):
        print("\n🛑 Dừng chương trình...")
        break
    elif key == ord('p'):
        paused = not paused
        print("⏸️  Tạm dừng" if paused else "▶️  Tiếp tục")
    elif key == ord('s'):
        screenshot_path = f'screenshot_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
        cv2.imwrite(screenshot_path, frame)
        print(f"📸 Đã lưu ảnh: {screenshot_path}")
    elif key == ord('d'):
        print("\n" + "="*60)
        print("📋 10 BIỂN SỐ GẦN NHẤT:")
        recent = db.get_recent_plates(10)
        for i, plate_data in enumerate(recent, 1):
            alert_icon = "🚨" if plate_data['is_watchlist'] else "  "
            print(f"{i}. {alert_icon} {plate_data['plate_number']} - {plate_data['timestamp']} (Frame: {plate_data['frame_number']})")
        print("="*60 + "\n")
    elif key == ord('w'):
        print("\n" + "="*60)
        print("👁️  DANH SÁCH WATCHLIST:")
        watchlist = db.get_watchlist()
        if watchlist:
            for i, item in enumerate(watchlist, 1):
                print(f"{i}. {item['plate_number']} - {item['reason']}")
                print(f"   Thêm lúc: {item['added_date']}, Phát hiện: {item['detection_count']} lần")
        else:
            print("   (Trống)")
        print("="*60 + "\n")
    elif key == ord('a'):
        print("\n➕ THÊM BIỂN SỐ VÀO WATCHLIST:")
        plate_input = input("Nhập biển số: ").strip()
        if plate_input:
            reason_input = input("Lý do (tùy chọn): ").strip() or "Thêm thủ công"
            success, result = db.add_to_watchlist(plate_input, reason_input, "warning")
            if success:
                print(f"✅ Đã thêm {plate_input} vào watchlist")
            else:
                print(f"❌ {result}")
    elif key == ord('m'):
        alert_sound_enabled = not alert_sound_enabled
        print(f"🔔 Âm thanh cảnh báo: {'BẬT' if alert_sound_enabled else 'TẮT'}")

# ===================== GIẢI PHÓNG TÀI NGUYÊN =====================
cap.release()
if out is not None:
    out.release()
    print(f"✅ Đã lưu video output!")
cv2.destroyAllWindows()

# Hiển thị thống kê cuối
stats = db.get_statistics()
print(f"\n📊 THỐNG KÊ:")
print(f"   - Tổng số phát hiện: {stats['total']}")
print(f"   - Biển số độc nhất: {stats['unique']}")
print(f"   - Trong watchlist: {stats['watchlist_count']}")
print(f"   - Cảnh báo chưa xử lý: {stats['alerts_pending']}")
print(f"   - Tổng số frame: {frame_count}")
print("👋 Chương trình kết thúc!")