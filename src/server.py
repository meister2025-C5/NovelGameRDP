# 必要なパッケージ: aiortc, websockets, mss, opencv-python, av

import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack
import cv2
import numpy as np
import mss
import sounddevice as sd
import threading
import wave



# 画面キャプチャ設定
SCREEN_FPS = 30  # キャプチャフレームレート
SCREEN_MONITOR_INDEX = 1  # mssのmonitor番号（1=メイン画面）

# 音声キャプチャ設定
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 1


class SystemAudioTrack(AudioStreamTrack):
	kind = "audio"

	def __init__(self, samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS):
		super().__init__()
		self.samplerate = samplerate
		self.channels = channels
		self.recording = []  # Store audio chunks
		self.is_recording = False
		self.stream = None

	def start_recording(self):
		print("Starting audio recording...")
		self.is_recording = True
		self.stream = sd.InputStream(
			samplerate=self.samplerate,
			channels=self.channels,
			dtype='int16',
			callback=self._audio_callback
		)
		self.stream.start()

	def _audio_callback(self, indata, frames, time, status):
		if self.is_recording:
			self.recording.append(indata.copy())

	def stop_recording(self):
		print("Stopping audio recording...")
		self.is_recording = False
		if self.stream:
			self.stream.stop()
			self.stream.close()

		# Combine all recorded chunks
		full_recording = np.concatenate(self.recording, axis=0)

		# Save to WAV file
		output_file = "out.wav"
		with wave.open(output_file, 'wb') as wf:
			wf.setnchannels(self.channels)
			wf.setsampwidth(2)  # 16-bit PCM
			wf.setframerate(self.samplerate)
			wf.writeframes(full_recording.tobytes())
		print(f"Audio saved to {output_file}")

	async def recv(self):
		from av import AudioFrame
		if not self.is_recording:
			return None

		# Simulate receiving audio data
		chunk = np.zeros((self.samplerate // 10, self.channels), dtype=np.int16)  # Example chunk
		frame = AudioFrame(format="s16", layout="mono", samples=len(chunk))
		frame.planes[0].update(chunk.tobytes())
		frame.sample_rate = self.samplerate
		await asyncio.sleep(0.1)  # Simulate real-time streaming
		return frame

	async def stop(self):
		self.stop_recording()
		print("Audio track stopped.")

# 画面キャプチャ用VideoStreamTrack
class ScreenTrack(VideoStreamTrack):
	def __init__(self, fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX):
		super().__init__()
		self.sct = mss.mss()
		self.monitor = self.sct.monitors[monitor_index]
		self.fps = fps
		self.frame_time = 1.0 / fps
		self._last_frame = 0

	async def recv(self):
		from av import VideoFrame
		pts, time_base = await self.next_timestamp()
		# フレームレート制御
		now = asyncio.get_event_loop().time()
		wait = self._last_frame + self.frame_time - now
		if wait > 0:
			await asyncio.sleep(wait)
		self._last_frame = asyncio.get_event_loop().time()
		img = np.array(self.sct.grab(self.monitor))
		frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
		video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
		video_frame.pts = pts
		video_frame.time_base = time_base
		return video_frame

# シグナリングサーバー
pcs = set()

async def offer(websocket, path):
    try:
        params = await websocket.recv()
        params = json.loads(params)

        # Validate SDP parameters
        if "sdp" not in params or "type" not in params:
            print("Invalid SDP parameters received")
            return

        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        pcs.add(pc)
        print("Created for", path)

        # 画面キャプチャトラックを追加
        screen_track = ScreenTrack(fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX)
        pc.addTrack(screen_track)

        # 音声キャプチャトラックを追加
        audio_track = SystemAudioTrack()
        audio_track.start_recording()  # Start recording when client connects
        pc.addTrack(audio_track)

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await websocket.send(json.dumps({"type": "candidate", "candidate": candidate}))

        # クライアントからのICE candidate受信
        async def ice_listener():
            while True:
                try:
                    msg = await websocket.recv()
                    msg = json.loads(msg)
                    if msg["type"] == "candidate":
                        await pc.addIceCandidate(msg["candidate"])
                except Exception:
                    break

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await websocket.send(json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

        # ICE candidateの受信を別タスクで
        asyncio.ensure_future(ice_listener())

        # 接続維持
        await websocket.wait_closed()
        await audio_track.stop()  # Stop recording when client disconnects
        await pc.close()
        pcs.discard(pc)

    except Exception as e:
        print("Error in offer handler:", e)

async def main():
	async with websockets.serve(offer, "0.0.0.0", 8765):
		print("Signaling server started on ws://0.0.0.0:8765")
		await asyncio.Future()  # run forever

if __name__ == "__main__":
	asyncio.run(main())
