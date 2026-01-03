import soundcard as sc
import numpy as np
import wave

# 録音パラメータ
fs = 44100        # サンプルレート (Hz)
duration = 5      # 録音時間 (秒)
channels = 1      # モノラル（ステレオの場合は2）

# デフォルトのマイクを取得
mic = sc.default_microphone()
if mic is None:
    print("Error: デフォルトのマイクが取得できませんでした。")
    exit()

print(f"使用するマイク: {mic}")

print(f"録音開始...({duration}秒間)")
try:
    # 録音: context manager を使って recorder を生成し、録音終了まで numframes 分のデータを取得
    with mic.recorder(samplerate=fs, channels=channels) as recorder:
        print("Recorder initialized.")  # デバッグ用ログ
        recording = recorder.record(numframes=fs * duration)
        print("録音終了")
except Exception as e:
    print(f"録音中にエラーが発生しました: {e}")
    exit()

# soundcard は float32 の範囲(-1.0～1.0)のデータを返すので、16bit PCMに変換する
recording_int16 = np.int16(recording * 32767)

# WAV ファイルに保存
output_file = "output.wav"
try:
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(channels)  # チャネル数
        wf.setsampwidth(2)         # 16bit → 2バイト
        wf.setframerate(fs)        # サンプルレート
        wf.writeframes(recording_int16.tobytes())
    print(f"音声を {output_file} に保存しました。")
except Exception as e:
    print(f"WAVファイルの保存中にエラーが発生しました: {e}")