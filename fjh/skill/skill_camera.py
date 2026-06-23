# -*- coding: utf-8 -*-
import time

import cv2


class CameraSkill:
    def __init__(self, device="/dev/video21"):
        self.device = device
        self.cap = None
        self.window_name = None

    def open(self):
        try:
            cam_idx = int(self.device.replace("/dev/video", ""))
        except ValueError:
            cam_idx = 21

        self.cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            print(f"[Camera Skill ERROR] 无法打开相机设备: {self.device}")
            return False
        print(f"[Camera Skill] 相机 {self.device} 已成功开启。")
        return True

    def read_frame(self):
        if self.cap and self.cap.isOpened():
            return self.cap.read()
        return False, None

    def open_window(self, window_name="PicoClaw Camera"):
        self.window_name = window_name
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        print(f"[Camera Skill] 相机显示窗口已打开: {self.window_name}")

    def show_frame(self, frame, window_name=None):
        if window_name and window_name != self.window_name:
            self.open_window(window_name)
        elif self.window_name is None:
            self.open_window()

        cv2.imshow(self.window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        return key

    def close_window(self):
        if self.window_name:
            cv2.destroyWindow(self.window_name)
            print(f"[Camera Skill] 相机显示窗口已关闭: {self.window_name}")
            self.window_name = None

    def release_capture(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            print(f"[Camera Skill] 相机采集连接已断开: {self.device}")

    def release(self):
        self.close_window()
        self.release_capture()


if __name__ == "__main__":
    print("=== [测试] 开始验证 CameraSkill ===")
    cam = CameraSkill(device="/dev/video21")

    if cam.open():
        print("操作提示: 画面窗口内按 q 键退出相机测试")
        while True:
            ret, frame = cam.read_frame()
            if ret:
                if cam.show_frame(frame, "Camera Independent Test") == ord("q"):
                    print("[测试] 收到退出指令。")
                    break
            else:
                print("[警告] 无法读取画面帧，1秒后重试。")
                time.sleep(1)

        cam.release()
    print("=== [测试] 结束 ===")
