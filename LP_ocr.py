import torch
import cv2

# ================== CẤU HÌNH ==================
yolov5_dir = r'F:\LPR_Chickens-LPR-V3\yolov5'
model_path = r'F:\LPR_Chickens-LPR-V3\model\LP_ocr.pt'
image_path = r'F:\LPR_Chickens-LPR-V3\detected_plates\3DG-88816_20251121_211109.jpg'

# ================== LOAD MODEL ==================
model = torch.hub.load(
    yolov5_dir,       # Thư mục YOLOv5 local
    'custom',         # Model custom
    path=model_path,  # Đường dẫn file .pt
    source='local'    # Sử dụng repo local
)

# ================== ĐỌC ẢNH ==================
img = cv2.imread(image_path)
if img is None:
    raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

# Chuyển ảnh sang RGB (YOLO yêu cầu)
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# ================== DÒ KÝ TỰ ==================
results = model(img_rgb, size=940)  # size có thể thay đổi tùy model và kích thước ảnh

# ================== LẤY KẾT QUẢ DƯỚI DẠNG PANDAS ==================
df = results.pandas().xyxy[0]

# In các thông tin cần thiết
print(df[['xmin', 'ymin', 'xmax', 'ymax', 'confidence', 'name']])
