# -*- coding: utf-8 -*-
import os

import cv2
import numpy as np

try:
    cv2.setNumThreads(int(os.getenv("PICOCLAW_OPENCV_THREADS", "1")))
except Exception:
    pass

try:
    from rknnlite.api import RKNNLite
except ImportError:
    RKNNLite = None


def softmax(x, axis=1):
    x = x - np.max(x, axis=axis, keepdims=True)
    x = np.exp(x)
    return x / np.sum(x, axis=axis, keepdims=True)


class YoloSkill:
    def __init__(self):
        self.rknn = None
        self.model_path = ""
        self.class_names = ["Stain", "Indentation", "Corner defect"]
        self.classes = []
        self.colors = [(0, 255, 0), (0, 0, 255), (255, 165, 0), (255, 0, 255)]

        self.img_size = 800
        self.conf_thres = 0.3
        self.iou_thres = 0.45

    def load_model(self, model_path):
        """加载 RKNN 模型并绑定 NPU，自动加载同名 txt 标签文件"""
        if RKNNLite is None:
            print("[Yolo Skill ERROR] 未检测到 rknnlite 依赖库，请确保在 RK3588 环境下运行。")
            return False

        model_path = os.path.abspath(model_path)
        if self.rknn is not None and self.model_path == model_path:
            return True

        try:
            if self.rknn is not None:
                self.rknn.release()
                self.rknn = None

            self.rknn = RKNNLite()
            ret = self.rknn.load_rknn(model_path)
            if ret != 0:
                print(f"[Yolo Skill ERROR] 加载 RKNN 文件失败: {model_path}")
                return False

            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
            if ret != 0:
                print("[Yolo Skill ERROR] 初始化 RKNN 三核运行时失败")
                return False

            txt_path = os.path.splitext(model_path)[0] + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    self.classes = [line.strip() for line in f.readlines() if line.strip()]
                print(f"[Yolo Skill INFO] 成功从文件映射 {len(self.classes)} 个类别: {txt_path}")
            else:
                self.classes = self.class_names.copy()
                print("[Yolo Skill WARN] 未发现同名 .txt，采用内置默认缺陷类别。")

            print("[Yolo Skill INFO] RKNN 模型加载成功！三核NPU已绑定。")
            self.model_path = model_path
            return True
        except Exception as e:
            self.model_path = ""
            print(f"[Yolo Skill ERROR] 模型加载异常: {str(e)}")
            return False

    def _letterbox(self, img):
        shape = img.shape[:2]
        r = min(self.img_size / shape[0], self.img_size / shape[1])
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw, dh = self.img_size - new_unpad[0], self.img_size - new_unpad[1]
        dw, dh = dw / 2, dh / 2

        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(
            img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        return img, r, (dw, dh)

    def _preprocess(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = np.expand_dims(img, 0)
        return img

    def _process_yolov8_outputs(self, outputs, r, pad, orig_shape):
        boxes, scores, class_ids = [], [], []
        strides = [8, 16, 32]

        model_num_classes = outputs[1].shape[1]
        if len(self.classes) < model_num_classes:
            self.classes.extend(
                [f"Class_{i}" for i in range(len(self.classes), model_num_classes)]
            )

        while len(self.colors) < len(self.classes):
            self.colors.append(tuple(int(x) for x in np.random.randint(0, 255, size=3)))

        for i, stride in enumerate(strides):
            box_feat = outputs[i * 3]
            cls_feat = outputs[i * 3 + 1]
            score_feat = outputs[i * 3 + 2]

            h, w = box_feat.shape[2], box_feat.shape[3]
            box_feat = box_feat.reshape(64, -1)
            cls_feat = cls_feat.reshape(model_num_classes, -1)
            score_feat = score_feat.reshape(-1)

            keep_idx = np.where(score_feat > self.conf_thres)[0]
            if len(keep_idx) == 0:
                continue

            cls_feat_kept = cls_feat[:, keep_idx]
            box_feat_kept = box_feat[:, keep_idx]

            cls_scores = 1 / (1 + np.exp(-cls_feat_kept))
            max_scores = np.max(cls_scores, axis=0)
            max_class_indices = np.argmax(cls_scores, axis=0)

            valid_idx = max_scores > self.conf_thres
            if not np.any(valid_idx):
                continue

            box_feat_valid = box_feat_kept[:, valid_idx]
            final_scores = max_scores[valid_idx]
            final_classes = max_class_indices[valid_idx]
            final_grids = keep_idx[valid_idx]

            box_feat_valid = box_feat_valid.reshape(4, 16, -1).transpose(2, 0, 1)
            dfl_weights = softmax(box_feat_valid, axis=2)
            dfl_points = np.arange(16, dtype=np.float32)
            box_dist = np.sum(dfl_weights * dfl_points, axis=2)

            grid_x = final_grids % w
            grid_y = final_grids // w

            x_min = (grid_x - box_dist[:, 0]) * stride
            y_min = (grid_y - box_dist[:, 1]) * stride
            x_max = (grid_x + box_dist[:, 2]) * stride
            y_max = (grid_y + box_dist[:, 3]) * stride

            dw, dh = pad
            x_min = (x_min - dw) / r
            y_min = (y_min - dh) / r
            x_max = (x_max - dw) / r
            y_max = (y_max - dh) / r

            for k in range(len(x_min)):
                boxes.append([x_min[k], y_min[k], x_max[k] - x_min[k], y_max[k] - y_min[k]])
                scores.append(float(final_scores[k]))
                class_ids.append(int(final_classes[k]))

        final_boxes, final_scores, final_class_ids = [], [], []
        if boxes:
            indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres)
            if len(indices) > 0:
                for i in indices.flatten():
                    box = boxes[i]
                    x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
                    x2 = min(orig_shape[1], int(box[0] + box[2]))
                    y2 = min(orig_shape[0], int(box[1] + box[3]))
                    final_boxes.append([x1, y1, x2, y2])
                    final_scores.append(scores[i])
                    final_class_ids.append(class_ids[i])

        return final_boxes, final_scores, final_class_ids

    def detect(self, frame, target_labels, annotate=True):
        """输入原图，返回是否检测到指定目标、画框图、命中的目标类别列表。"""
        if self.rknn is None:
            return False, frame, []

        orig_shape = frame.shape[:2]
        img_in, ratio, pad = self._letterbox(frame)
        blob = self._preprocess(img_in)

        outputs = self.rknn.inference(inputs=[blob])
        if outputs is not None and len(outputs) == 9:
            boxes, scores, class_ids = self._process_yolov8_outputs(outputs, ratio, pad, orig_shape)
        else:
            boxes, scores, class_ids = [], [], []

        target_detected = False
        detected_target_labels = []
        annotated_frame = frame.copy() if annotate else frame

        for box, score, class_id in zip(boxes, scores, class_ids):
            x1, y1, x2, y2 = box
            cls_name = self.classes[class_id] if class_id < len(self.classes) else f"ID: {class_id}"
            if annotate:
                color = self.colors[class_id] if class_id < len(self.colors) else (0, 255, 0)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    annotated_frame,
                    f"{cls_name} {score:.2f}",
                    (x1, max(y1 - 10, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

            if cls_name in target_labels:
                target_detected = True
                detected_target_labels.append(cls_name)

        return target_detected, annotated_frame, detected_target_labels

    def release(self):
        if self.rknn:
            self.rknn.release()
            self.rknn = None
            self.model_path = ""


if __name__ == "__main__":
    print("=== [测试] 开始验证 YoloSkill ===")
    yolo = YoloSkill()
    default_model = "./5319.rknn"
    model_path = input(f"请输入 .rknn 模型路径 (回车默认 {default_model}): ").strip() or default_model

    if yolo.load_model(model_path):
        img_path = "test.jpg"
        if os.path.exists(img_path):
            print(f"[测试] 找到测试图片: {img_path}")
            frame = cv2.imread(img_path)
        else:
            print(f"[测试] 当前目录未找到 {img_path}，自动生成随机图进行 NPU 压力测试。")
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        detected, res_img, labels = yolo.detect(frame, target_labels=["Stain"])
        print(f"[测试] 推理完成！是否检测到指定目标: {detected}, labels={labels}")

        cv2.imshow("YOLO Independent Test", res_img)
        print("操作提示: 按任意键退出测试")
        cv2.waitKey(0)

        yolo.release()
        cv2.destroyAllWindows()
    else:
        print("[测试] 模型加载失败，退出。")
    print("=== [测试] 结束 ===")
