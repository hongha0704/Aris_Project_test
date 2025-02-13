from ultralytics import YOLO
import cv2
import numpy as np
from scipy.spatial.distance import cdist
import logging

# YOLO 모델의 로깅 레벨 설정
logging.getLogger('ultralytics').setLevel(logging.ERROR)

def predict_on_image(model, img, conf):
    result = model.track(img, conf=conf, persist=True)[0]

    # Detection
    cls = result.boxes.cls.cpu().numpy() if result.boxes else []  # 클래스, (N, 1)
    probs = result.boxes.conf.cpu().numpy() if result.boxes else []  # 신뢰도 점수, (N, 1)
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes else []   # 박스 좌표, xyxy 형식, (N, 4)

    # Segmentation
    masks = result.masks.data.cpu().numpy() if result.masks is not None else []  # 마스크, (N, H, W)
    
    return boxes, masks, cls, probs  # 예측 결과 반환

def overlay(image, mask, color, alpha=0.5):
    """이미지와 세그멘테이션 마스크를 결합하여 하나의 이미지를 만듭니다."""
    mask = cv2.resize(mask, (image.shape[1], image.shape[0]))  # 마스크를 이미지 크기로 리사이즈
    colored_mask = np.zeros_like(image, dtype=np.uint8)  # 이미지와 같은 크기의 색 마스크 생성
    for c in range(3):  # BGR 각 채널에 대해
        colored_mask[:, :, c] = mask * color[c]  # 마스크를 색상으로 칠함
    
    mask_indices = mask > 0  # 마스크가 적용된 부분의 인덱스
    if mask_indices.any():  # mask_indices가 유효한지 확인
        overlay_image = image.copy()  # 원본 이미지를 복사하여 오버레이 이미지 생성
        overlay_image[mask_indices] = cv2.addWeighted(image[mask_indices], 1 - alpha, colored_mask[mask_indices], alpha, 0)  # 마스크 부분만 밝기 조절
        return overlay_image  # 오버레이된 이미지 반환
    else:
        return image  # 유효하지 않으면 원본 이미지 반환

def find_contours(mask):
    """마스크에서 외곽선을 찾습니다."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours

# 모델 로드
model = YOLO('/home/beakhongha/YOLO_ARIS/train19/weights/best.pt')

# 카메라 열기
webcam = cv2.VideoCapture(2)  # 웹캠 장치 열기
webcam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # 프레임 너비 설정
webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # 프레임 높이 설정

if not webcam.isOpened():  # 웹캠이 열리지 않은 경우
    print("웹캠을 열 수 없습니다. 프로그램을 종료합니다.")  # 오류 메시지 출력
    exit()  # 프로그램 종료

# 라벨별 색상 정의 (BGR 형식)
colors = {
    'cup': (0, 255, 0),  # 컵: 녹색
    'capsule': (0, 0, 255)  # 캡슐: 빨간색
}

while True:
    ret, frame = webcam.read()  # 웹캠에서 프레임 읽기
    if not ret:  # 프레임을 읽지 못한 경우
        print("카메라에서 프레임을 읽을 수 없습니다. 프로그램을 종료합니다.")  # 오류 메시지 출력
        break  # 루프 종료

    # 현재 프레임 예측
    boxes, masks, cls, probs = predict_on_image(model, frame, conf=0.2)

    # 탐지된 객체 출력
    detected_objects = []

    # 원본 이미지에 마스크 오버레이 및 디텍션 박스 표시
    image_with_masks = np.copy(frame)  # 원본 이미지 복사

    for box, mask, class_id, prob in zip(boxes, masks, cls, probs):  # 각 객체에 대해
        label = model.names[int(class_id)]  # 클래스 라벨 가져오기
        
        if label not in ['cup', 'capsule']:  # 'cup' 및 'capsule'이 아닌 객체 무시
            continue

        detected_objects.append(f'{label}: {prob:.2f}')  # 탐지된 객체 리스트에 추가

        color = colors.get(label, (255, 255, 255))  # 클래스에 해당하는 색상 가져오기
        
        if mask is not None and len(mask) > 0:
            # 마스크 오버레이
            image_with_masks = overlay(image_with_masks, mask, color, alpha=0.3)

            # 라벨별 외곽선 저장
            contours = find_contours(mask)

        # 디텍션 박스 및 라벨 표시
        x1, y1, x2, y2 = map(int, box)  # 박스 좌표 정수형으로 변환
        cv2.rectangle(image_with_masks, (x1, y1), (x2, y2), color, 2)  # 경계 상자 그리기
        
        # center 좌표(pixel)
        center_x_pixel = (x2 - x1) / 2 + x1
        center_y_pixel = (y2 - y1) / 2 + y1

        # center 좌표 변환(pixel to mm)
        center_x = -1 * ((center_x_pixel * (1 + (38/474) * (center_y_pixel/194)) - 19 * (center_y_pixel/194) - 62) * 800 / (474 * (1 + (38/474) * (center_y_pixel/194)))) + 400
        center_y = ((center_y_pixel - 171) * (315/194)) - 170

        center_x_mm = center_x
        center_y_mm = center_y * 0.915
        
        # 최종 center 좌표(mm)
        center_point_mm = (float(center_x_mm), float(center_y_mm))
        
        print(f"center point : ({center_x_mm:.3f}, {center_y_mm:.3f})")
        cv2.circle(image_with_masks, (int(center_x_pixel), int(center_y_pixel)), 5, (0, 0, 255), -1)  # 중심점에 빨간색 점 찍기
        cv2.putText(image_with_masks, f'{label}: {prob:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)  # 라벨 및 신뢰도 표시
        cv2.putText(image_with_masks, f'Center: ({int(center_x_mm)}, {int(center_y_mm)})', (x1, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


    # 인식 된 객체 터미널에 출력
    if detected_objects:
        print("Detected objects:", ", ".join(detected_objects))

    # 마스크가 적용된 프레임 표시
    cv2.imshow("Webcam with Segmentation Masks and Detection Boxes", image_with_masks)


    # 'q' 키를 누르면 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 자원 해제
webcam.release()  # 웹캠 장치 해제
cv2.destroyAllWindows()  # 모든 OpenCV 창 닫기
