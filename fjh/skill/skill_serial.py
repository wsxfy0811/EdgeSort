# -*- coding: utf-8 -*-
import os
import serial
import threading
import time


class SerialSkill:
    def __init__(self, port="/dev/ttyS9", baud=115200):
        self.port = port
        self.baud = baud
        self.ser = None
        self.arduino_ready = True
        self.trigger_count = 0
        self.running = False
        self.listener_thread = None
        self.status_callback = None
        self.pending_removal = False
        self.lock = threading.Lock()
        self.default_command = os.getenv("PICOCLAW_ARM_DEFAULT_COMMAND", "D")
        line_ending = os.getenv("PICOCLAW_ARM_LINE_ENDING", "NONE").upper()
        if line_ending == "CRLF":
            self.line_ending = "\r\n"
        elif line_ending == "LF":
            self.line_ending = "\n"
        else:
            self.line_ending = ""

    def set_status_callback(self, callback):
        self.status_callback = callback

    def is_ready(self):
        return self.arduino_ready and self.ser is not None and self.ser.is_open

    def wait_until_ready(self, timeout=None):
        started_at = time.time()
        while self.ser and self.ser.is_open and not self.arduino_ready:
            if timeout is not None and time.time() - started_at >= timeout:
                return False
            time.sleep(0.05)
        return self.arduino_ready

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.ser.reset_input_buffer()
            self.running = True
            self.listener_thread = threading.Thread(target=self._listener, daemon=True)
            self.listener_thread.start()
            print(f"[Serial Skill] 串口 {self.port} 连接成功，监听线程已启动。")
            return True
        except Exception as e:
            print(f"[Serial Skill ERROR] 串口打开失败: {e}")
            return False

    def _handle_status(self, event_name, decoded):
        self.arduino_ready = True
        print(f"\n[Serial Skill] 收到下位机 {event_name}：{decoded}")

        if self.pending_removal:
            self.pending_removal = False
            if self.status_callback:
                self.status_callback(event_name, decoded)

    def _listener(self):
        """后台串口异步非阻塞接收线程"""
        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    line = self.ser.readline()
                    if line:
                        decoded = line.decode("utf-8", errors="ignore").strip()
                        upper = decoded.upper()
                        if "READY" in upper:
                            self._handle_status("READY", decoded)
                        elif "FINISH" in upper or "FINISHED" in upper:
                            self._handle_status("FINISH", decoded)
                except Exception as exc:
                    print(f"[Serial Skill WARNING] 接收异常: {exc}")
            time.sleep(0.01)

    def send_command(self, command):
        """发送机械臂分拣指令。Arduino 端当前只读取单字符 N/D。"""
        with self.lock:
            if not self.ser or not self.ser.is_open:
                print("[Serial Skill ERROR] 串口未打开，无法发送机械臂指令。")
                return False
            if not self.arduino_ready:
                return False

            try:
                command = (command or "").strip().upper()
                if command not in ("N", "D"):
                    print(f"[Serial Skill ERROR] 非法机械臂指令: {command!r}")
                    return False

                payload = f"{command}{self.line_ending}".encode("utf-8")
                written = self.ser.write(payload)
                self.ser.flush()
                self.arduino_ready = False
                self.pending_removal = True
                self.trigger_count += 1
                print(
                    f"[Serial Skill] 已发送机械臂指令: {payload!r}, "
                    f"bytes={written}, count={self.trigger_count}"
                )
                return True
            except Exception as e:
                print(f"[Serial Skill ERROR] 发送机械臂指令失败: {e}")
                return False

    def send_start(self):
        """兼容旧调用；默认发送 D。新逻辑请使用 send_command('N'/'D')。"""
        return self.send_command(self.default_command)

    def release(self):
        self.running = False
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=1.0)
        if self.ser:
            self.ser.close()
            self.ser = None


if __name__ == "__main__":
    print("=== [测试] 开始验证 SerialSkill ===")
    ser = SerialSkill(port="/dev/ttyS9", baud=115200)

    def on_done(event_name, message):
        print(f"[测试] 收到完成回调: {event_name}, {message}")

    ser.set_status_callback(on_done)
    if ser.connect():
        print("操作提示: 输入 n 发送N，输入 d 发送D，输入 q 退出")
        try:
            while True:
                cmd = input(">> ").strip().lower()
                if cmd in ("n", "d"):
                    if ser.send_command(cmd.upper()):
                        print(f"[测试] 已发送 {cmd.upper()}，累计触发次数: {ser.trigger_count}")
                    else:
                        print("[测试] 发送失败，下位机可能未就绪。")
                elif cmd == "q":
                    break
        except KeyboardInterrupt:
            pass
        finally:
            ser.release()
    print("=== [测试] 结束 ===")
