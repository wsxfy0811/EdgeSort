# -*- coding: utf-8 -*-
import argparse
import os
import queue
import re
import threading
import time

import cv2

from skill_camera import CameraSkill
from skill_serial import SerialSkill
from skill_voice import VoiceListener, VoiceSkill
from skill_yolo import YoloSkill


SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.getenv("PICOCLAW_MODEL_DIR", SKILL_DIR)
DEFAULT_CAMERA = os.getenv("PICOCLAW_CAMERA_DEVICE", "/dev/video21")
DEFAULT_SERIAL = os.getenv("PICOCLAW_SERIAL_PORT", "/dev/ttyS9")
DEFAULT_BAUD = int(os.getenv("PICOCLAW_SERIAL_BAUD", "115200"))
try:
    cv2.setNumThreads(int(os.getenv("PICOCLAW_OPENCV_THREADS", "1")))
except Exception:
    pass
ARM_COMMAND_BY_TARGET = {
    "Stain": "N",
    "Indentation": "D",
    "Corner defect": "D",
}
TARGET_PRIORITY = ("Indentation", "Corner defect", "Stain")

TARGET_ALIASES = {
    "1": ("Stain", "1污渍"),
    "一": ("Stain", "1污渍"),
    "衣": ("Stain", "1污渍"),
    "依": ("Stain", "1污渍"),
    "壹": ("Stain", "1污渍"),
    "幺": ("Stain", "1污渍"),
    "污渍": ("Stain", "1污渍"),
    "污迹": ("Stain", "1污渍"),
    "物资": ("Stain", "1污渍"),
    "无渍": ("Stain", "1污渍"),
    "污子": ("Stain", "1污渍"),
    "五子": ("Stain", "1污渍"),
    "误资": ("Stain", "1污渍"),
    "脏污": ("Stain", "1污渍"),
    "stain": ("Stain", "1污渍"),
    "2": ("Indentation", "2划痕"),
    "二": ("Indentation", "2划痕"),
    "贰": ("Indentation", "2划痕"),
    "儿": ("Indentation", "2划痕"),
    "而": ("Indentation", "2划痕"),
    "划痕": ("Indentation", "2划痕"),
    "华痕": ("Indentation", "2划痕"),
    "花痕": ("Indentation", "2划痕"),
    "刮痕": ("Indentation", "2划痕"),
    "压痕": ("Indentation", "2划痕"),
    "indentation": ("Indentation", "2划痕"),
    "3": ("Corner defect", "3缺角"),
    "三": ("Corner defect", "3缺角"),
    "叁": ("Corner defect", "3缺角"),
    "山": ("Corner defect", "3缺角"),
    "缺角": ("Corner defect", "3缺角"),
    "缺脚": ("Corner defect", "3缺角"),
    "缺觉": ("Corner defect", "3缺角"),
    "角缺陷": ("Corner defect", "3缺角"),
    "corner defect": ("Corner defect", "3缺角"),
}

CHINESE_DIGITS = {
    "零": "0",
    "〇": "0",
    "一": "1",
    "幺": "1",
    "衣": "1",
    "依": "1",
    "壹": "1",
    "二": "2",
    "两": "2",
    "贰": "2",
    "儿": "2",
    "而": "2",
    "三": "3",
    "叁": "3",
    "山": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

START_KEYWORDS = ("启动", "开始", "检测", "打开", "开启", "开", "启用")
DOMAIN_KEYWORDS = (
    "飞机盒",
    "飞机和",
    "飞机合",
    "飞机河",
    "飞机禾",
    "飞鸡盒",
    "飞鸡河",
    "飞几盒",
    "飞几河",
    "飞行盒",
    "飞机",
    "缺陷",
    "检测",
    "警测",
    "检侧",
    "系统",
)
WAKE_WORDS = ("小智", "小志", "晓智", "小字", "字小字", "picoclaw", "pico claw")
STOP_KEYWORDS = ("停止", "终止", "退出", "结束", "stop")
EXIT_KEYWORDS = ("退出", "退出程序", "关闭程序", "结束程序")
YES_WORDS = ("是", "确认", "可以", "使用", "好的", "好", "yes", "确定")
NO_WORDS = ("否", "不", "不要", "取消", "no")
CHANGE_WORDS = ("更换", "修改", "换", "变更")
REMOVE_WORDS = ("移除", "删除", "去掉", "取消")
REPORT_WORDS = ("汇报", "回报", "报告", "播报统计", "统计", "报一下", "汇报一下")
MODEL_WORDS = ("模型", "model")
TARGET_WORDS = ("目标", "标签", "缺陷", "检测目标")
CONTINUE_WORDS = ("继续", "恢复", "开始", "启动", "执行", "可以", "好的", "好", "是")
FILLER_TEXTS = ("嗯", "嗯嗯", "啊", "啊啊", "呃", "呃呃", "哦", "噢", "哎", "唉", "喂")
SHORT_COMMAND_TEXTS = (
    "1",
    "2",
    "3",
    "一",
    "二",
    "三",
    "衣",
    "依",
    "壹",
    "幺",
    "贰",
    "儿",
    "而",
    "叁",
    "山",
    "好",
    "是",
    "不",
    "否",
)
TEXT_REPLACEMENTS = {
    "小志": "小智",
    "晓智": "小智",
    "小字": "小智",
    "飞机和": "飞机盒",
    "飞机合": "飞机盒",
    "飞机核": "飞机盒",
    "飞机河": "飞机盒",
    "飞机禾": "飞机盒",
    "飞鸡盒": "飞机盒",
    "飞鸡河": "飞机盒",
    "飞几盒": "飞机盒",
    "飞几河": "飞机盒",
    "飞行盒": "飞机盒",
    "警测": "检测",
    "检侧": "检测",
    "侦测": "检测",
    "物资": "污渍",
    "无渍": "污渍",
    "污子": "污渍",
    "五子": "污渍",
    "误资": "污渍",
    "华痕": "划痕",
    "花痕": "划痕",
    "刮痕": "划痕",
    "缺脚": "缺角",
    "缺觉": "缺角",
}
PINYIN_CHARS = {
    "唤": "huan",
    "醒": "xing",
    "小": "xiao",
    "晓": "xiao",
    "智": "zhi",
    "志": "zhi",
    "字": "zi",
    "飞": "fei",
    "机": "ji",
    "鸡": "ji",
    "几": "ji",
    "盒": "he",
    "何": "he",
    "和": "he",
    "合": "he",
    "核": "he",
    "河": "he",
    "禾": "he",
    "荷": "he",
    "检": "jian",
    "减": "jian",
    "捡": "jian",
    "测": "ce",
    "侧": "ce",
    "厕": "ce",
    "缺": "que",
    "角": "jiao",
    "脚": "jiao",
    "觉": "jiao",
    "污": "wu",
    "屋": "wu",
    "乌": "wu",
    "吴": "wu",
    "物": "wu",
    "无": "wu",
    "误": "wu",
    "五": "wu",
    "渍": "zi",
    "资": "zi",
    "自": "zi",
    "紫": "zi",
    "子": "zi",
    "质": "zhi",
    "迹": "ji",
    "脏": "zang",
    "划": "hua",
    "画": "hua",
    "话": "hua",
    "化": "hua",
    "华": "hua",
    "花": "hua",
    "痕": "hen",
    "很": "hen",
    "恨": "hen",
    "刮": "gua",
    "压": "ya",
    "模": "mo",
    "摸": "mo",
    "磨": "mo",
    "魔": "mo",
    "型": "xing",
    "形": "xing",
    "行": "xing",
    "目": "mu",
    "标": "biao",
    "签": "qian",
    "确": "que",
    "却": "que",
    "雀": "que",
    "认": "ren",
    "任": "ren",
    "人": "ren",
    "定": "ding",
    "可": "ke",
    "以": "yi",
    "好": "hao",
    "开": "kai",
    "始": "shi",
    "继": "ji",
    "续": "xu",
    "需": "xu",
    "要": "yao",
    "添": "tian",
    "天": "tian",
    "加": "jia",
    "家": "jia",
    "还": "hai",
    "再": "zai",
    "更": "geng",
    "跟": "geng",
    "根": "geng",
    "换": "huan",
    "环": "huan",
    "修": "xiu",
    "改": "gai",
    "变": "bian",
    "移": "yi",
    "除": "chu",
    "删": "shan",
    "去": "qu",
    "掉": "diao",
    "退": "tui",
    "推": "tui",
    "腿": "tui",
    "出": "chu",
    "关": "guan",
    "闭": "bi",
    "程": "cheng",
    "序": "xu",
    "实": "shi",
    "时": "shi",
    "语": "yu",
    "音": "yin",
    "停": "ting",
    "止": "zhi",
    "终": "zhong",
    "结": "jie",
    "束": "shu",
    "启": "qi",
    "动": "dong",
    "打": "da",
    "用": "yong",
    "取": "qu",
    "消": "xiao",
    "不": "bu",
    "否": "fou",
}


def normalize_text(text):
    processed = (text or "").strip()
    for src, dst in TEXT_REPLACEMENTS.items():
        processed = processed.replace(src, dst)
    return re.sub(r"\s+", " ", processed).lower()


def compact_pinyin(text):
    return "".join(PINYIN_CHARS.get(ch, ch.lower()) for ch in re.sub(r"\s+", "", text or ""))


def contains_any_keyword(text, words):
    normalized = normalize_text(text)
    if any(word in normalized for word in words):
        return True
    normalized_pinyin = compact_pinyin(normalized)
    for word in words:
        compact_word = re.sub(r"\s+", "", word or "")
        if len(compact_word) <= 1:
            continue
        word_pinyin = compact_pinyin(compact_word)
        if word_pinyin and word_pinyin in normalized_pinyin:
            return True
    return False


def is_valid_command_text(text):
    compact = re.sub(r"[\s,，.。!！?？、:：;；'\"]+", "", text or "")
    if not compact:
        return False
    if compact in FILLER_TEXTS:
        return False
    if len(compact) <= 1 and compact not in SHORT_COMMAND_TEXTS:
        return False
    return True


def has_wake_word(text):
    return contains_any_keyword(text, WAKE_WORDS)


def has_start_intent(text):
    return contains_any_keyword(text, START_KEYWORDS)


def has_domain_intent(text):
    return contains_any_keyword(text, DOMAIN_KEYWORDS)


def is_wake_only(text):
    return has_wake_word(text) and not has_start_intent(text) and not has_domain_intent(text)


def is_start_command(text):
    has_wake = has_wake_word(text)
    has_start = has_start_intent(text)
    has_domain = has_domain_intent(text)
    return (has_wake and (has_start or has_domain)) or (has_domain and has_start)


def is_stop_command(text):
    return contains_any_keyword(text, STOP_KEYWORDS)


def is_exit_command(text):
    return contains_any_keyword(text, EXIT_KEYWORDS)


def is_yes(text):
    return contains_any_keyword(text, YES_WORDS)


def is_no(text):
    return contains_any_keyword(text, NO_WORDS)


def is_stop_confirm(text):
    return is_yes(text) or is_stop_command(text)


def has_change_intent(text):
    return contains_any_keyword(text, CHANGE_WORDS)


def has_report_intent(text):
    return contains_any_keyword(text, REPORT_WORDS)


def has_remove_intent(text):
    return contains_any_keyword(text, REMOVE_WORDS)


def wants_model_change(text):
    return contains_any_keyword(text, MODEL_WORDS)


def wants_target_change(text):
    return contains_any_keyword(text, TARGET_WORDS)


def is_continue_command(text):
    return is_yes(text) or contains_any_keyword(text, CONTINUE_WORDS)


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def list_models(model_dir=MODEL_DIR):
    if not os.path.isdir(model_dir):
        return []
    return sorted(name for name in os.listdir(model_dir) if name.lower().endswith(".rknn"))


def model_display_name(path_or_name):
    return os.path.splitext(os.path.basename(path_or_name or ""))[0]


def extract_model_name(text):
    normalized = normalize_text(text)
    match = re.search(r"([\w.-]+\.rknn)", normalized)
    if match:
        return match.group(1)

    number_match = re.search(r"\b(\d+)\b", normalized)
    if number_match:
        return f"{number_match.group(1)}.rknn"

    chinese_number_match = re.search(r"[零〇一幺衣依壹二两贰儿而三叁山四五六七八九]+", text or "")
    if chinese_number_match:
        digits = "".join(CHINESE_DIGITS[ch] for ch in chinese_number_match.group(0))
        return f"{digits}.rknn"

    return ""


def _add_target(targets, target):
    if target and target[0] not in [item[0] for item in targets]:
        targets.append(target)


def extract_targets(text):
    normalized = normalize_text(text)
    compact = re.sub(r"[\s,，.。!！?？、:：;；'\"]+", "", text or "").lower()
    normalized_pinyin = compact_pinyin(normalized)
    targets = []

    if (
        re.search(r"(?<!\d)1(?!\d)", normalized)
        or any(word in compact for word in ("一", "衣", "依", "壹", "幺", "1污渍"))
    ):
        _add_target(targets, TARGET_ALIASES["1"])
    if (
        re.search(r"(?<!\d)2(?!\d)", normalized)
        or any(word in compact for word in ("二", "贰", "儿", "而", "2划痕"))
    ):
        _add_target(targets, TARGET_ALIASES["2"])
    if (
        re.search(r"(?<!\d)3(?!\d)", normalized)
        or any(word in compact for word in ("三", "叁", "山", "3缺角"))
    ):
        _add_target(targets, TARGET_ALIASES["3"])

    for alias, target in TARGET_ALIASES.items():
        if alias in ("1", "2", "3", "一", "衣", "依", "壹", "幺", "二", "贰", "儿", "而", "三", "叁", "山"):
            continue
        alias_pinyin = compact_pinyin(alias)
        if alias in normalized or (alias_pinyin and alias_pinyin in normalized_pinyin):
            _add_target(targets, target)

    return targets


class DetectionTask:
    def __init__(self, model_path, target_labels, target_cns, voice, show_window=True):
        self.model_path = model_path
        self.target_labels = target_labels
        self.target_cns = target_cns
        self.voice = voice
        self.show_window = show_window
        self.stop_event = threading.Event()
        self.thread = None
        self.serial = None
        self.trigger_count = 0
        self.started_event = threading.Event()
        self.start_failed = False
        self.fail_reason = ""
        self.last_arm_busy_log_at = 0.0
        self.wait_for_arm_on_stop = True
        self.suppress_finished_speech = False
        self.sorting_enabled = threading.Event()
        self.sorting_enabled.set()
        self.runtime_enabled = threading.Event()
        self.runtime_enabled.set()
        self.config_lock = threading.Lock()
        self.camera = None
        self.serial = None
        self.yolo = None
        self.detect_interval = float(os.getenv("PICOCLAW_DETECT_INTERVAL", "0.06"))
        self.last_detect_at = 0.0
        self.hardware_connected = False

    def arm_command_for_target(self, label):
        return ARM_COMMAND_BY_TARGET.get(label)

    def target_name(self, label):
        with self.config_lock:
            for target_label, target_cn in zip(self.target_labels, self.target_cns):
                if target_label == label:
                    return target_cn
        return label

    def select_detected_label(self, detected_labels):
        with self.config_lock:
            target_labels = self.target_labels[:]
        detected_set = set(detected_labels)
        for label in TARGET_PRIORITY:
            if label in detected_set and label in target_labels:
                return label
        for label in detected_labels:
            if label in target_labels:
                return label
        return target_labels[0]

    def set_sorting_enabled(self, enabled):
        if enabled:
            self.sorting_enabled.set()
            print("[Detection] 分拣执行已恢复。")
        else:
            self.sorting_enabled.clear()
            print("[Detection] 分拣执行已暂停。")

    def update_targets(self, target_labels, target_cns):
        with self.config_lock:
            self.target_labels = target_labels[:]
            self.target_cns = target_cns[:]
        print(f"[Detection] 检测目标已更新为: {target_labels}")

    def update_config(self, model_path, target_labels, target_cns):
        with self.config_lock:
            self.model_path = model_path
            self.target_labels = target_labels[:]
            self.target_cns = target_cns[:]
        print(
            "[Detection] 检测参数已更新: "
            f"model={model_path}, targets={target_labels}"
        )

    def suspend_runtime(self):
        self.runtime_enabled.clear()
        self.sorting_enabled.clear()
        print("[Detection] 检测硬件使用已暂停，等待重新配置。")

    def resume_runtime(self):
        self.runtime_enabled.set()
        self.sorting_enabled.set()
        print("[Detection] 检测硬件使用已恢复。")

    def wait_until_arm_ready(self, timeout=None):
        if self.serial and self.serial.ser and self.serial.ser.is_open:
            return self.serial.wait_until_ready(timeout=timeout)
        return True

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join()

    def _on_sort_finished(self, event_name, message):
        if not self.suppress_finished_speech:
            self.voice.speak("缺陷品已移除。")

    def _ensure_model_loaded(self):
        with self.config_lock:
            model_path = self.model_path
        if not self.yolo.load_model(model_path):
            self.fail_reason = f"模型加载失败: {model_path}"
            self.start_failed = True
            self.voice.speak("模型加载失败，请检查模型路径。")
            return False
        return True

    def _connect_hardware(self):
        if self.hardware_connected:
            return True

        print(f"[Detection] 正在打开相机: {DEFAULT_CAMERA}")
        if not self.camera.open():
            self.fail_reason = f"相机打开失败: {DEFAULT_CAMERA}"
            self.start_failed = True
            self.voice.speak("相机打开失败，请检查相机设备。")
            return False
        if self.show_window and self.camera.window_name is None:
            self.camera.open_window("PicoClaw Smart Camera")

        print(f"[Detection] 正在连接串口: {DEFAULT_SERIAL}, baud={DEFAULT_BAUD}")
        if not self.serial.connect():
            self.camera.release_capture()
            self.fail_reason = f"串口连接失败: {DEFAULT_SERIAL}"
            self.start_failed = True
            self.voice.speak("串口连接失败，请检查机械臂连接。")
            return False

        self.serial.set_status_callback(self._on_sort_finished)
        self.hardware_connected = True
        return True

    def _disconnect_hardware(self, wait_for_arm=True):
        if not self.hardware_connected:
            return
        if (
            wait_for_arm
            and self.serial
            and self.serial.ser
            and self.serial.ser.is_open
            and not self.serial.is_ready()
        ):
            print("[Detection] 暂停前等待机械臂完成当前动作并返回 READY。")
            self.serial.wait_until_ready()
        if self.serial:
            self.serial.release()
        if self.camera:
            self.camera.release_capture()
        self.hardware_connected = False

    def _run(self):
        self.camera = CameraSkill(DEFAULT_CAMERA)
        self.serial = SerialSkill(DEFAULT_SERIAL, DEFAULT_BAUD)
        self.yolo = YoloSkill()

        self.voice.speak("系统启动中，正在加载模型与硬件。")
        try:
            print(f"[Detection] 正在加载模型: {self.model_path}")
            if not self._ensure_model_loaded():
                self.started_event.set()
                return
            if not self._connect_hardware():
                self.started_event.set()
                return

            self.started_event.set()
            unconfigured_labels = [
                label for label in self.target_labels if not self.arm_command_for_target(label)
            ]
            if unconfigured_labels:
                self.fail_reason = f"目标标签没有配置机械臂指令: {unconfigured_labels}"
                self.start_failed = True
                self.voice.speak("目标标签没有配置机械臂指令，任务已停止。")
                return
            for label in self.target_labels:
                print(
                    f"[Detection] 目标标签 {label} 对应机械臂指令 "
                    f"{self.arm_command_for_target(label)!r}"
                )

            target_text = "、".join(self.target_cns)
            self.voice.speak(f"相机已打开，机械臂已连接，开始检测{target_text}。")
            self.voice.wait_until_done()

            while not self.stop_event.is_set():
                if not self.runtime_enabled.is_set():
                    self._disconnect_hardware(wait_for_arm=True)
                    time.sleep(0.05)
                    continue

                if not self._ensure_model_loaded() or not self._connect_hardware():
                    time.sleep(0.5)
                    continue

                if self.detect_interval > 0:
                    wait_seconds = self.detect_interval - (time.time() - self.last_detect_at)
                    if wait_seconds > 0:
                        time.sleep(wait_seconds)
                    self.last_detect_at = time.time()

                ret, frame = self.camera.read_frame()
                if not ret:
                    print("[Detection WARNING] 相机已打开，但读取画面失败。")
                    time.sleep(0.01)
                    continue

                with self.config_lock:
                    active_target_labels = self.target_labels[:]

                target_detected, annotated_frame, detected_labels = self.yolo.detect(
                    frame, active_target_labels, annotate=self.show_window
                )

                if target_detected and self.sorting_enabled.is_set():
                    detected_label = self.select_detected_label(detected_labels)
                    arm_command = self.arm_command_for_target(detected_label)
                    if self.serial.is_ready() and self.serial.send_command(arm_command):
                        self.trigger_count = self.serial.trigger_count
                        label_text = self.target_name(detected_label)
                        self.voice.speak(
                            f"已识别出目标标签{label_text}，已发送{arm_command}指令，开始分拣。"
                        )

                if self.show_window:
                    annotated_frame = self._draw_status(annotated_frame, self.serial.trigger_count)
                    key = self.camera.show_frame(annotated_frame, "PicoClaw Smart Camera")
                    if key == ord("q"):
                        self.stop_event.set()
        except Exception as exc:
            print(f"[Detection ERROR] {exc}")
            self.voice.speak("检测任务发生异常，任务已停止。")
        finally:
            if self.serial:
                self.trigger_count = self.serial.trigger_count
            self._disconnect_hardware(wait_for_arm=self.wait_for_arm_on_stop)
            if self.camera:
                self.camera.release()
            if self.yolo:
                self.yolo.release()

    def _draw_status(self, frame, sorted_count):
        with self.config_lock:
            target_text = ",".join(self.target_labels)
        mode_text = "ACTIVE" if self.sorting_enabled.is_set() else "PAUSED"
        cv2.putText(
            frame,
            f"Targets: {target_text}",
            (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Sorted: {sorted_count}",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Sorting: {mode_text}",
            (10, 105),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2,
        )
        return frame


class PicoClawOrchestrator:
    def __init__(self, model_dir=MODEL_DIR, voice=None, listener=None, release_resources=True):
        self.model_dir = model_dir
        self.voice = voice or VoiceSkill()
        self.listener = listener or VoiceListener(speaker=self.voice)
        self.release_resources = release_resources
        self.commands = queue.Queue()
        self.active_task = None
        self.running = True
        self.last_wake_at = 0.0
        self.last_wake_response_at = 0.0
        self.pending_command_parts = []
        self.wake_timeout_seconds = 10.0
        self.show_window = env_flag("PICOCLAW_SHOW_WINDOW", True)
        self.current_model_path = ""
        self.current_target_labels = []
        self.current_target_cns = []
        self.last_trigger_count = 0
        self.state = "WAIT_WAKE"

    def _on_text(self, text):
        if not is_valid_command_text(text):
            return
        print(f"[Voice Command] {text}")
        self.commands.put(text)

    def _remember_command_part(self, text):
        now = time.time()
        self.pending_command_parts = [
            item for item in self.pending_command_parts if now - item[0] <= self.wake_timeout_seconds
        ]
        self.pending_command_parts.append((now, text))

    def _combined_recent_command(self):
        now = time.time()
        parts = [
            text for ts, text in self.pending_command_parts if now - ts <= self.wake_timeout_seconds
        ]
        return " ".join(parts)

    def _within_wake_window(self):
        return time.time() - self.last_wake_at <= self.wake_timeout_seconds

    def start_listener(self):
        if not self.listener.running:
            self.listener.start_listen(on_text=self._on_text)

    def stop_listener(self):
        self.listener.stop_listen()

    def start_detection_task(self, model_path, target_labels, target_cns):
        self.current_model_path = model_path
        self.current_target_labels = target_labels[:]
        self.current_target_cns = target_cns[:]
        self.active_task = DetectionTask(
            model_path,
            target_labels,
            target_cns,
            self.voice,
            show_window=self.show_window,
        )
        self.active_task.start()
        if not self.active_task.started_event.wait(timeout=20.0):
            print("[Detection WARNING] 检测任务启动较慢，仍在后台初始化。")
            self.voice.speak("检测任务正在后台初始化，请稍候。")
        elif self.active_task.start_failed:
            print(f"[Detection ERROR] {self.active_task.fail_reason}")
            self.active_task = None

    def active_task_running(self):
        return (
            self.active_task is not None
            and self.active_task.thread is not None
            and self.active_task.thread.is_alive()
        )

    def current_trigger_count(self):
        if self.active_task is not None:
            self.last_trigger_count = self.active_task.trigger_count
        return self.last_trigger_count

    def report_text(self):
        count = self.current_trigger_count()
        target_text = "、".join(self.current_target_cns) if self.current_target_cns else "未设置"
        return f"当前共计识别并分拣缺陷品{count}件，目标标签为{target_text}。"

    def speak_report(self, wait_for_arm=False):
        sorting_was_enabled = False
        if wait_for_arm and self.active_task is not None:
            sorting_was_enabled = self.active_task.sorting_enabled.is_set()
            self.active_task.set_sorting_enabled(False)
            timeout = float(os.getenv("PICOCLAW_REPORT_ARM_WAIT_TIMEOUT", "20"))
            self.active_task.wait_until_arm_ready(timeout=None if timeout <= 0 else timeout)
            self.last_trigger_count = self.active_task.trigger_count
        self.voice.speak(self.report_text())
        self.voice.wait_until_done(timeout=8)
        if wait_for_arm and self.active_task is not None and sorting_was_enabled and self.state == "RUNNING":
            self.active_task.set_sorting_enabled(True)

    def stop_active_task_for_interaction(self):
        if not self.active_task_running():
            return 0

        task = self.active_task
        count = task.trigger_count
        task.stop_event.set()
        task.suppress_finished_speech = True
        self.voice.clear_pending()
        task.stop()
        count = task.trigger_count
        self.last_trigger_count = count
        self.voice.clear_pending()
        self.active_task = None
        return count

    def pause_active_task_for_interaction(self):
        if not self.active_task_running():
            return
        self.active_task.suspend_runtime()
        self.active_task.suppress_finished_speech = True
        self.voice.clear_pending()

    def request_exit(self):
        if self.active_task_running():
            self.active_task.set_sorting_enabled(False)
            self.active_task.suppress_finished_speech = True
            self.voice.clear_pending()
            self.speak_report(wait_for_arm=True)
        self.voice.speak("已退出程序。")
        self.voice.wait_until_done(timeout=5)
        self.running = False

    def reset_pending_config(self):
        self.current_model_path = ""
        self.current_target_labels = []
        self.current_target_cns = []

    def resolve_model_from_text(self, text):
        model_name = extract_model_name(text)
        if not model_name:
            return None

        available = list_models(self.model_dir)
        exact = next((name for name in available if name.lower() == model_name.lower()), None)
        if exact:
            return os.path.join(self.model_dir, exact)

        self.voice.speak(
            f"未找到{model_display_name(model_name)}模型。当前可用模型有：{'，'.join(available)}。请重新说模型编号。"
        )
        return None

    def add_targets_from_text(self, text):
        targets = extract_targets(text)
        if not targets:
            return False
        for label, cn in targets:
            if label not in self.current_target_labels:
                self.current_target_labels.append(label)
                self.current_target_cns.append(cn)
        return True

    def remove_targets_from_text(self, text):
        targets = extract_targets(text)
        if not targets:
            return False

        removed = []
        for label, cn in targets:
            if label in self.current_target_labels:
                index = self.current_target_labels.index(label)
                self.current_target_labels.pop(index)
                if index < len(self.current_target_cns):
                    self.current_target_cns.pop(index)
                removed.append(cn)

        if removed:
            self.voice.speak(f"已移除{'、'.join(removed)}标签。")
            return True

        self.voice.speak("当前没有这个检测标签。")
        return True

    def prompt_wake(self):
        self.state = "WAIT_WAKE"
        self.voice.speak("请使用语音唤醒小智。")

    def prompt_detection_model(self):
        self.state = "WAIT_MODEL"
        self.reset_pending_config()
        self.voice.speak("已进入飞机盒缺陷检测。请告诉我使用什么模型，例如一。")

    def prompt_detect_command(self):
        self.state = "WAIT_DETECT"
        self.voice.speak("我在。请说检测指令。")

    def prompt_model(self):
        self.state = "WAIT_MODEL"
        self.voice.speak("已开启检测任务。请告诉我使用什么模型，例如一。")

    def prompt_target(self):
        self.state = "WAIT_TARGET"
        self.voice.speak("请告诉我需要检测的缺陷目标标签：1污渍，2划痕，3缺角。")

    def prompt_add_target(self):
        self.state = "WAIT_ADD_TARGET"
        self.voice.speak("请问是否还需要添加需要检测的缺陷目标标签？")

    def prompt_after_stop(self):
        self.state = "WAIT_AFTER_STOP"
        self.voice.speak("我在。请问是要更换参数还是退出程序？")

    def should_add_more_targets(self, text):
        if contains_any_keyword(text, ("不需要", "不用", "不要", "否", "不")):
            return False
        return contains_any_keyword(text, ("需要", "添加", "还要", "继续添加", "再加", "要"))

    def should_finish_targets(self, text):
        return contains_any_keyword(
            text,
            ("不需要", "不用", "不要", "否", "不", "开始", "检测", "确认", "确定", "可以", "好"),
        )

    def start_current_task(self):
        if not self.current_model_path:
            self.prompt_model()
            return
        if not self.current_target_labels:
            self.prompt_target()
            return
        self.state = "RUNNING"
        if self.active_task_running():
            self.active_task.update_config(
                self.current_model_path,
                self.current_target_labels,
                self.current_target_cns,
            )
            self.active_task.suppress_finished_speech = False
            self.active_task.resume_runtime()
            self.voice.speak("参数已更换完毕，继续检测任务。")
            return

        self.start_detection_task(
            self.current_model_path,
            self.current_target_labels,
            self.current_target_cns,
        )
        if not self.active_task_running() and self.active_task is None:
            self.state = "WAIT_AFTER_STOP"

    def process_realtime_text(self, text):
        if is_exit_command(text):
            self.request_exit()
            return

        if has_report_intent(text):
            self.speak_report(wait_for_arm=self.state == "RUNNING")
            return

        if self.state == "WAIT_WAKE":
            if has_wake_word(text):
                self.prompt_detect_command()
            return

        if self.state == "WAIT_DETECT":
            if "检测" in normalize_text(text) or is_start_command(text):
                self.prompt_model()
            return

        if self.state == "WAIT_MODEL":
            model_path = self.resolve_model_from_text(text)
            if model_path:
                self.current_model_path = model_path
                self.voice.speak(f"已使用{model_display_name(model_path)}模型。")
                self.prompt_target()
            return

        if self.state == "WAIT_TARGET":
            if has_remove_intent(text):
                self.remove_targets_from_text(text)
                self.prompt_target()
                return
            if self.add_targets_from_text(text):
                target_text = "、".join(self.current_target_cns)
                self.voice.speak(f"已使用{target_text}标签。")
                self.prompt_add_target()
            return

        if self.state == "WAIT_ADD_TARGET":
            if has_remove_intent(text):
                self.remove_targets_from_text(text)
                self.prompt_add_target()
                return
            if self.should_add_more_targets(text):
                self.voice.speak("好的。")
                self.prompt_target()
            elif self.should_finish_targets(text):
                self.start_current_task()
            elif self.add_targets_from_text(text):
                target_text = "、".join(self.current_target_cns)
                self.voice.speak(f"已使用{target_text}标签。")
                self.prompt_add_target()
            return

        if self.state == "RUNNING":
            if has_wake_word(text):
                self.pause_active_task_for_interaction()
                self.speak_report(wait_for_arm=True)
                self.prompt_after_stop()
            return

        if self.state == "WAIT_AFTER_STOP":
            if has_change_intent(text):
                self.reset_pending_config()
                self.prompt_model()
            return

    def run(self):
        self.prompt_wake()
        self.start_listener()

        try:
            while self.running:
                try:
                    text = self.commands.get(timeout=0.2)
                except queue.Empty:
                    continue

                self.process_realtime_text(text)
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.stop_listener()
            if self.active_task:
                self.active_task.stop()
            if self.release_resources:
                self.voice.release()


def run_direct_mode(args):
    voice = VoiceSkill()
    parsed_targets = extract_targets(args.target)
    if parsed_targets:
        target_labels = [target[0] for target in parsed_targets]
        target_cns = [target[1] for target in parsed_targets]
    else:
        target_labels = [item.strip() for item in args.target.split(",") if item.strip()]
        target_cns = (
            [item.strip() for item in args.target_cn.split(",") if item.strip()]
            if args.target_cn
            else target_labels
        )
        if len(target_cns) < len(target_labels):
            target_cns.extend(target_labels[len(target_cns) :])

    task = DetectionTask(
        args.model,
        target_labels,
        target_cns,
        voice,
        show_window=args.show_window,
    )
    task.start()
    try:
        while task.thread and task.thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        task.stop()
    finally:
        voice.speak(f"结束工作。共计发现并移除{task.trigger_count}个缺陷品。")
        voice.wait_until_done(timeout=5)
        voice.release()


def main():
    parser = argparse.ArgumentParser(description="PicoClaw voice-driven defect detector")
    parser.add_argument("--model", type=str, default="", help="Direct mode RKNN model path")
    parser.add_argument("--target", type=str, default="", help="Direct mode target label")
    parser.add_argument("--target-cn", type=str, default="", help="Direct mode Chinese target name")
    parser.add_argument(
        "--show-window",
        action="store_true",
        default=env_flag("PICOCLAW_SHOW_WINDOW", True),
        help="Show OpenCV preview window",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Start voice listener mode. This is the default when --model is omitted.",
    )
    args = parser.parse_args()

    if args.model and args.target:
        model_path = args.model
        if not os.path.isabs(model_path):
            model_path = os.path.join(MODEL_DIR, model_path)
        args.model = model_path
        run_direct_mode(args)
        return

    orchestrator = PicoClawOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
