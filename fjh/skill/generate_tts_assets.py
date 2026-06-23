# -*- coding: utf-8 -*-
import argparse
import os

from skill_voice import (
    TTS_ASSET_DIR,
    TTS_ASSET_PROMPTS,
    VoiceSkill,
    normalize_tts_text,
    resample_audio,
    write_wav,
)


def main():
    parser = argparse.ArgumentParser(description="Generate fixed PicoClaw TTS wav assets.")
    parser.add_argument(
        "--output-dir",
        default=TTS_ASSET_DIR,
        help="Directory for generated wav files.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Output wav sample rate.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.environ["PICOCLAW_TTS_ASSETS"] = "0"
    voice = VoiceSkill()
    try:
        for name, text in TTS_ASSET_PROMPTS.items():
            normalized = normalize_tts_text(text)
            samples, source_rate = voice._get_tts_audio(normalized)
            if args.sample_rate and source_rate != args.sample_rate:
                samples = resample_audio(samples, source_rate, args.sample_rate)
                source_rate = args.sample_rate

            output_path = os.path.join(args.output_dir, f"{name}.wav")
            write_wav(output_path, samples, source_rate)
            print(f"[TTS ASSET] {name}: {text} -> {output_path}")
    finally:
        voice.release()


if __name__ == "__main__":
    main()
