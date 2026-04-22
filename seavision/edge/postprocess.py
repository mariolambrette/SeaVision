"""
YOLO ONNX pre/post processing for the edge runtime.

Preporcessing steps letterbox + normalise + transpose) and post processing
(confidence filter + NMS) must match the export settings exactly.

Dependencies: numpy, opencv-headless.
"""

from typing import List, Tuple

import cv2
import numpy as np


def letterbox(
    img: np.ndarray,
    new_shape: Tuple[int, int] = (640, 640),
) -> Tuple[np.ndarray, float, Tuple[float, float]]:
    """
    Resize and pad image to target size, preserving aspect ratio.

    Matches the Ultralytics letterbox exactly so that box coordinates
    from the model can be correctly scaled back to the original frame.

    Args:
        img: BGR image as numpy array.
        new_shape: Target (height, width).

    Returns:
        Tuple of (padded_image, scale_ratio, (pad_w, pad_h)).
    """
    h, w = img.shape[:2]
    r = min(new_shape[0] / h, new_shape[1] / w)
    new_unpad = (int(round(w * r)), int(round(h * r)))

    dw = (new_shape[1] - new_unpad[0]) / 2
    dh = (new_shape[0] - new_unpad[1]) / 2

    if (w, h) != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw + 0.1))
    img = cv2.copyMakeBorder(
        img, top, bottom, left, right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )

    return img, r, (dw, dh)


def preprocess(
    img_bgr: np.ndarray,
    imgsz: int,
) -> Tuple[np.ndarray, float, Tuple[float, float]]:
    """Preprocess a BGR frame for YOLO ONNX inference.

    Steps:
    1. Letterbox resize to (imgsz, imgsz).
    2. BGR -> RGB colour conversion.
    3. Normalise uint8 [0, 255] to float32 [0.0, 1.0].
    4. Transpose HWC -> CHW.
    5. Add batch dimension.

    Args:
        img_bgr: Original BGR frame.
        imgsz: Target size (square).

    Returns:
        Tuple of (input_tensor, scale_ratio, (pad_w, pad_h)).
        input_tensor has shape [1, 3, imgsz, imgsz], dtype float32.
    """
    img, ratio, pad = letterbox(img_bgr, new_shape=(imgsz, imgsz))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
    img = np.expand_dims(img, axis=0)    # add batch dim
    return img, ratio, pad


def postprocess(
    output: List[np.ndarray],
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
) -> List[Tuple[float, float, float, float, float, int]]:
    """Post-process YOLO ONNX output to detection tuples.

    YOLO11 ONNX output shape: [1, 4+num_classes, N]
    - 4 = cx, cy, w, h (box coordinates in input tensor space)
    - num_classes = class scores
    - N = number of candidate anchors

    Args:
        output: Raw ONNX Runtime output (list of numpy arrays).
        conf_threshold: Minimum confidence to keep a detection.
        iou_threshold: IoU threshold for non-maximum suppression.

    Returns:
        List of (x1, y1, x2, y2, confidence, class_id) tuples.
        Coordinates are in the input tensor's pixel space (i.e.
        letterboxed). The caller is responsible for scaling back to
        original frame coordinates if needed.
    """
    # Transpose from [1, 4+C, N] to [N, 4+C]
    preds = output[0].squeeze(0).T

    boxes_cxcywh = preds[:, :4]
    class_scores = preds[:, 4:]

    max_scores = np.max(class_scores, axis=1)
    class_ids = np.argmax(class_scores, axis=1)

    # Confidence filter
    mask = max_scores > conf_threshold
    boxes_cxcywh = boxes_cxcywh[mask]
    max_scores = max_scores[mask]
    class_ids = class_ids[mask]

    if len(boxes_cxcywh) == 0:
        return []

    # Convert cx,cy,w,h -> x,y,w,h for NMSBoxes (expects top-left origin)
    boxes_xywh = np.zeros_like(boxes_cxcywh)
    boxes_xywh[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2  # x1
    boxes_xywh[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2  # y1
    boxes_xywh[:, 2] = boxes_cxcywh[:, 2]                            # w
    boxes_xywh[:, 3] = boxes_cxcywh[:, 3]                            # h

    # Convert cx,cy,w,h -> x1,y1,x2,y2 for output
    boxes_xyxy = np.zeros_like(boxes_cxcywh)
    boxes_xyxy[:, 0] = boxes_xywh[:, 0]
    boxes_xyxy[:, 1] = boxes_xywh[:, 1]
    boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2]
    boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3]

    # NMS via OpenCV
    indices = cv2.dnn.NMSBoxes(
        boxes_xywh.tolist(),
        max_scores.tolist(),
        conf_threshold,
        iou_threshold,
    )

    detections = []
    if len(indices) > 0:
        for i in np.asarray(indices).reshape(-1):  # fixes Sequence[int] type error
            detections.append((
                float(boxes_xyxy[i, 0]),
                float(boxes_xyxy[i, 1]),
                float(boxes_xyxy[i, 2]),
                float(boxes_xyxy[i, 3]),
                float(max_scores[i]),
                int(class_ids[i]),
            ))

    return detections


def scale_boxes_to_original(
    detections: List[Tuple[float, float, float, float, float, int]],
    ratio: float,
    pad: Tuple[float, float],
) -> List[Tuple[float, float, float, float, float, int]]:
    """Scale detection boxes from letterboxed space back to original frame.

    Args:
        detections: Detections in letterboxed pixel space.
        ratio: Scale ratio from letterbox.
        pad: Padding offsets (pad_w, pad_h) from letterbox.

    Returns:
        Detections with coordinates in the original frame's pixel space.
    """
    pad_w, pad_h = pad
    scaled = []
    for x1, y1, x2, y2, conf, cls_id in detections:
        x1 = (x1 - pad_w) / ratio
        y1 = (y1 - pad_h) / ratio
        x2 = (x2 - pad_w) / ratio
        y2 = (y2 - pad_h) / ratio
        scaled.append((x1, y1, x2, y2, conf, cls_id))
    return scaled
