"""
Main Detection Script với Camera Control
Hỗ trợ điều khiển từ Dashboard
"""
import threading
import io
from PIL import Image
import cv2
import torch
import time
import os
import argparse
import json
from datetime import datetime

# Import modules
from config import Config
from database_manager import AdvancedLicensePlateDB
from camera_manager import CameraManager
import function.utils_rotate as utils_rotate
import function.helper as helper


class LicensePlateDetector:
    """
    License Plate Detection System với Camera Control
    """
    
    def __init__(self, args):
        """Khởi tạo detector"""
        self.args = args
        
        # Khởi tạo config
        Config.init_app()
        
        # Khởi tạo database
        self.db = AdvancedLicensePlateDB()
        
        # Khởi tạo camera manager
        self.camera_manager = CameraManager()
        
        # Load models
        print("⏳ Đang tải models...")
        self.yolo_LP_detect = torch.hub.load('yolov5', 'custom', 
                                             path=Config.LP_DETECTOR_MODEL, 
                                             force_reload=True, source='local')
        self.yolo_license_plate = torch.hub.load('yolov5', 'custom', 
                                                 path=Config.LP_OCR_MODEL, 
                                                 force_reload=True, source='local')
        self.yolo_license_plate.conf = Config.YOLO_CONFIDENCE
        print("✅ Models đã tải xong!")
        
        # State management
        self.running = False
        self.paused = False
        self.frame_count = 0
        self.detected_plates_history = {}
        self.alert_frames = {}
        
        # Statistics
        self.stats = {
            'start_time': None,
            'frames_processed': 0,
            'detections_count': 0,
            'watchlist_hits': 0
        }
        
        # Video writer (nếu save)
        self.out = None
        
        # Load watchlist từ file nếu có
        self.load_watchlist_from_file()

        # ⭐ QUAN TRỌNG: Khởi tạo biến cho streaming
        self.current_frame = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
    
    def get_jpeg(self):
        """
        Chuyển đổi frame hiện tại sang JPEG để stream
        Method này được gọi bởi app.py trong route /video_feed
        """
        with self.lock:
            if self.current_frame is None:
                return None

            # Encode sang JPEG
            try:
                ret, jpeg = cv2.imencode('.jpg', self.current_frame)
                if ret:
                    return jpeg.tobytes()
            except Exception as e:
                print(f"⚠️  Lỗi encode JPEG: {e}")
            
            return None
    
    def stop(self):
        """Hàm để gọi từ bên ngoài khi muốn dừng"""
        self.stop_event.set()
        self.running = False
    
    def load_watchlist_from_file(self):
        """Load watchlist từ file text"""
        if self.args.watchlist and os.path.exists(self.args.watchlist):
            print(f"📋 Đang tải watchlist từ {self.args.watchlist}...")
            count = 0
            with open(self.args.watchlist, 'r', encoding='utf-8') as f:
                for line in f:
                    plate = line.strip()
                    if plate and not plate.startswith('#'):
                        success, _ = self.db.add_to_watchlist(plate, "Từ file watchlist", "warning")
                        if success:
                            count += 1
            print(f"   ✅ Đã thêm {count} biển số vào watchlist")
    
    def open_camera(self, source_type: str, source_value: str) -> bool:
        """
        Mở camera source
        
        Returns:
            bool: Thành công hay không
        """
        success, message = self.camera_manager.open_source(source_type, source_value)
        
        if success:
            print(f"✅ {message}")
            
            # Setup video writer nếu cần
            if self.args.save:
                self.setup_video_writer()
            
            # Update state file
            self.update_state_file(running=True, source_type=source_type, source_value=source_value)
            
            return True
        else:
            print(f"❌ {message}")
            return False
    
    def setup_video_writer(self):
        """Setup video writer để save output"""
        info = self.camera_manager.get_info()
        
        if 'width' in info and 'height' in info:
            width = info['width']
            height = info['height']
            fps = info.get('fps', Config.DEFAULT_FPS)
        else:
            width = Config.DEFAULT_VIDEO_WIDTH
            height = Config.DEFAULT_VIDEO_HEIGHT
            fps = Config.DEFAULT_FPS
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        output_path = f'output_{time.strftime("%Y%m%d_%H%M%S")}.mp4'
        self.out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        print(f"💾 Sẽ lưu video vào: {output_path}")
    
    def process_frame(self, frame):
        """
        Xử lý một frame: phát hiện biển số
        
        Returns:
            Tuple[frame, detected_plates]
        """
        # Phát hiện biển số
        plates = self.yolo_LP_detect(frame, size=640)
        list_plates = plates.pandas().xyxy[0].values.tolist()
        
        detected_plates = []
        
        for plate in list_plates:
            x = int(plate[0])
            y = int(plate[1])
            w = int(plate[2] - plate[0])
            h = int(plate[3] - plate[1])
            confidence = plate[4]
            
            # Crop biển số
            crop_img = frame[y:y+h, x:x+w]
            
            # Đọc biển số (thử nhiều góc xoay)
            lp = "unknown"
            for cc in range(0, 2):
                for ct in range(0, 2):
                    lp = helper.read_plate(self.yolo_license_plate, 
                                          utils_rotate.deskew(crop_img, cc, ct))
                    if lp != "unknown":
                        break
                if lp != "unknown":
                    break
            
            if lp != "unknown":
                detected_plates.append({
                    'plate_number': lp,
                    'confidence': confidence,
                    'bbox': (x, y, w, h),
                    'crop': crop_img
                })
                
                # Kiểm tra watchlist
                is_watchlist, watchlist_info = self.db.check_watchlist(lp)
                
                # Vẽ khung
                box_color = (0, 0, 255) if is_watchlist else (0, 255, 0)
                cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 3)
                
                # Vẽ text
                text_bg_color = (0, 0, 255) if is_watchlist else (0, 255, 0)
                text_size = cv2.getTextSize(lp, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
                cv2.rectangle(frame, (x, y-35), (x + text_size[0] + 10, y), text_bg_color, -1)
                
                display_text = f"⚠️ {lp}" if is_watchlist else lp
                cv2.putText(frame, display_text, (x, y-10), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)
                
                # Lưu vào database
                should_save = self.should_save_plate(lp)
                
                if should_save:
                    image_path = None
                    if self.args.save_crops:
                        crop_filename = f'detected_plates/{lp}_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
                        cv2.imwrite(crop_filename, crop_img)
                        image_path = crop_filename
                    
                    source_info = self.camera_manager.get_info()
                    source_str = f"{source_info.get('source_type', 'unknown')}"
                    
                    plate_id, triggered_alert = self.db.save_plate(
                        lp, self.frame_count, confidence, image_path, source_str
                    )
                    
                    self.stats['detections_count'] += 1
                    
                    if triggered_alert:
                        self.stats['watchlist_hits'] += 1
                        print(f"🚨 CẢNH BÁO: Phát hiện biển số trong watchlist: {lp}")
                        self.alert_frames[lp] = self.frame_count + Config.ALERT_DISPLAY_FRAMES
                        
                        # Auto pause nếu bật
                        if Config.AUTO_PAUSE_ON_ALERT:
                            self.paused = True
                            print("⏸️  Tự động pause do phát hiện watchlist")
                    else:
                        print(f"💾 Đã lưu: {lp} (ID: {plate_id})")
                    
                    self.detected_plates_history[lp] = self.frame_count
        
        return frame, detected_plates
    
    def should_save_plate(self, plate_number: str) -> bool:
        """Kiểm tra có nên lưu biển số này không (để tránh duplicate)"""
        if plate_number not in self.detected_plates_history:
            return True
        
        frames_since_last = self.frame_count - self.detected_plates_history[plate_number]
        return frames_since_last > Config.DETECTION_COOLDOWN
    
    def draw_ui_overlay(self, frame):
        """Vẽ UI overlay lên frame"""
        # Background cho info panel
        info_bg = frame.copy()
        cv2.rectangle(info_bg, (5, 5), (350, 180), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, info_bg, 0.3, 0)
        
        # FPS
        if self.stats['start_time']:
            elapsed = time.time() - self.stats['start_time']
            fps = int(self.frame_count / elapsed) if elapsed > 0 else 0
        else:
            fps = 0
        
        cv2.putText(frame, f"FPS: {fps}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"Frame: {self.frame_count}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        cv2.putText(frame, f"Detections: {self.stats['detections_count']}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        cv2.putText(frame, f"Total DB: {self.db.get_total_count()}", (10, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        
        # Watchlist count
        watchlist_count = self.db.get_statistics()['watchlist_count']
        cv2.putText(frame, f"Watchlist: {watchlist_count}", (10, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,255), 2)
        
        # Alert banners
        alert_y = 220
        for plate, end_frame in list(self.alert_frames.items()):
            if self.frame_count < end_frame:
                cv2.rectangle(frame, (0, alert_y-30), (frame.shape[1], alert_y+10), (0, 0, 255), -1)
                cv2.putText(frame, f"!!! CANH BAO: {plate} trong danh sach theo doi !!!", 
                           (20, alert_y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3)
                alert_y += 50
            else:
                del self.alert_frames[plate]
        
        return frame
    
    def run(self):
        """Main detection loop"""

        # Kiểm tra camera đã mở chưa
        if not self.camera_manager.is_opened:
            print("❌ Chưa mở camera source. Dùng open_camera() trước.")
            return
        # Trạng thái
        self.running = True
        self.stats['start_time'] = time.time()
        
        print("\n🚀 Bắt đầu phát hiện...")
        print("⌨️  Nhấn 'q' để thoát")
        print("⌨️  Nhấn 'p' để tạm dừng/tiếp tục")
        print("⌨️  Nhấn 's' để chụp ảnh\n")
        
        while self.running and not self.stop_event.is_set():
            
            # Check pause
            if self.paused:
                key = cv2.waitKey(100) & 0xFF
                if key == ord('p'):
                    self.paused = False
                    print("▶️  Tiếp tục")
                elif key == ord('q'):
                    break
                continue
            
            # Đọc frame
            ret, frame = self.camera_manager.read_frame()
            
            if not ret:
                print("⚠️  Không đọc được frame. Kết thúc.")
                break
            
            self.frame_count += 1
            self.stats['frames_processed'] += 1
            
            # Skip frames nếu cần (để tăng tốc)
            if self.frame_count % Config.FRAME_SKIP != 0:
                continue
            
            # Process frame
            frame, detected = self.process_frame(frame)
            
            # Draw UI overlay
            frame = self.draw_ui_overlay(frame)
            
            # ⭐ LƯU FRAME CHO WEB STREAMING
            with self.lock:
                self.current_frame = frame.copy()

            # Save video
            if self.out is not None:
                self.out.write(frame)
            
            # Hiển thị
            if Config.ENABLE_PREVIEW:
                cv2.imshow("License Plate Detection", frame)
            
            # Keyboard control
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n🛑 Dừng phát hiện...")
                break
            elif key == ord('p'):
                self.paused = True
                print("⏸️  Tạm dừng")
            elif key == ord('s'):
                screenshot_path = f'screenshot_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
                cv2.imwrite(screenshot_path, frame)
                print(f"📸 Đã lưu: {screenshot_path}")
        
        # Cleanup
        self.cleanup()
    
    def cleanup(self):
        """Dọn dẹp resources"""
        self.running = False
        
        # Close camera
        self.camera_manager.close()
        
        # Release video writer
        if self.out is not None:
            self.out.release()
            print("✅ Đã lưu video output")
        
        # Close windows
        cv2.destroyAllWindows()
        
        # Update state file
        self.update_state_file(running=False)
        
        # Print statistics
        self.print_statistics()
    
    def print_statistics(self):
        """In thống kê kết thúc"""
        stats = self.db.get_statistics()
        
        print(f"\n📊 THỐNG KÊ:")
        print(f"   - Frames xử lý: {self.stats['frames_processed']}")
        print(f"   - Biển số phát hiện: {self.stats['detections_count']}")
        print(f"   - Watchlist hits: {self.stats['watchlist_hits']}")
        print(f"   - Tổng DB: {stats['total']}")
        print(f"   - Biển số độc nhất: {stats['unique']}")
        print("👋 Hoàn tất!")
    
    def update_state_file(self, running=None, source_type=None, source_value=None):
        """Cập nhật state file để dashboard tracking"""
        try:
            # Đọc state hiện tại
            if os.path.exists(Config.STATE_FILE):
                with open(Config.STATE_FILE, 'r') as f:
                    state = json.load(f)
            else:
                state = {}
            
            # Update state
            if running is not None:
                state['running'] = running
            
            if source_type is not None:
                state['source_type'] = source_type
                state['source_value'] = source_value
                state['start_time'] = datetime.now().isoformat() if running else None
            
            state['frames_processed'] = self.stats['frames_processed']
            state['detections_count'] = self.stats['detections_count']
            state['last_update'] = datetime.now().isoformat()
            
            # Ghi vào file
            with open(Config.STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        
        except Exception as e:
            print(f"⚠️  Lỗi update state: {e}")


# ==================== MAIN ====================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='License Plate Detection with Camera Control')
    parser.add_argument('--source-type', type=str, default='webcam', 
                       help='Loại nguồn: webcam/phone/video/image')
    parser.add_argument('--source-value', type=str, default='0', 
                       help='Giá trị nguồn (ID/URL/path)')
    parser.add_argument('--save', action='store_true', help='Lưu video output')
    parser.add_argument('--save-crops', action='store_true', help='Lưu ảnh biển số')
    parser.add_argument('--watchlist', type=str, help='File watchlist')
    
    args = parser.parse_args()
    
    # Tạo detector
    detector = LicensePlateDetector(args)
    
    # Mở camera
    if not detector.open_camera(args.source_type, args.source_value):
        print("❌ Không thể mở camera. Thoát.")
        return
    
    # Run detection
    try:
        detector.run()
    except KeyboardInterrupt:
        print("\n⚠️  Bị ngắt bởi user")
        detector.cleanup()
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        detector.cleanup()


if __name__ == '__main__':
    main()