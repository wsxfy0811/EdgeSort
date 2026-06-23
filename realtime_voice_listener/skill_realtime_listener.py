# -*- coding: utf-8 -*-
import importlib.util
import os
import queue
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


VENV_PYTHON = Path.home() / "text" / "ven" / "ai" / "bin" / "python3"
BOX_PROCESS_LOG = Path.home() / ".picoclaw" / "logs" / "box_defect_process.log"


def ensure_voice_env():
    """Use the voice venv Python even if PicoClaw directly launches this file."""
    if os.name != "posix":
        return
    if os.environ.get("PICOCLAW_VOICE_ENV_READY") == "1":
        return
    if not VENV_PYTHON.exists():
        print(f"[Realtime Listener WARNING] venv python not found: {VENV_PYTHON}")
        return
    if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        os.environ["PICOCLAW_VOICE_ENV_READY"] = "1"
        return

    os.environ["PICOCLAW_VOICE_ENV_READY"] = "1"
    print(f"[Realtime Listener] switching to voice venv: {VENV_PYTHON}")
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def workspace_dir():
    configured = os.getenv("PICOCLAW_WORKSPACE_DIR", "").strip()
    if configured:
        return Path(configured)

    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "workspace":
            return parent
    return current.parents[1]


def find_box_skill_dir():
    env_path = os.getenv("PICOCLAW_BOX_SKILL_DIR", "").strip()
    workspace = workspace_dir()
    candidates = [
        Path(env_path) if env_path else None,
        workspace / "skills" / "fjh" / "skill",
        workspace / "fjh" / "skill",
        Path("/home/elf/.picoclaw/workspace/fjh/skill"),
        Path("/home/elf/.picoclaw/workspace/skills/fjh/skill"),
        Path(__file__).resolve().parents[2] / "fjh" / "新运行逻辑",
    ]
    for path in candidates:
        if path and (path / "main.py").exists() and (path / "skill_voice.py").exists():
            return path
    checked = "\n".join(str(path) for path in candidates if path)
    raise FileNotFoundError(
        "未找到飞机盒检测 skill，请确认 main.py 和 skill_voice.py 位于以下任一路径：\n"
        f"{checked}"
    )


ensure_voice_env()

BOX_SKILL_DIR = find_box_skill_dir()
if str(BOX_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(BOX_SKILL_DIR))

from skill_voice import VoiceListener, VoiceSkill  # noqa: E402


WAKE_WORDS = ("小智", "小志", "晓智", "小字", "字小字", "picoclaw", "pico claw")
EXIT_WORDS = ("退出", "退出程序", "关闭程序", "结束程序", "stop")
QUIT_ALL_WORDS = ("退出实时语音程序", "关闭实时语音程序", "quit")
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
BOX_PROGRAM_WORDS = (
    "飞机盒",
    "飞机和",
    "飞机合",
    "飞机核",
    "飞机河",
    "飞机禾",
    "飞鸡盒",
    "飞鸡河",
    "飞几盒",
    "飞几河",
    "飞行盒",
    "飞机盒检测",
    "飞机盒缺陷",
    "缺陷检测",
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
}
SHORTCUT_TARGET_TEXT = {
    "1": "1污渍",
    "2": "2划痕",
    "3": "3缺角",
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


def is_valid_command_text(text):
    compact = re.sub(r"[\s,，.。!！?？、:：;；'\"]+", "", text or "")
    if not compact or compact in FILLER_TEXTS:
        return False
    return len(compact) > 1 or compact in SHORT_COMMAND_TEXTS


def has_any(text, words):
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


def compact_pinyin(text):
    return "".join(PINYIN_CHARS.get(ch, ch.lower()) for ch in re.sub(r"\s+", "", text or ""))


def shortcut_to_voice_text(command):
    text = normalize_text(command)
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    direct_map = {
        "wake": "小智",
        "box": "飞机盒",
        "ok": "确认",
        "yes": "确认",
        "no": "不需要",
        "change": "更换",
        "exit": "退出",
        "quit": "退出实时语音程序",
    }
    if compact in direct_map:
        return direct_map[compact]

    parts = compact.split()
    if len(parts) == 2:
        action, value = parts
        target_text = SHORTCUT_TARGET_TEXT.get(value)
        if action == "m":
            return value
        if action == "t" and target_text:
            return target_text
        if action == "add" and target_text:
            return target_text
        if action == "rm" and target_text:
            return f"移除{target_text}"

    return command


def load_box_skill_module():
    main_path = BOX_SKILL_DIR / "main.py"
    if not main_path.exists():
        raise FileNotFoundError(f"box defect skill main.py not found: {main_path}")

    module_name = "picoclaw_box_defect_skill_main"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(module_name, main_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class RealtimeVoiceListenerSkill:
    def __init__(self):
        self.voice = VoiceSkill()
        self._raw_speak = self.voice.speak
        self.voice.speak = self._speak
        self.listener = VoiceListener(speaker=self.voice)
        self.commands = queue.Queue()
        self.running = True
        self.state = "WAIT_WAKE"
        self.box_orchestrator = None
        self.box_terminal_started = False

    def log_box_process(self, message):
        try:
            BOX_PROCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with BOX_PROCESS_LOG.open("a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] {message}\n")
        except Exception as exc:
            print(f"[Realtime Listener WARNING] failed to write box process log: {exc}")

    def _speak(self, text):
        if self.state == "BOX_DEFECT":
            self.log_box_process(f"播报内容: {text}")
        self._raw_speak(text)

    def open_box_process_terminal(self):
        if self.box_terminal_started or os.name != "posix":
            return

        self.log_box_process("飞机盒程序日志窗口已打开。")
        command = (
            f"echo 'PicoClaw 飞机盒程序进程日志'; "
            f"echo '日志文件: {BOX_PROCESS_LOG}'; "
            f"echo '实时语音退出后此窗口会自动关闭。'; "
            f"tail --pid={os.getpid()} -n 80 -F {BOX_PROCESS_LOG}"
        )

        terminal_commands = []
        if shutil.which("gnome-terminal"):
            terminal_commands.append(["gnome-terminal", "--", "bash", "-lc", command])
        if shutil.which("x-terminal-emulator"):
            terminal_commands.append(["x-terminal-emulator", "-e", f"bash -lc {command!r}"])
        if shutil.which("xfce4-terminal"):
            terminal_commands.append(["xfce4-terminal", "--command", f"bash -lc {command!r}"])
        if shutil.which("konsole"):
            terminal_commands.append(["konsole", "-e", "bash", "-lc", command])

        for terminal_command in terminal_commands:
            try:
                subprocess.Popen(
                    terminal_command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self.box_terminal_started = True
                return
            except Exception as exc:
                print(f"[Realtime Listener WARNING] failed to open terminal: {exc}")

        print("[Realtime Listener WARNING] no terminal emulator found for box process log.")

    def _on_text(self, text):
        if not is_valid_command_text(text):
            return
        print(f"[Realtime Listener Command] {text}")
        if self.state == "BOX_DEFECT":
            self.log_box_process(f"识别文字: {text}")
        self.commands.put(text)

    def start_listener(self):
        if not self.listener.running:
            self.listener.start_listen(on_text=self._on_text)

    def stop_listener(self):
        self.listener.stop_listen()

    def prompt_wake(self):
        self.state = "WAIT_WAKE"
        self.voice.speak("请使用语音唤醒小智。")

    def prompt_program(self):
        self.state = "WAIT_PROGRAM"
        self.voice.speak("我在。请问需要执行什么程序？")

    def enter_box_defect_skill(self):
        module = load_box_skill_module()
        self.open_box_process_terminal()
        self.log_box_process(f"进入飞机盒程序，skill路径: {BOX_SKILL_DIR}")
        if self.box_orchestrator is None:
            self.box_orchestrator = module.PicoClawOrchestrator(
                model_dir=str(BOX_SKILL_DIR),
                voice=self.voice,
                listener=self.listener,
                release_resources=False,
            )
        self.state = "BOX_DEFECT"
        self.box_orchestrator.running = True
        self.box_orchestrator.prompt_detection_model()

    def exit_box_defect_skill(self):
        if self.box_orchestrator and self.box_orchestrator.active_task:
            self.log_box_process("正在退出飞机盒程序，停止检测任务。")
            task = self.box_orchestrator.active_task
            task.suppress_finished_speech = True
            task.set_sorting_enabled(False)
            self.voice.clear_pending()
            task.wait_until_arm_ready(timeout=20)
            task.stop()
            self.box_orchestrator.last_trigger_count = task.trigger_count
            self.box_orchestrator.speak_report(wait_for_arm=False)
            self.box_orchestrator.active_task = None
        else:
            self.log_box_process("退出飞机盒程序。")

        self.box_orchestrator = None
        self.log_box_process("播报内容: 已退出飞机盒程序。请使用语音唤醒小智。")
        self.state = "WAIT_WAKE"
        self.voice.speak("已退出飞机盒程序。请使用语音唤醒小智。")

    def close_picoclaw_agent(self):
        if os.name != "posix" or os.getenv("PICOCLAW_CLOSE_AGENT_ON_EXIT", "1") == "0":
            return
        try:
            user = os.getenv("USER", "").strip()
            command = ["pkill", "-f", "picoclaw agent"]
            if user:
                command[1:1] = ["-u", user]
            subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            print(f"[Realtime Listener WARNING] failed to close picoclaw agent: {exc}")

    def exit_all(self):
        if self.box_orchestrator and self.box_orchestrator.active_task:
            self.box_orchestrator.active_task.stop()
            self.box_orchestrator.active_task = None
        self.voice.speak("已退出实时语音监听。")
        self.voice.wait_until_done(timeout=5)
        self.running = False
        self.close_picoclaw_agent()

    def process_text(self, text):
        text = shortcut_to_voice_text(text)

        if has_any(text, QUIT_ALL_WORDS):
            self.exit_all()
            return

        if has_any(text, EXIT_WORDS):
            if self.state == "BOX_DEFECT":
                self.exit_box_defect_skill()
            else:
                self.exit_all()
            return

        if self.state == "WAIT_WAKE":
            if has_any(text, WAKE_WORDS):
                self.prompt_program()
            return

        if self.state == "WAIT_PROGRAM":
            if has_any(text, BOX_PROGRAM_WORDS):
                self.enter_box_defect_skill()
            else:
                self.voice.speak("暂时没有匹配到可执行程序。请说飞机盒缺陷检测。")
            return

        if self.state == "BOX_DEFECT":
            self.box_orchestrator.process_realtime_text(text)
            if not self.box_orchestrator.running:
                self.log_box_process("飞机盒程序已返回实时监听。")
                self.box_orchestrator = None
                self.prompt_wake()

    def run(self):
        print(f"[Realtime Listener] box skill dir: {BOX_SKILL_DIR}")
        self.prompt_wake()
        self.start_listener()
        try:
            while self.running:
                try:
                    text = self.commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.process_text(text)
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.stop_listener()
            if self.box_orchestrator and self.box_orchestrator.active_task:
                self.box_orchestrator.active_task.stop()
            self.close_picoclaw_agent()
            self.voice.release()


def main():
    RealtimeVoiceListenerSkill().run()


if __name__ == "__main__":
    main()
