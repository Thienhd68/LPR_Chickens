import torch
import cv2
import numpy as np

# ================== CẤU HÌNH ==================
model_path = r'F:\LPR_Chickens-LPR-V3\model\LP_ocr.pt'
yolov5_dir = r'F:\LPR_Chickens-LPR-V3\yolov5'
image_path = r'F:\LPR_Chickens-LPR-V3\detected_plates\3DG-88816_20251121_211109.jpg'

# ================== LOAD MODEL ==================
model = torch.hub.load(yolov5_dir, 'custom', path=model_path, source='local')

# ================== ĐỌC ẢNH ==================
img = cv2.imread(image_path)
if img is None:
    raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

# ================== PHÓNG TO ẢNH NẾU NHỎ ==================
height, width = img.shape[:2]
if max(height, width) < 300:  # nếu ảnh nhỏ hơn 300px thì phóng
    scale_factor = 3
    img = cv2.resize(img, (width*scale_factor, height*scale_factor), interpolation=cv2.INTER_LINEAR)

# ================== TĂNG ĐỘ SÁNG/CONTRAST ==================
alpha = 1.3  # contrast (1.0-3.0)
beta = 20    # brightness (0-100)
img_enhanced = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

# ================== CHUYỂN SANG RGB ==================
img_rgb = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2RGB)

# ================== DÒ KÝ TỰ ==================
results = model(img_rgb, size=640)  # thử size phù hợp với ảnh
df = results.pandas().xyxy[0]

# Lọc ký tự có confidence cao
df = df[df['confidence'] > 0.3]

# ================== VẼ KÝ TỰ ==================
for i, row in df.iterrows():
    x1, y1 = int(row['xmin']), int(row['ymin'])
    x2, y2 = int(row['xmax']), int(row['ymax'])
    label = str(row['name'])
    
    # Vẽ khung chữ nhật
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
    
    # Font nhỏ vừa phải, không che ảnh
    font_scale = 0.5
    thickness = 1
    cv2.putText(img, label, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness)

# ================== HIỂN THỊ ẢNH ==================
cv2.imshow("Detected Characters", img)
cv2.waitKey(0)
cv2.destroyAllWindows()

# ================== LƯU KẾT QUẢ ==================
output_path = r'F:\LPR_Chickens-LPR-V3\detected_plates\result_enhanced.jpg'
cv2.imwrite(output_path, img)
print(f"Ảnh kết quả đã lưu tại: {output_path}")
