"""
Camera Manager Module - Quản lý các loại camera
Hỗ trợ: Webcam, Phone (IP), RTSP, Video, Image/Folder
"""
import cv2
import os
import glob
import time
import numpy as np
from typing import Optional, Tuple, List
from pathlib import Path
from config import Config


class CameraManager:
    """
    Quản lý nhiều loại nguồn camera
    
    Hỗ trợ:
    - Webcam (ID: 0, 1, 2...)
    - Phone Camera (URL HTTP)
    - RTSP Stream (Camera IP)
    - Video File (.mp4, .avi, .mov)
    - Image/Folder (Xử lý tuần tự)
    """
    
    def __init__(self):
        """Khởi tạo Camera Manager"""
        self.cap = None
        self.source_type = None
        self.source_value = None
        self.is_opened = False
        self.frame_count = 0
        self.start_time = None
        
        # Cho image folder
        self.image_list = []
        self.current_image_index = 0
    
    def open_source(self, source_type: str, source_value: str) -> Tuple[bool, str]:
        """
        Mở nguồn camera
        
        Args:
            source_type: Loại nguồn (webcam/phone/rtsp/video/image)
            source_value: Giá trị nguồn (ID/URL/path)
        
        Returns:
            (success, message)
        
        Ví dụ:
            manager.open_source('webcam', '0')
            manager.open_source('rtsp', 'rtsp://admin:123@192.168.1.1:554/stream')
        """
        # Đóng nguồn cũ nếu có
        if self.is_opened:
            self.close()
        
        # Validate nguồn
        valid, msg = Config.validate_camera_source(source_type, source_value)
        if not valid:
            return False, msg
        
        self.source_type = source_type
        self.source_value = source_value
        
        try:
            if source_type == 'webcam':
                return self._open_webcam(int(source_value))
            
            elif source_type in ['phone', 'rtsp', 'youtube']:
                return self._open_stream(source_value)
            
            elif source_type == 'video':
                return self._open_video(source_value)
            
            elif source_type == 'image':
                return self._open_image_source(source_value)
            
            else:
                return False, f"Loại nguồn không hỗ trợ: {source_type}"
        
        except Exception as e:
            return False, f"Lỗi khi mở nguồn: {str(e)}"
    
    def _open_webcam(self, camera_id: int) -> Tuple[bool, str]:
        """Mở webcam/USB camera"""
        self.cap = cv2.VideoCapture(camera_id)
        
        # FIX: Đặt properties trước khi đọc frame
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.DEFAULT_VIDEO_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.DEFAULT_VIDEO_HEIGHT)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Giảm buffer delay
        
        if not self.cap.isOpened():
            return False, f"❌ Không thể mở Webcam {camera_id}. Kiểm tra camera có bị chiếm không."
        
        # Test đọc frame
        ret, frame = self.cap.read()
        if not ret:
            self.cap.release()
            self.cap = None
            return False, f"❌ Webcam {camera_id} mở được nhưng không đọc được frame"
        
        self.is_opened = True
        self.start_time = time.time()
        
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        return True, f"✅ Webcam {camera_id} sẵn sàng ({actual_w}x{actual_h})"
    
    def _open_stream(self, url: str) -> Tuple[bool, str]:
        """Mở stream (Phone/RTSP/YouTube) - FIX timeout issue"""
        self.cap = cv2.VideoCapture(url)
        
        # Thêm timeout properties cho RTSP
        self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        
        if not self.cap.isOpened():
            return False, f"❌ Không thể kết nối stream. URL có đúng không?"
        
        # Test đọc frame với timeout
        start = time.time()
        ret = False
        frame = None
        
        while time.time() - start < Config.CAMERA_TIMEOUT:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                break
            time.sleep(0.1)
        
        if not ret or frame is None:
            self.cap.release()
            self.cap = None
            return False, f"❌ Stream mở được nhưng không nhận frame sau {Config.CAMERA_TIMEOUT}s"
        
        self.is_opened = True
        self.start_time = time.time()
        
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        
        return True, f"✅ Stream kết nối ({width}x{height})"
    
    def _open_video(self, filepath: str) -> Tuple[bool, str]:
        """Mở video file"""
        if not os.path.exists(filepath):
            return False, f"❌ File không tồn tại: {filepath}"
        
        self.cap = cv2.VideoCapture(filepath)
        
        if not self.cap.isOpened():
            return False, f"❌ Không thể mở video. Codec không hỗ trợ?"
        
        # Test đọc frame
        ret, frame = self.cap.read()
        if not ret:
            self.cap.release()
            self.cap = None
            return False, "❌ Video mở được nhưng không đọc được frame"
        
        # Reset về đầu video
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        self.is_opened = True
        self.start_time = time.time()
        
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0
        
        return True, f"✅ Video: {total_frames} frames, {fps}fps, {width}x{height}"
    
    def _open_image_source(self, path: str) -> Tuple[bool, str]:
        """Mở image file hoặc folder"""
        if not os.path.exists(path):
            return False, f"❌ Đường dẫn không tồn tại: {path}"
        
        # Nếu là file ảnh đơn
        if os.path.isfile(path):
            ext = path.split('.')[-1].lower()
            if ext not in Config.ALLOWED_IMAGE_EXTENSIONS:
                return False, f"❌ Extension không hỗ trợ: {ext}"
            self.image_list = [path]
        
        # Nếu là folder
        elif os.path.isdir(path):
            self.image_list = []
            for ext in Config.ALLOWED_IMAGE_EXTENSIONS:
                self.image_list.extend(glob.glob(os.path.join(path, f"*.{ext}")))
                self.image_list.extend(glob.glob(os.path.join(path, f"*.{ext.upper()}")))
            
            if not self.image_list:
                return False, f"❌ Không tìm thấy ảnh nào trong folder"
        else:
            return False, f"❌ Đường dẫn không hợp lệ"
        
        self.image_list.sort()
        self.current_image_index = 0
        self.is_opened = True
        self.start_time = time.time()
        
        return True, f"✅ Sẵn sàng xử lý {len(self.image_list)} ảnh"
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Đọc frame tiếp theo
        
        Returns:
            (success, frame) hoặc (False, None) khi hết
        """
        if not self.is_opened:
            return False, None
        
        self.frame_count += 1
        
        # Nếu là image source
        if self.source_type == 'image':
            return self._read_image_frame()
        
        # Nếu là video/camera source
        else:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return True, frame
            return False, None
    
    def _read_image_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Đọc frame từ image list"""
        if self.current_image_index >= len(self.image_list):
            return False, None
        
        image_path = self.image_list[self.current_image_index]
        frame = cv2.imread(image_path)
        
        if frame is None:
            print(f"⚠️  Lỗi đọc ảnh: {image_path}")
            self.current_image_index += 1
            return self._read_image_frame()
        
        self.current_image_index += 1
        return True, frame
    
    def get_info(self) -> dict:
        """Lấy thông tin nguồn hiện tại"""
        if not self.is_opened:
            return {'opened': False, 'source_type': None}
        
        info = {
            'opened': True,
            'source_type': self.source_type,
            'source_value': self.source_value,
            'frame_count': self.frame_count,
            'uptime': time.time() - self.start_time if self.start_time else 0
        }
        
        if self.source_type == 'image':
            total = len(self.image_list)
            current = self.current_image_index
            info['total_images'] = total
            info['current_image'] = current
            info['progress'] = (current / total * 100) if total > 0 else 0
        
        elif self.cap:
            try:
                info['width'] = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                info['height'] = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                info['fps'] = int(self.cap.get(cv2.CAP_PROP_FPS))
                
                if self.source_type == 'video':
                    total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    current = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                    info['total_frames'] = total
                    info['current_frame'] = current
                    info['progress'] = (current / total * 100) if total > 0 else 0
            except:
                pass
        
        return info
    
    def close(self):
        """Đóng nguồn camera"""
        if self.cap:
            self.cap.release()
            self.cap = None
        
        self.is_opened = False
        self.source_type = None
        self.source_value = None
        self.frame_count = 0
        self.image_list = []
        self.current_image_index = 0


# ==================== HELPER FUNCTIONS ====================

def list_available_cameras(max_check: int = 5) -> List[dict]:
    """
    Quét webcam khả dụng
    
    Args:
        max_check: Số camera tối đa cần kiểm tra
    
    Returns:
        List[dict]: Danh sách camera khả dụng
    """
    available = []
    
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        ret, frame = cap.read()
        
        if ret and frame is not None:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            available.append({
                'id': i,
                'name': f'Camera {i}',
                'resolution': f'{width}x{height}',
                'available': True
            })
        
        cap.release()
        time.sleep(0.1)
    
    return available


def test_camera_source(source_type: str, source_value: str) -> Tuple[bool, str, dict]:
    """
    Test kết nối camera
    
    Returns:
        (success, message, info_dict)
    """
    manager = CameraManager()
    success, message = manager.open_source(source_type, source_value)
    
    info = {}
    
    if success:
        frames_read = 0
        for _ in range(5):
            ret, frame = manager.read_frame()
            if ret:
                frames_read += 1
        
        info = manager.get_info()
        info['test_frames_read'] = frames_read
        manager.close()
    
    return success, message, info