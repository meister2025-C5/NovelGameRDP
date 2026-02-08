# 必要なパッケージ: aiortc, websockets, mss, opencv-python, av

import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack, RTCIceCandidate
import cv2
import numpy as np
import mss
import sounddevice as sd
import threading
import wave
import os
import fractions
import time
try:
	from pynput.mouse import Controller, Button
	import ctypes
	_mouse = Controller()
except Exception as e:
	print("pynput import/init failed:", e)
	_mouse = None



# 設定ファイルの絶対パスを取得
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# デフォルト設定
default_settings = {
    "SCREEN_FPS": 30,
    "SCREEN_MONITOR_INDEX": 2,
    "AUDIO_SAMPLE_RATE": 48000,
    "AUDIO_CHANNELS": 1,
    "SERVER_IP": "192.168.128.125"
}

# 設定を読み込む関数
def load_settings():
    try:
        with open(CONFIG_FILE, "r") as f:
            settings = json.load(f)
            print("読み込んだ設定:", settings)  # デバッグ用出力
            return settings
    except FileNotFoundError:
        print("設定ファイルが見つかりません。デフォルト設定を使用します。")
        return default_settings

# 設定を読み込む
settings = load_settings()

# 画面キャプチャ設定
SCREEN_FPS = settings["SCREEN_FPS"]
SCREEN_MONITOR_INDEX = settings["SCREEN_MONITOR_INDEX"]

# 音声キャプチャ設定
AUDIO_SAMPLE_RATE = settings["AUDIO_SAMPLE_RATE"]
AUDIO_CHANNELS = settings["AUDIO_CHANNELS"]

# サーバーのIPアドレス設定
SERVER_IP = settings["SERVER_IP"]

class SystemAudioTrack(AudioStreamTrack):
	kind = "audio"

	def __init__(self, samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS, device_id=None):
		super().__init__()
		self.samplerate = samplerate
		self.channels = channels
		self.q = asyncio.Queue()
		self.loop = asyncio.get_event_loop()
		self.stream = None
		self.device_id = device_id
		self._pts = 0

	def start_recording(self):
		print("Starting audio recording...")
		blocksize = int(self.samplerate * 0.02)
		try:
			if self.device_id is not None:
				self.stream = sd.InputStream(
					device=self.device_id,
					samplerate=self.samplerate,
					channels=self.channels,
					dtype='int16',
					callback=self._audio_callback,
					blocksize=blocksize
				)
			else:
				self.stream = sd.InputStream(
					samplerate=self.samplerate,
					channels=self.channels,
					dtype='int16',
					callback=self._audio_callback,
					blocksize=blocksize
				)
			self.stream.start()
			print(f"Audio stream started (device={self.device_id})")
		except Exception as e:
			print(f"Error starting audio stream: {e}")

	def _audio_callback(self, indata, frames, time, status):
		if status:
			print(status)
		# push a copy to the asyncio queue in a thread-safe way
		self.loop.call_soon_threadsafe(self.q.put_nowait, indata.copy())

	def stop_recording(self):
		print("Stopping audio recording...")
		if self.stream:
			self.stream.stop()
			self.stream.close()

	async def recv(self):
		from av import AudioFrame
		# wait for next chunk
		data = await self.q.get()
		# data shape: (samples, channels)
		samples = data.shape[0]
		layout = 'mono' if self.channels == 1 else 'stereo'
		frame = AudioFrame(format='s16', layout=layout, samples=samples)
		frame.planes[0].update(data.tobytes())
		frame.sample_rate = self.samplerate

		# set pts/time_base based on sample count
		frame.pts = self._pts
		frame.time_base = fractions.Fraction(1, self.samplerate)
		self._pts += samples
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

		# send server ICE candidates to client
		@pc.on("icecandidate")
		async def on_icecandidate(candidate):
			if candidate:
				try:
					await websocket.send(json.dumps({"type": "candidate", "candidate": candidate}))
				except Exception as e:
					print("Failed to send candidate:", e)

		# buffer for any incoming candidates before remote description is set
		candidate_buffer = []

		# track pressed buttons to detect stuck presses
		pressed_buttons = {}

		async def _release_stuck_buttons():
			import time
			while True:
				now = time.time()
				for b, ts in list(pressed_buttons.items()):
					if now - ts > 5.0:
						print(f"Releasing stuck button: {b}")
						try:
							_mouse.release(Button.left if b == 'left' else Button.right)
						except Exception as e:
							print('watchdog release error', e)
						pressed_buttons.pop(b, None)
				await asyncio.sleep(1.0)

		# start watchdog task for this connection
		watchdog_task = asyncio.create_task(_release_stuck_buttons())

		# read signaling messages until websocket closes
		while True:
			try:
				msg_raw = await websocket.recv()
			except Exception:
				break

			try:
				msg = json.loads(msg_raw)
			except Exception:
				print("Received non-json signaling message")
				continue

			# Input messages (from client overlay)
			if msg.get("type") == "input":
				def handle_input(m):
					if _mouse is None:
						print("Mouse controller not available")
						return
					print('handle_input', m)
					try:
						# screen size (Windows)
						try:
							screen_w = ctypes.windll.user32.GetSystemMetrics(0)
							screen_h = ctypes.windll.user32.GetSystemMetrics(1)
						except Exception:
							# fallback to 1920x1080
							screen_w, screen_h = 1920, 1080
						if m.get('input') == 'mouse':
							# only relative movement (dx/dy normalized) is supported now
							action = m.get('action')
							# apply relative movement if provided
							if 'dx' in m or 'dy' in m:
								dx_norm = float(m.get('dx', 0))
								dy_norm = float(m.get('dy', 0))
								dx_px = int(dx_norm * screen_w)
								dy_px = int(dy_norm * screen_h)
								try:
									_mouse.move(dx_px, dy_px)
								except Exception:
									# fallback: adjust by current position
									try:
										cx, cy = _mouse.position
										_mouse.position = (int(cx + dx_px), int(cy + dy_px))
									except Exception:
										pass
							# handle button actions (down/up) independent of coordinates
						if action == 'click':
							button_name = m.get('button', 'left')
							button = Button.left if button_name == 'left' else Button.right
							try:
								_mouse.click(button)
							except Exception as e:
								print('click error', e)
						if action == 'down':
							button_name = m.get('button', 'left')
							button = Button.left if button_name == 'left' else Button.right
							_mouse.press(button)
							pressed_buttons[button_name] = time.time()
						elif action == 'up':
							button_name = m.get('button', 'left')
							button = Button.left if button_name == 'left' else Button.right
							try:
								_mouse.release(button)
							except Exception as e:
								print('release error', e)
							pressed_buttons.pop(button_name, None)
						elif m.get('input') == 'wheel':
							dx = float(m.get('deltaX', 0))
							dy = float(m.get('deltaY', 0))
							# Convert pixel-ish delta to scroll clicks (WHEEL_DELTA=120)
							try:
								sx = int(dx / 120)
								sy = int(dy / 120)
							except Exception:
								sx = 0
								sy = int(dy)
							_mouse.scroll(sx, sy)
					except Exception as e:
						print('handle_input error', e)
				# delegate to thread
				asyncio.get_event_loop().run_in_executor(None, handle_input, msg)
				continue

			# Offer handling
			if msg.get("type") == "offer" and "sdp" in msg:
				offer = RTCSessionDescription(sdp=msg["sdp"], type=msg["type"])
				await pc.setRemoteDescription(offer)

				# apply any buffered candidates (convert dict->RTCIceCandidate)
				for c in candidate_buffer:
					try:
						if isinstance(c, dict):
							rtc_c = RTCIceCandidate(
								sdpMid=c.get('sdpMid'),
								sdpMLineIndex=c.get('sdpMLineIndex'),
								candidate=c.get('candidate')
							)
							await pc.addIceCandidate(rtc_c)
						else:
							await pc.addIceCandidate(c)
					except Exception as e:
						print("Error adding buffered candidate:", e)
				candidate_buffer.clear()

				# create and send answer
				answer = await pc.createAnswer()
				await pc.setLocalDescription(answer)
				await websocket.send(json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

			# Candidate handling
			elif msg.get("type") == "candidate" and msg.get("candidate"):
				cand = msg["candidate"]
				# convert incoming candidate dict to RTCIceCandidate
				try:
					rtc_cand = RTCIceCandidate(
						sdpMid=cand.get('sdpMid'),
						sdpMLineIndex=cand.get('sdpMLineIndex'),
						candidate=cand.get('candidate')
					)
				except Exception:
					rtc_cand = None

				if pc.remoteDescription is None:
					# buffer the raw dict; will convert when applying
					candidate_buffer.append(cand)
				else:
					if rtc_cand is not None:
						try:
							await pc.addIceCandidate(rtc_cand)
						except Exception as e:
							print("Error adding candidate:", e)
					else:
						print("Invalid candidate format received:", cand)
			else:
				print("Unexpected signaling message:", msg)

		# connection closed, cleanup
		# cancel watchdog
		try:
			watchdog_task.cancel()
		except Exception:
			pass
		await audio_track.stop()
		await pc.close()
		pcs.discard(pc)

	except Exception as e:
		print("Error in offer handler:", e)

async def main():
	async with websockets.serve(offer, SERVER_IP, 8765):
		print(f"Signaling server started on ws://{SERVER_IP}:8765")
		await asyncio.Future()  # run forever

if __name__ == "__main__":
	asyncio.run(main())
