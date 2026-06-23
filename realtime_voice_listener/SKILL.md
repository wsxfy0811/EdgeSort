---
name: realtime-voice-listener
description: PicoClaw 启动后自动调用的独立常驻实时语音监听入口。负责唤醒小智、询问用户需要执行什么程序，并在听到“飞机盒”后调用 workspace/fjh/skill 中的飞机盒缺陷检测 skill。
entrypoint: "bash start_realtime_listener.sh"
auto_start: true
---

# 实时语音监听入口 Skill

## 自动启动

PicoClaw 启动后自动调用本 skill：

```bash
bash /home/elf/.picoclaw/workspace/skills/realtime_voice_listener/start_realtime_listener.sh
```

如果希望一个命令同时启动 `picoclaw agent` 和实时语音监听，使用：

```bash
bash /home/elf/.picoclaw/workspace/skills/realtime_voice_listener/start_picoclaw_with_voice.sh
```

该脚本会启动 `picoclaw agent`、实时语音监听，以及一个用于手动补充输入的文字终端。

当前版本执行后会尽量打开三个新终端：

- `PicoClaw Agent`：显示 `picoclaw agent` 文字交互界面
- `PicoClaw 实时语音监听`：显示实时语音程序进程、ASR 识别文本、TTS 播报输出
- `PicoClaw 语音文字补充输入`：当语音识别不准时，可输入短命令补充控制

如果系统没有可用终端模拟器，则会退回到当前终端运行 agent，并将实时语音监听写入日志。

如果 PicoClaw 只识别 Python 入口，也可以调用：

```bash
python3 /home/elf/.picoclaw/workspace/skills/realtime_voice_listener/main.py
```

或：

```bash
python3 /home/elf/.picoclaw/workspace/skills/realtime_voice_listener/skill.py
```

启动脚本会先执行：

```bash
source ~/text/ven/ai/bin/activate
```

并默认绑定 ELF2/RK3588 板载声卡：

```bash
PICOCLAW_AUDIO_CARD_NAME=rockchipnau8822
PICOCLAW_INPUT_CARD_NAME=rockchipnau8822
PICOCLAW_OUTPUT_CARD_NAME=rockchipnau8822
PICOCLAW_INPUT_SAMPLE_RATE=48000
PICOCLAW_INPUT_CHANNEL=best
```

也就是默认使用 `card1 rockchipnau8822` 采集语音，并通过同一卡的 3.5mm 耳机孔输出语音播报。如果现场 `sounddevice` 枚举编号变化，可临时用 `PICOCLAW_INPUT_DEVICE=<编号>`、`PICOCLAW_OUTPUT_DEVICE=<编号>` 覆盖。

然后启动实时监听入口：

```bash
python3 skill_realtime_listener.py
```

## 语音流程

1. 自动播报“请使用语音唤醒小智。”
2. 听到“小智”后，播报“我在。请问需要执行什么程序？”
3. 用户回答中出现“飞机盒”关键词后，调用 `/home/elf/.picoclaw/workspace/skills/fjh/skill` 中的飞机盒缺陷检测 skill。
4. 进入飞机盒程序时会再新开一个终端窗口显示飞机盒子程序日志，包括子程序阶段的识别文字、播报内容和流程状态；日志文件为 `~/.picoclaw/logs/box_defect_process.log`。
5. 后续由飞机盒缺陷检测 skill 继续询问模型、缺陷标签，并执行相机、YOLO、串口分拣流程。
6. 飞机盒程序运行中说“退出”，只退出飞机盒程序并回到实时语音监听，不关闭实时语音程序。
7. 只有在没有子程序运行时说“退出”，才退出实时语音监听，并自动关闭 `picoclaw agent` 终端、实时语音终端和子程序日志终端。

## 语音文字补充输入

`picovoice` 启动后会新开 `PicoClaw 语音文字补充输入` 终端。可输入以下短命令，系统会把它们转换成与语音识别相同的文本并送入实时监听流程：

```text
wake      唤醒小智
box       进入飞机盒程序
1         当前问模型时使用 1.rknn；当前问缺陷时检测 1污渍
2         当前问模型时使用 2.rknn；当前问缺陷时检测 2划痕
3         当前问模型时使用 3.rknn；当前问缺陷时检测 3缺角
add 2     添加划痕
rm 1      移除污渍
ok        确认/开始
no        不需要继续添加
change    更换参数
exit      退出当前程序
quit      退出实时语音程序
```

补充输入通道使用 FIFO 文件：

```bash
~/.picoclaw/runtime/voice_text_input.fifo
```

需要时也可以手动写入，推荐直接写入数字：

```bash
echo "1" > ~/.picoclaw/runtime/voice_text_input.fifo
```

## 关键词纠错

实时监听层会先做轻量纠错和小范围拼音匹配，不只针对“飞机盒”，也覆盖“小智、检测、模型、污渍、划痕、缺角、确认、取消、继续、更换、添加、移除、退出”等流程关键词。

例如“飞机河/飞鸡盒/飞几河”这类拼音接近 `feijihe` 的识别结果，会按“飞机盒”处理；“屋子/吴字”会按“污渍”处理；“画很”会按“划痕”处理；“却认/雀任”会按“确认”处理。

## 路径

默认调用的飞机盒缺陷检测 skill 路径：

```bash
/home/elf/.picoclaw/workspace/skills/fjh/skill
```

如现场路径不同，可以通过环境变量覆盖：

```bash
PICOCLAW_BOX_SKILL_DIR=/home/elf/.picoclaw/workspace/skills/fjh/skill
```
