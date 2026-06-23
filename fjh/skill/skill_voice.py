# -*- coding: utf-8 -*-
import argparse
from collections import OrderedDict
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import wave

import numpy as np
import sherpa_onnx
import sounddevice as sd

try:
    import resampy
except ImportError:
    resampy = None


ASR_MODEL_DIR = "/home/elf/text/yuyin/sensevoice/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09"
ASR_SILERO_VAD_MODEL = os.path.join(ASR_MODEL_DIR, "silero_vad.onnx")
TTS_MODEL_DIR = "/home/elf/text/yuyin/matcha_tts/matcha-icefall-zh-baker"
TTS_ACOUSTIC_MODEL = "/home/elf/text/yuyin/matcha_tts/matcha-icefall-zh-baker/model-steps-3.onnx"
TTS_VOCODER = "/home/elf/text/yuyin/matcha_tts/matcha-icefall-zh-baker/hifigan_v2.onnx"
TTS_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "tts")
TTS_ASSET_PROMPTS = {
    "prompt_wake": "请使用语音唤醒小智。",
    "prompt_program": "我在。请问需要执行什么程序？",
    "prompt_enter_box": "已进入飞机盒缺陷检测。",
    "prompt_enter_box_model": "已进入飞机盒缺陷检测。请告诉我使用什么模型，例如一。",
    "prompt_box_opened": "已打开飞机盒程序。",
    "prompt_detect_command": "我在。请说检测指令。",
    "prompt_start_model": "已开启检测任务。请告诉我使用什么模型，例如一。",
    "prompt_model": "请告诉我使用什么模型，例如一。",
    "prompt_target": "请告诉我需要检测的缺陷目标标签：1污渍，2划痕，3缺角。",
    "prompt_add_target": "请问是否还需要添加需要检测的缺陷目标标签？",
    "prompt_after_stop": "我在。请问是要更换参数还是退出程序？",
    "ok": "好的。",
    "exit_program": "已退出程序。",
    "exit_box_wake": "已退出飞机盒程序。请使用语音唤醒小智。",
    "exit_realtime": "已退出实时语音监听。",
    "detect_init": "检测任务正在后台初始化，请稍候。",
    "no_program": "暂时没有匹配到可执行程序。请说飞机盒缺陷检测。",
    "item_removed": "缺陷品已移除。",
    "model_load_failed": "模型加载失败，请检查模型路径。",
    "camera_open_failed": "相机打开失败，请检查相机设备。",
    "serial_connect_failed": "串口连接失败，请检查机械臂连接。",
    "system_loading": "系统启动中，正在加载模型与硬件。",
    "target_no_arm_command": "目标标签没有配置机械臂指令，任务已停止。",
    "detect_error": "检测任务发生异常，任务已停止。",
    "no_target_label": "当前没有这个检测标签。",
    "param_updated": "参数已更换完毕，继续检测任务。",
}
OUTPUT_SAMPLE_RATE_CANDIDATES = (16000, 48000, 44100, 32000, 22050)
INPUT_SAMPLE_RATE_CANDIDATES = (48000, 44100, 32000, 16000)
BOARD_AUDIO_CARD_NAMES = ("rockchipnau8822", "nau8822")
BOARD_AUDIO_CARD_INDEX_HINTS = ("card1", "card 1", "hw:1", "plughw:1")
ASR_FILLER_TEXTS = {
    "嗯",
    "嗯嗯",
    "啊",
    "啊啊",
    "呃",
    "呃呃",
    "哦",
    "噢",
    "哎",
    "唉",
    "喂",
}
ASR_SHORT_COMMAND_TEXTS = {
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
}
ASR_ECHO_PATTERNS = (
    "请使用语音唤醒小智",
    "请问需要执行什么程序",
    "已进入飞机盒缺陷检测",
    "请告诉我使用什么模型",
    "请告诉我需要检测的缺陷目标标签",
    "请问是否还需要添加",
    "相机已打开机械臂已连接",
    "系统启动中正在加载模型与硬件",
    "缺陷品已移除",
)
ASR_TEXT_REPLACEMENTS = {
    "小志": "小智",
    "晓智": "小智",
    "小字": "小智",
    "字小字": "小智小智",
    "飞机和": "飞机盒",
    "飞机合": "飞机盒",
    "飞机核": "飞机盒",
    "飞机河": "飞机盒",
    "飞机禾": "飞机盒",
    "飞机荷": "飞机盒",
    "飞鸡盒": "飞机盒",
    "飞鸡河": "飞机盒",
    "飞几盒": "飞机盒",
    "飞几河": "飞机盒",
    "飞行盒": "飞机盒",
    "警测": "检测",
    "检侧": "检测",
    "检厕": "检测",
    "坚测": "检测",
    "减测": "检测",
    "侦测": "检测",
    "污迹": "污渍",
    "污质": "污渍",
    "污子": "污渍",
    "屋子": "污渍",
    "乌字": "污渍",
    "乌渍": "污渍",
    "乌滋": "污渍",
    "吴字": "污渍",
    "无字": "污渍",
    "污滋": "污渍",
    "胡字": "污渍",
    "湖字": "污渍",
    "糊字": "污渍",
    "呼字": "污渍",
    "护字": "污渍",
    "胡渍": "污渍",
    "湖渍": "污渍",
    "糊渍": "污渍",
    "物资": "污渍",
    "无渍": "污渍",
    "五子": "污渍",
    "误资": "污渍",
    "脏污": "污渍",
    "划很": "划痕",
    "画很": "划痕",
    "画痕": "划痕",
    "话痕": "划痕",
    "华痕": "划痕",
    "花痕": "划痕",
    "刮痕": "划痕",
    "缺脚": "缺角",
    "缺觉": "缺角",
    "却角": "缺角",
    "雀角": "缺角",
    "缺叫": "缺角",
    "却叫": "缺角",
    "磨型": "模型",
    "磨形": "模型",
    "魔型": "模型",
    "摸型": "模型",
    "却认": "确认",
    "确任": "确认",
    "雀认": "确认",
    "雀任": "确认",
    "跟换": "更换",
    "根换": "更换",
    "更环": "更换",
    "天加": "添加",
    "添家": "添加",
    "推出来": "退出",
    "腿出来": "退出",
    "推出": "退出",
    "腿出": "退出",
    "衣污渍": "一污渍",
    "依污渍": "一污渍",
    "壹污渍": "一污渍",
    "幺污渍": "一污渍",
    "一胡字": "一污渍",
    "一湖字": "一污渍",
    "一糊字": "一污渍",
    "一呼字": "一污渍",
    "一乌字": "一污渍",
    "一乌渍": "一污渍",
    "一乌滋": "一污渍",
    "衣胡字": "一污渍",
    "依胡字": "一污渍",
    "幺胡字": "一污渍",
    "衣乌字": "一污渍",
    "依乌字": "一污渍",
    "幺乌字": "一污渍",
    "贰划痕": "二划痕",
    "儿划痕": "二划痕",
    "而划痕": "二划痕",
    "叁缺角": "三缺角",
    "山缺角": "三缺角",
}


def _device_name(dev):
    return str(dev.get("name", "")).strip()


def _device_has_channels(dev, is_input):
    key = "max_input_channels" if is_input else "max_output_channels"
    return int(dev.get(key, 0) or 0) > 0


def _env_device_index(devices, is_input):
    env_name = "PICOCLAW_INPUT_DEVICE" if is_input else "PICOCLAW_OUTPUT_DEVICE"
    env_device = os.getenv(env_name, "").strip()
    if not env_device:
        return None
    try:
        idx = int(env_device)
        if idx < 0 or idx >= len(devices):
            raise IndexError(f"device index {idx} out of range")
        if _device_has_channels(devices[idx], is_input):
            return idx
        direction = "input" if is_input else "output"
        print(f"[HW WARNING] {env_name}={idx} has no {direction} channels.")
    except Exception as exc:
        prefix = "ASR" if is_input else "TTS"
        print(f"[{prefix} HW WARNING] Invalid {env_name}={env_device}: {exc}")
    return None


def _preferred_audio_names(is_input):
    specific = os.getenv(
        "PICOCLAW_INPUT_CARD_NAME" if is_input else "PICOCLAW_OUTPUT_CARD_NAME",
        "",
    ).strip()
    common = os.getenv("PICOCLAW_AUDIO_CARD_NAME", "").strip()
    names = []
    for name in (specific, common, *BOARD_AUDIO_CARD_NAMES):
        lowered = name.lower()
        if lowered and lowered not in names:
            names.append(lowered)
    return names


def _rank_audio_device(dev, is_input):
    if not _device_has_channels(dev, is_input):
        return None
    name = _device_name(dev).lower()
    preferred_names = _preferred_audio_names(is_input)
    for rank, preferred in enumerate(preferred_names):
        if preferred in name:
            return rank
    if any(hint in name for hint in BOARD_AUDIO_CARD_INDEX_HINTS):
        return len(preferred_names)
    return None


def find_nau8822_device(is_input=True):
    """Find the ELF2 RK3588 onboard nau8822 device for mic input or 3.5mm output."""
    try:
        devices = sd.query_devices()
        env_idx = _env_device_index(devices, is_input)
        if env_idx is not None:
            return env_idx

        ranked = []
        for idx, dev in enumerate(devices):
            rank = _rank_audio_device(dev, is_input)
            if rank is not None:
                ranked.append((rank, idx))
        if ranked:
            ranked.sort()
            return ranked[0][1]

        io_name = "input" if is_input else "output"
        print(
            f"[HW WARNING] rockchipnau8822 {io_name} device not found, "
            "using system default. You can set PICOCLAW_INPUT_DEVICE or "
            "PICOCLAW_OUTPUT_DEVICE to override."
        )
        return None
    except Exception as exc:
        print(f"[HW ERROR] Failed to query audio devices: {exc}")
        return None


def require_file(path, label):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def normalize_tts_text(text):
    stripped = (text or "").strip()
    if not stripped:
        return stripped

    replacements = {
        "PicoClaw": "皮克克劳",
        "picoclaw": "皮克克劳",
        "pico claw": "皮克克劳",
        ".rknn": "模型",
        "rknn": "模型",
        "RKNN": "模型",
        "START": "开始",
        "READY": "就绪",
        "FINISH": "完成",
    }
    for src, dst in replacements.items():
        stripped = stripped.replace(src, dst)

    has_cjk = re.search(r"[\u3400-\u9fff]", stripped) is not None
    has_ascii_word = re.search(r"[A-Za-z]", stripped) is not None
    if has_ascii_word and not has_cjk:
        print(
            "[TTS WARNING] The zh-baker Matcha model cannot speak English words. "
            "Using a Chinese test sentence instead."
        )
        return "你好，我已经准备好了。"

    return stripped


def resample_audio(samples, source_rate, target_rate):
    if source_rate == target_rate or len(samples) == 0:
        return samples

    duration = len(samples) / float(source_rate)
    target_length = max(1, int(duration * target_rate))
    old_indices = np.linspace(0, len(samples) - 1, len(samples))
    new_indices = np.linspace(0, len(samples) - 1, target_length)
    return np.interp(new_indices, old_indices, samples).astype(np.float32)


def resample_input_audio(samples, source_rate, target_rate):
    if source_rate != target_rate and resampy is not None and len(samples) > 0:
        return resampy.resample(samples, source_rate, target_rate).astype(np.float32)
    return resample_audio(samples, source_rate, target_rate)


def pick_output_settings(device, preferred_rate):
    rates = []
    if preferred_rate:
        rates.append(int(preferred_rate))
    rates.extend(rate for rate in OUTPUT_SAMPLE_RATE_CANDIDATES if rate not in rates)

    channel_candidates = (1, 2)
    try:
        if device is not None:
            dev_info = sd.query_devices(device)
            max_channels = int(dev_info.get("max_output_channels", 1))
            channel_candidates = tuple(ch for ch in channel_candidates if ch <= max_channels) or (1,)

        for rate in rates:
            for channels in channel_candidates:
                try:
                    sd.check_output_settings(device=device, samplerate=rate, channels=channels)
                    return rate, channels
                except Exception:
                    continue
    except Exception as exc:
        print(f"[TTS HW WARNING] Failed to probe output settings: {exc}")

    return 48000, 1


def pick_input_settings(device, preferred_rate):
    rates = []
    if preferred_rate:
        rates.append(int(preferred_rate))
    rates.extend(rate for rate in INPUT_SAMPLE_RATE_CANDIDATES if rate not in rates)

    try:
        max_channels = 1
        if device is not None:
            dev_info = sd.query_devices(device)
            max_channels = int(dev_info.get("max_input_channels", 1))
        channel_candidates = tuple(ch for ch in (2, 1) if ch <= max_channels) or (1,)

        for rate in rates:
            for channels in channel_candidates:
                try:
                    sd.check_input_settings(device=device, samplerate=rate, channels=channels)
                    return rate, channels
                except Exception:
                    continue
    except Exception as exc:
        print(f"[ASR HW WARNING] Failed to probe input settings: {exc}")

    return 48000, 1


def to_channels(samples, channels):
    if channels <= 1:
        return samples[:, 0] if samples.ndim == 2 else samples
    if samples.ndim == 1:
        return np.column_stack([samples] * channels)
    if samples.shape[1] == channels:
        return samples
    return np.column_stack([samples[:, 0]] * channels)


def write_wav(path, samples, sample_rate):
    mono = samples[:, 0] if samples.ndim == 2 else samples
    pcm = np.clip(mono, -0.99, 0.99)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def read_wav(path):
    with wave.open(path, "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sample_width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported wav sample width: {sample_width}")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32), sample_rate


def pick_input_channel(indata, mode="mean"):
    if indata.ndim == 1:
        return indata.astype(np.float32)

    if mode == "mean":
        return indata.mean(axis=1).astype(np.float32)

    if mode.isdigit():
        channel_index = min(max(int(mode), 0), indata.shape[1] - 1)
        return indata[:, channel_index].astype(np.float32)

    best_index = 0
    best_rms = -1.0
    for channel_index in range(indata.shape[1]):
        channel = indata[:, channel_index].astype(np.float32)
        channel = channel - float(np.mean(channel))
        rms = float(np.sqrt(np.mean(np.square(channel)))) if channel.size else 0.0
        if rms > best_rms:
            best_index = channel_index
            best_rms = rms

    return indata[:, best_index].astype(np.float32)


def auto_level_audio(samples, fixed_gain, target_rms=0.045, max_gain=30.0):
    samples = samples - float(np.mean(samples))
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    if rms <= 1e-8:
        return samples.astype(np.float32), rms, 1.0

    if fixed_gain > 0:
        gain = fixed_gain
    else:
        gain = min(max_gain, target_rms / rms)

    samples = np.clip(samples * gain, -0.8, 0.8).astype(np.float32)
    return samples, rms, gain


def unpack_audio_item(item):
    if isinstance(item, tuple):
        return item
    rms = float(np.sqrt(np.mean(np.square(item)))) if item is not None and item.size else 0.0
    return item, rms, rms, 1.0


def merge_texts(texts):
    merged = []
    for text in texts:
        text = (text or "").strip()
        if not text:
            continue
        if merged and merged[-1] == text:
            continue
        merged.append(text)
    return " ".join(merged).strip()


def clean_asr_text(text):
    return re.sub(r"[\s,，.。!！?？、:：;；'\"]+", "", (text or "").strip())


def postprocess_asr_text(text):
    processed = (text or "").strip()
    for src, dst in ASR_TEXT_REPLACEMENTS.items():
        processed = processed.replace(src, dst)
    repeat_phrases = (
        "一污渍",
        "1污渍",
        "二划痕",
        "2划痕",
        "三缺角",
        "3缺角",
        "污渍",
        "划痕",
        "缺角",
        "小智",
        "飞机盒",
        "退出",
    )
    for phrase in repeat_phrases:
        while phrase + phrase in processed:
            processed = processed.replace(phrase + phrase, phrase)
    return processed


def is_meaningful_asr_text(text):
    cleaned = clean_asr_text(text)
    if not cleaned:
        return False
    if cleaned in ASR_FILLER_TEXTS:
        return False
    if any(pattern in cleaned for pattern in ASR_ECHO_PATTERNS):
        return False
    if len(cleaned) <= 1 and cleaned not in ASR_SHORT_COMMAND_TEXTS:
        return False
    return True


class VoiceSkill:
    """Text-to-speech manager based on Matcha-TTS + HiFiGAN."""

    def __init__(
        self,
        model_dir=TTS_MODEL_DIR,
        acoustic_model=TTS_ACOUSTIC_MODEL,
        vocoder=TTS_VOCODER,
    ):
        self.tts_queue = queue.Queue()
        self.running = True
        self.is_playing = False
        self.last_playback_ended_at = 0.0
        self.last_speak_text = ""
        self.last_speak_at = 0.0
        self.cache_enabled = os.getenv("PICOCLAW_TTS_CACHE", "1") != "0"
        self.cache_max_items = max(0, int(os.getenv("PICOCLAW_TTS_CACHE_ITEMS", "32")))
        self.tts_cache = OrderedDict()
        self.asset_enabled = os.getenv("PICOCLAW_TTS_ASSETS", "1") != "0"
        self.asset_dir = os.getenv("PICOCLAW_TTS_ASSET_DIR", TTS_ASSET_DIR)
        self.tts_asset_map = self._build_tts_asset_map()
        self.model_dir = model_dir
        self.acoustic_model = acoustic_model
        self.vocoder = vocoder
        self.tts = None
        self.tts_lock = threading.Lock()
        self.lazy_model = os.getenv("PICOCLAW_TTS_LAZY", "1") != "0"

        self.output_device = find_nau8822_device(is_input=False)
        self.output_sample_rate = 48000
        self.output_channels = 1

        preferred_output_sr = os.getenv("PICOCLAW_OUTPUT_SAMPLE_RATE", "").strip()
        hw_sr = int(preferred_output_sr) if preferred_output_sr else 48000

        self.output_sample_rate, self.output_channels = pick_output_settings(
            self.output_device, hw_sr
        )
        print(
            "[TTS HW] Bound output device, "
            f"device={self.output_device}, "
            f"sample rate: {self.output_sample_rate}Hz, channels: {self.output_channels}"
        )

        if self.lazy_model:
            print("[TTS INFO] Matcha-TTS model will load on first non-asset speech.")
        else:
            self._load_tts_engine()

        self.worker_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.worker_thread.start()

    def _load_tts_engine(self):
        if self.tts is not None:
            return

        with self.tts_lock:
            if self.tts is not None:
                return

            print("[TTS INFO] Loading Matcha-TTS model...")
            start_time = time.time()

            require_file(self.acoustic_model, "Matcha acoustic model")
            require_file(self.vocoder, "HiFiGAN vocoder")

            matcha_config = sherpa_onnx.OfflineTtsMatchaModelConfig(
                acoustic_model=self.acoustic_model,
                vocoder=self.vocoder,
                lexicon=os.path.join(self.model_dir, "lexicon.txt"),
                tokens=os.path.join(self.model_dir, "tokens.txt"),
                data_dir=os.path.join(self.model_dir, "espeak-ng-data"),
                dict_dir=os.path.join(self.model_dir, "dict"),
            )

            model_config = sherpa_onnx.OfflineTtsModelConfig(
                matcha=matcha_config,
                num_threads=int(os.getenv("PICOCLAW_TTS_THREADS", "4")),
                debug=False,
                provider="cpu",
            )

            rule_fsts = [
                os.path.join(self.model_dir, "phone.fst"),
                os.path.join(self.model_dir, "date.fst"),
                os.path.join(self.model_dir, "number.fst"),
            ]
            existing_fsts = [path for path in rule_fsts if os.path.exists(path)]

            config = sherpa_onnx.OfflineTtsConfig(
                model=model_config,
                rule_fsts=",".join(existing_fsts),
                max_num_sentences=1,
            )

            self.tts = sherpa_onnx.OfflineTts(config)
            print(f"[TTS INFO] TTS engine loaded in {time.time() - start_time:.2f}s.")

    def _build_tts_asset_map(self):
        if not self.asset_enabled:
            return {}

        asset_map = {}
        for name, prompt in TTS_ASSET_PROMPTS.items():
            path = os.path.join(self.asset_dir, f"{name}.wav")
            if not os.path.exists(path):
                continue
            normalized = normalize_tts_text(prompt)
            if normalized in asset_map:
                print(f"[TTS ASSET WARNING] Duplicate prompt mapping ignored: {name}")
                continue
            asset_map[normalized] = path

        if asset_map:
            print(f"[TTS ASSET INFO] Loaded {len(asset_map)} preset wav prompt(s) from {self.asset_dir}")
        else:
            print(f"[TTS ASSET INFO] No preset wav prompts found in {self.asset_dir}")
        return asset_map

    def _tts_worker(self):
        while self.running:
            try:
                text = self.tts_queue.get(timeout=0.5)
                text = normalize_tts_text(text)
                if text:
                    print(f"\n[TTS PLAY]: {text}")
                    self._play_tts(text)
                self.tts_queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                print(f"[TTS ERROR] Worker failed: {exc}")

    def _play_tts(self, text):
        try:
            self.is_playing = True
            samples, source_rate = self._get_tts_audio(text)
            if len(samples) == 0:
                print("[TTS WARNING] Generated empty audio.")
                return

            samples = np.clip(samples, -0.99, 0.99)
            if self._play_with_sounddevice(samples, source_rate):
                return
            if self._play_with_aplay(samples, source_rate):
                return
            print("[TTS ERROR] Playback failed with both sounddevice and aplay.")
        except Exception as exc:
            print(f"[TTS ERROR] Playback failed: {exc}")
        finally:
            self.is_playing = False
            self.last_playback_ended_at = time.time()

    def _get_tts_audio(self, text):
        if self.cache_enabled and text in self.tts_cache:
            samples, sample_rate = self.tts_cache.pop(text)
            self.tts_cache[text] = (samples, sample_rate)
            return samples, sample_rate

        asset_path = self.tts_asset_map.get(text)
        if asset_path:
            try:
                samples, sample_rate = read_wav(asset_path)
                print(f"[TTS ASSET PLAY]: {os.path.basename(asset_path)}")
                if self.cache_enabled and self.cache_max_items > 0:
                    self.tts_cache[text] = (samples.copy(), sample_rate)
                    while len(self.tts_cache) > self.cache_max_items:
                        self.tts_cache.popitem(last=False)
                return samples, sample_rate
            except Exception as exc:
                print(f"[TTS ASSET WARNING] Failed to read {asset_path}: {exc}")

        self._load_tts_engine()
        audio = self.tts.generate(text, sid=0, speed=1.0)
        samples = np.asarray(audio.samples, dtype=np.float32)
        sample_rate = audio.sample_rate if audio.sample_rate else self.output_sample_rate

        if self.cache_enabled and self.cache_max_items > 0 and len(samples) > 0:
            self.tts_cache[text] = (samples.copy(), sample_rate)
            while len(self.tts_cache) > self.cache_max_items:
                self.tts_cache.popitem(last=False)

        return samples, sample_rate

    def _play_with_sounddevice(self, source_samples, source_rate):
        rates = [self.output_sample_rate]
        rates.extend(rate for rate in OUTPUT_SAMPLE_RATE_CANDIDATES if rate not in rates)
        devices = [self.output_device]
        if self.output_device is not None:
            devices.append(None)

        last_error = None
        for device in devices:
            for rate in rates:
                samples = resample_audio(source_samples, source_rate, rate)
                for channels in (self.output_channels, 1, 2):
                    try:
                        out = to_channels(samples, channels).astype(np.float32)
                        sd.play(out, samplerate=rate, device=device, blocking=True)
                        self.output_device = device
                        self.output_sample_rate = rate
                        self.output_channels = channels
                        print(
                            "[TTS HW] Playback OK with sounddevice, "
                            f"device={device}, rate={rate}, channels={channels}"
                        )
                        return True
                    except Exception as exc:
                        last_error = exc
                        try:
                            sd.stop()
                        except Exception:
                            pass

        if last_error:
            print(f"[TTS HW WARNING] sounddevice playback failed: {last_error}")
        return False

    def _play_with_aplay(self, source_samples, source_rate):
        rates = [self.output_sample_rate]
        rates.extend(rate for rate in OUTPUT_SAMPLE_RATE_CANDIDATES if rate not in rates)
        last_error = None

        for rate in rates:
            samples = resample_audio(source_samples, source_rate, rate)
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_path = tmp_file.name
                write_wav(tmp_path, samples, rate)
                subprocess.run(
                    ["aplay", "-q", tmp_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.output_sample_rate = rate
                print(f"[TTS HW] Playback OK with aplay, rate={rate}")
                return True
            except Exception as exc:
                last_error = exc
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        if last_error:
            print(f"[TTS HW WARNING] aplay playback failed: {last_error}")
        return False

    def speak(self, text):
        normalized = normalize_tts_text(text)
        now = time.time()
        if normalized and normalized == self.last_speak_text and now - self.last_speak_at < 2.0:
            print(f"[TTS INFO] Suppressed repeated speech: {normalized}")
            return
        self.last_speak_text = normalized
        self.last_speak_at = now
        self.tts_queue.put(text)

    def clear_pending(self):
        cleared = 0
        while True:
            try:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            print(f"[TTS INFO] Cleared {cleared} pending speech item(s).")

    def wait_until_done(self, timeout=None):
        started_at = time.time()
        while self.is_playing or self.tts_queue.unfinished_tasks > 0:
            if timeout is not None and time.time() - started_at > timeout:
                return False
            time.sleep(0.05)
        return True

    def release(self):
        self.running = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)


class VoiceListener:
    """Speech-to-text manager based on the SenseVoice offline model."""

    def __init__(self, model_dir=ASR_MODEL_DIR, speaker: VoiceSkill = None):
        self.model_dir = model_dir
        self.speaker = speaker
        self.running = False
        self.target_sample_rate = 16000
        self.audio_queue = queue.Queue(
            maxsize=max(0, int(os.getenv("PICOCLAW_ASR_QUEUE_CHUNKS", "24")))
        )
        self.listen_thread = None
        self.on_text = None
        self.energy_threshold = float(os.getenv("PICOCLAW_ASR_ENERGY", "0.001"))
        self.raw_noise_floor = float(os.getenv("PICOCLAW_ASR_RAW_GATE", "0.0006"))
        self.input_gain = float(os.getenv("PICOCLAW_ASR_GAIN", "0"))
        self.auto_gain_target = float(os.getenv("PICOCLAW_ASR_TARGET_RMS", "0.045"))
        self.auto_gain_max = float(os.getenv("PICOCLAW_ASR_MAX_GAIN", "120.0"))
        self.input_channel_mode = os.getenv("PICOCLAW_INPUT_CHANNEL", "best").strip().lower()
        self.decode_window_seconds = float(os.getenv("PICOCLAW_ASR_WINDOW_SECONDS", "1.1"))
        self.max_phrase_seconds = float(os.getenv("PICOCLAW_ASR_MAX_SECONDS", "4.5"))
        self.after_tts_ignore_seconds = float(os.getenv("PICOCLAW_ASR_AFTER_TTS_IGNORE", "1.2"))
        self.debug_asr = os.getenv("PICOCLAW_ASR_DEBUG", "0") == "1"
        self.use_vad = os.getenv("PICOCLAW_ASR_USE_VAD", "1") != "0"
        self.vad_fallback = os.getenv("PICOCLAW_ASR_VAD_FALLBACK", "0") == "1"
        self.input_block_seconds = float(os.getenv("PICOCLAW_ASR_BLOCK_SECONDS", "0.05"))
        self.last_queue_drop_log_at = 0.0
        self.last_accepted_text = ""
        self.last_accepted_at = 0.0
        self.last_raw_text = ""
        self.last_raw_at = 0.0
        self.vad = None

        self.input_device = find_nau8822_device(is_input=True)
        self.hardware_sample_rate = 16000
        self.hardware_channels = 1

        if self.input_device is not None:
            dev_info = sd.query_devices(self.input_device)
            preferred_sr = os.getenv("PICOCLAW_INPUT_SAMPLE_RATE", "").strip()
            if preferred_sr:
                hw_sr = int(preferred_sr)
            else:
                hw_sr = 48000
            self.hardware_sample_rate, self.hardware_channels = pick_input_settings(
                self.input_device,
                hw_sr,
            )

        print(
            "[ASR HW] Bound input device, "
            f"device={self.input_device}, "
            f"sample rate: {self.hardware_sample_rate}Hz, channels: {self.hardware_channels}"
        )

        model_path = require_file(os.path.join(model_dir, "model.int8.onnx"), "SenseVoice model")
        tokens_path = require_file(os.path.join(model_dir, "tokens.txt"), "SenseVoice tokens")

        print("[ASR INFO] Loading SenseVoice recognizer...")
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_path,
            tokens=tokens_path,
            num_threads=int(os.getenv("PICOCLAW_ASR_THREADS", "4")),
            use_itn=os.getenv("PICOCLAW_ASR_ITN", "1") == "1",
            debug=False,
            provider="cpu",
        )
        self._init_vad()
        print("[ASR INFO] Speech recognizer is ready.")
        print(
            "[ASR INFO] Listening settings: "
            f"energy_hint={self.energy_threshold}, raw_gate={self.raw_noise_floor}, "
            f"gain={self.input_gain or 'auto'}, "
            f"target_rms={self.auto_gain_target}, channel={self.input_channel_mode}, "
            f"window={self.decode_window_seconds}s, max={self.max_phrase_seconds}s, "
            f"block={self.input_block_seconds}s, queue={self.audio_queue.maxsize or 'unbounded'}, "
            f"vad={'on' if self.vad else 'off'}, fallback={'on' if self.vad_fallback else 'off'}"
        )

    def _init_vad(self):
        if not self.use_vad:
            return
        if not os.path.exists(ASR_SILERO_VAD_MODEL):
            print(f"[ASR INFO] VAD model not found, fallback to window decode: {ASR_SILERO_VAD_MODEL}")
            return
        try:
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = ASR_SILERO_VAD_MODEL
            config.silero_vad.threshold = float(os.getenv("PICOCLAW_VAD_THRESHOLD", "0.55"))
            config.silero_vad.min_silence_duration = float(
                os.getenv("PICOCLAW_VAD_MIN_SILENCE", "0.08")
            )
            config.silero_vad.min_speech_duration = float(
                os.getenv("PICOCLAW_VAD_MIN_SPEECH", "0.16")
            )
            config.silero_vad.max_speech_duration = float(
                os.getenv("PICOCLAW_VAD_MAX_SPEECH", "8.0")
            )
            config.sample_rate = self.target_sample_rate
            self.vad = sherpa_onnx.VoiceActivityDetector(
                config,
                buffer_size_in_seconds=int(os.getenv("PICOCLAW_VAD_BUFFER_SECONDS", "100")),
            )
            print("[ASR INFO] Silero VAD enabled.")
        except Exception as exc:
            self.vad = None
            print(f"[ASR WARNING] Failed to enable Silero VAD, fallback to window decode: {exc}")

    def _reset_vad(self):
        if not self.vad:
            return
        try:
            if hasattr(self.vad, "reset"):
                self.vad.reset()
            else:
                self._init_vad()
        except Exception:
            self._init_vad()

    def _queue_audio_item(self, item):
        try:
            self.audio_queue.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            self.audio_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.audio_queue.put_nowait(item)
        except queue.Full:
            return

        now = time.time()
        if self.debug_asr and now - self.last_queue_drop_log_at >= 1.0:
            print("[ASR WARNING] audio queue full, dropped stale chunk")
            self.last_queue_drop_log_at = now

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[ASR HW WARNING] Audio status: {status}")

        if self.speaker and self.speaker.is_playing:
            return
        if (
            self.speaker
            and time.time() - getattr(self.speaker, "last_playback_ended_at", 0.0)
            < self.after_tts_ignore_seconds
        ):
            return

        samples = pick_input_channel(indata, self.input_channel_mode)
        samples, raw_rms, applied_gain = auto_level_audio(
            samples,
            self.input_gain,
            target_rms=self.auto_gain_target,
            max_gain=self.auto_gain_max,
        )
        if raw_rms < self.raw_noise_floor:
            if self.debug_asr:
                self._queue_audio_item((np.array([], dtype=np.float32), raw_rms, 0.0, applied_gain))
            return

        processed_rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        if self.debug_asr:
            self._queue_audio_item((samples, raw_rms, processed_rms, applied_gain))
            return

        self._queue_audio_item((samples, raw_rms, processed_rms, applied_gain))

    def _unpack_audio_item(self, item):
        samples, raw_rms, proc_rms, gain = unpack_audio_item(item)
        if samples.size and self.hardware_sample_rate != self.target_sample_rate:
            samples = resample_input_audio(
                samples,
                self.hardware_sample_rate,
                self.target_sample_rate,
            )
        return samples, raw_rms, proc_rms, gain

    def _accept_decoded_text(self, text):
        raw_text = (text or "").strip()
        now = time.time()
        if raw_text and raw_text == self.last_raw_text and now - self.last_raw_at < 1.2:
            return False
        self.last_raw_text = raw_text
        self.last_raw_at = now

        text = postprocess_asr_text(text)
        if is_meaningful_asr_text(text):
            cleaned = clean_asr_text(text)
            last_cleaned = clean_asr_text(self.last_accepted_text)
            if text == self.last_accepted_text and now - self.last_accepted_at < 1.8:
                return False
            if (
                len(cleaned) >= 2
                and len(last_cleaned) >= 2
                and now - self.last_accepted_at < 1.8
                and (cleaned in last_cleaned or last_cleaned in cleaned)
            ):
                return False
            self.last_accepted_text = text
            self.last_accepted_at = now
            print(f"\n[ASR TEXT]: {text}")
            if self.on_text:
                self.on_text(text)
            return True

        if text:
            if self.debug_asr:
                print(f"\n[ASR IGNORE]: {text}")
        return False

    def start_listen(self, on_text=None):
        if self.running:
            return
        self.on_text = on_text
        self._clear_audio_queue()
        self.running = True
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()

    def _decode_samples(self, samples):
        if samples.size == 0:
            return ""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.target_sample_rate, samples)
        if hasattr(stream, "input_finished"):
            stream.input_finished()
        self.recognizer.decode_stream(stream)
        result = self._get_stream_result(stream)
        return result.text.strip() if hasattr(result, "text") else str(result).strip()

    def _get_stream_result(self, stream):
        if hasattr(self.recognizer, "get_result"):
            return self.recognizer.get_result(stream)
        result = getattr(stream, "result", None)
        if result is not None:
            return result
        if hasattr(stream, "get_result"):
            return stream.get_result()
        return ""

    def _listen_loop(self):
        if self.vad:
            self._listen_loop_with_vad()
            return

        print("\n[ASR INFO] Listening. Press Ctrl+C to stop.")
        buffer = np.array([], dtype=np.float32)
        last_level_log = time.time()
        peak_raw_rms = 0.0
        peak_proc_rms = 0.0
        last_gain = 1.0

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while self.running:
                    chunk = None
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        pass

                    now = time.time()
                    if chunk is not None:
                        chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                        peak_raw_rms = max(peak_raw_rms, raw_rms)
                        peak_proc_rms = max(peak_proc_rms, proc_rms)
                        last_gain = gain
                        buffer = np.concatenate((buffer, chunk))

                        max_samples = int(self.target_sample_rate * self.max_phrase_seconds)
                        if len(buffer) > max_samples:
                            buffer = buffer[-max_samples:]

                    if self.debug_asr and now - last_level_log >= 1.0:
                        print(
                            "[ASR LEVEL] "
                            f"raw={peak_raw_rms:.6f}, proc={peak_proc_rms:.5f}, gain={last_gain:.1f}"
                        )
                        last_level_log = now

                    decode_samples = int(self.target_sample_rate * self.decode_window_seconds)
                    if len(buffer) >= decode_samples:
                        if peak_proc_rms < self.energy_threshold and self.debug_asr:
                            print(f"[ASR IGNORE] low energy: {peak_proc_rms:.5f}")
                        current_text = self._decode_samples(buffer)
                        self._accept_decoded_text(current_text)
                        buffer = np.array([], dtype=np.float32)
                        peak_raw_rms = 0.0
                        peak_proc_rms = 0.0
                        last_gain = 1.0

                    time.sleep(0.02)
        except Exception as exc:
            print(f"\n[ASR RUNTIME ERROR] Failed to open microphone stream: {exc}")

    def _listen_loop_with_vad(self):
        print("\n[ASR INFO] Listening with Silero VAD. Press Ctrl+C to stop.")
        self._reset_vad()
        buffer = np.array([], dtype=np.float32)
        offset = 0
        last_level_log = time.time()
        peak_raw_rms = 0.0
        peak_proc_rms = 0.0
        last_gain = 1.0
        last_vad_decode_at = time.time()
        vad_frame_size = 160

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while self.running:
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        chunk = None

                    now = time.time()
                    if chunk is not None:
                        chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                        peak_raw_rms = max(peak_raw_rms, raw_rms)
                        peak_proc_rms = max(peak_proc_rms, proc_rms)
                        last_gain = gain
                        buffer = np.concatenate((buffer, chunk))

                    while offset + vad_frame_size <= len(buffer):
                        self.vad.accept_waveform(buffer[offset : offset + vad_frame_size])
                        offset += vad_frame_size

                    while not self.vad.empty():
                        segment = np.copy(self.vad.front.samples)
                        self.vad.pop()
                        text = self._decode_samples(segment)
                        self._accept_decoded_text(text)
                        last_vad_decode_at = now

                    if offset > self.target_sample_rate * 5:
                        buffer = buffer[offset:]
                        offset = 0

                    if self.debug_asr and now - last_level_log >= 1.0:
                        print(
                            "[ASR LEVEL] "
                            f"raw={peak_raw_rms:.6f}, proc={peak_proc_rms:.5f}, gain={last_gain:.1f}"
                        )
                        last_level_log = now

                    fallback_samples = int(self.target_sample_rate * self.decode_window_seconds)
                    fallback_due = (
                        self.vad_fallback
                        and
                        len(buffer) >= fallback_samples
                        and peak_proc_rms >= self.energy_threshold
                        and now - last_vad_decode_at >= self.decode_window_seconds
                    )
                    if fallback_due:
                        recent = buffer[-fallback_samples:]
                        text = self._decode_samples(recent)
                        accepted = self._accept_decoded_text(text)
                        if accepted:
                            last_vad_decode_at = now
                        buffer = np.array([], dtype=np.float32)
                        offset = 0

                    time.sleep(0.01)
        except Exception as exc:
            print(f"\n[ASR RUNTIME ERROR] Failed to open VAD microphone stream: {exc}")

    def stop_listen(self):
        self.running = False
        if (
            self.listen_thread
            and self.listen_thread.is_alive()
            and threading.current_thread() is not self.listen_thread
        ):
            self.listen_thread.join(timeout=2.0)
        self.listen_thread = None

    def _clear_audio_queue(self):
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def listen_once(self, timeout=8, phrase_seconds=3.0):
        if self.vad:
            return self._listen_once_with_vad(timeout=timeout)

        if self.running:
            self.stop_listen()

        self._clear_audio_queue()
        buffer = np.array([], dtype=np.float32)
        started_at = time.time()

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while time.time() - started_at < timeout:
                    chunk = None
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        pass

                    now = time.time()
                    if chunk is not None:
                        chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                        buffer = np.concatenate((buffer, chunk))

                    max_samples = int(self.target_sample_rate * phrase_seconds)
                    if len(buffer) >= max_samples:
                        text = postprocess_asr_text(self._decode_samples(buffer))
                        if is_meaningful_asr_text(text):
                            return text
                        if text and self.debug_asr:
                            print(f"[ASR IGNORE]: {text}")
                        buffer = np.array([], dtype=np.float32)
        except Exception as exc:
            print(f"[ASR RUNTIME ERROR] Failed to listen once: {exc}")

        if buffer.size >= int(self.target_sample_rate * 0.5):
            text = postprocess_asr_text(self._decode_samples(buffer))
            return text if is_meaningful_asr_text(text) else ""
        return ""

    def listen_for_duration(self, duration=5.0):
        if self.vad:
            return self._listen_for_duration_with_vad(duration=duration)

        if self.running:
            self.stop_listen()

        old_ignore_seconds = self.after_tts_ignore_seconds
        self.after_tts_ignore_seconds = 0.0
        self._clear_audio_queue()
        buffer = np.array([], dtype=np.float32)
        started_at = time.time()

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while time.time() - started_at < duration:
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                    buffer = np.concatenate((buffer, chunk))
        except Exception as exc:
            print(f"[ASR RUNTIME ERROR] Failed fixed-duration recording: {exc}")
        finally:
            self.after_tts_ignore_seconds = old_ignore_seconds

        if buffer.size < int(self.target_sample_rate * 0.3):
            return ""
        text = postprocess_asr_text(self._decode_samples(buffer))
        return text if is_meaningful_asr_text(text) else ""

    def _listen_once_with_vad(self, timeout=8):
        if self.running:
            self.stop_listen()

        self._reset_vad()
        self._clear_audio_queue()
        buffer = np.array([], dtype=np.float32)
        offset = 0
        started_at = time.time()
        vad_frame_size = 160

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while time.time() - started_at < timeout:
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        chunk = None

                    if chunk is not None:
                        chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                        buffer = np.concatenate((buffer, chunk))

                    while offset + vad_frame_size <= len(buffer):
                        self.vad.accept_waveform(buffer[offset : offset + vad_frame_size])
                        offset += vad_frame_size

                    while not self.vad.empty():
                        segment = np.copy(self.vad.front.samples)
                        self.vad.pop()
                        text = postprocess_asr_text(self._decode_samples(segment))
                        if is_meaningful_asr_text(text):
                            return text
                        if text and self.debug_asr:
                            print(f"[ASR IGNORE]: {text}")

                    if offset > self.target_sample_rate * 5:
                        buffer = buffer[offset:]
                        offset = 0
        except Exception as exc:
            print(f"[ASR RUNTIME ERROR] Failed to listen once with VAD: {exc}")

        return ""

    def _listen_for_duration_with_vad(self, duration=5.0):
        if self.running:
            self.stop_listen()

        old_ignore_seconds = self.after_tts_ignore_seconds
        self.after_tts_ignore_seconds = 0.0
        self._reset_vad()
        self._clear_audio_queue()
        buffer = np.array([], dtype=np.float32)
        offset = 0
        started_at = time.time()
        vad_frame_size = 160
        recognized_texts = []

        try:
            with sd.InputStream(
                device=self.input_device,
                channels=self.hardware_channels,
                samplerate=self.hardware_sample_rate,
                dtype="float32",
                blocksize=max(1, int(self.input_block_seconds * self.hardware_sample_rate)),
                callback=self._audio_callback,
            ):
                while time.time() - started_at < duration:
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        chunk = None

                    if chunk is not None:
                        chunk, raw_rms, proc_rms, gain = self._unpack_audio_item(chunk)
                        buffer = np.concatenate((buffer, chunk))

                    while offset + vad_frame_size <= len(buffer):
                        self.vad.accept_waveform(buffer[offset : offset + vad_frame_size])
                        offset += vad_frame_size

                    while not self.vad.empty():
                        segment = np.copy(self.vad.front.samples)
                        self.vad.pop()
                        text = postprocess_asr_text(self._decode_samples(segment))
                        if is_meaningful_asr_text(text):
                            recognized_texts.append(text)
                        elif text and self.debug_asr:
                            print(f"[ASR IGNORE]: {text}")

                    if offset > self.target_sample_rate * 5:
                        buffer = buffer[offset:]
                        offset = 0
        except Exception as exc:
            print(f"[ASR RUNTIME ERROR] Failed fixed-duration VAD recording: {exc}")
        finally:
            self.after_tts_ignore_seconds = old_ignore_seconds

        while self.vad and not self.vad.empty():
            segment = np.copy(self.vad.front.samples)
            self.vad.pop()
            text = postprocess_asr_text(self._decode_samples(segment))
            if is_meaningful_asr_text(text):
                recognized_texts.append(text)

        if not recognized_texts and buffer.size >= int(self.target_sample_rate * 0.5):
            recent = buffer[-int(self.target_sample_rate * min(duration, self.decode_window_seconds)) :]
            text = postprocess_asr_text(self._decode_samples(recent))
            if is_meaningful_asr_text(text):
                recognized_texts.append(text)

        return merge_texts(recognized_texts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ELF2 RK3588 Voice Service Framework")
    parser.add_argument(
        "--mode",
        type=str,
        default="loop",
        choices=["tts", "asr", "loop"],
        help="Run mode: tts, asr, or loop",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="你好，我已经准备好了。",
        help="Text to speak in TTS mode",
    )
    args = parser.parse_args()

    print("=== Starting ELF2 voice interaction test ===")

    if args.mode == "tts":
        speaker = VoiceSkill()
        speaker.speak(args.text)
        speaker.wait_until_done()
        speaker.release()
    elif args.mode == "asr":
        listener = VoiceListener()
        listener.start_listen()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            listener.stop_listen()
    else:
        speaker = VoiceSkill()
        listener = VoiceListener(speaker=speaker)

        speaker.speak("语音交互服务已启动。")
        speaker.speak("请开始说话。")

        listener.start_listen()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            listener.stop_listen()
            speaker.release()

    print("\n=== Voice service stopped ===")
