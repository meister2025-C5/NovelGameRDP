import sounddevice as sd
def get_mme_device_index_and_samplerate(name):
    for idx, dev in enumerate(sd.query_devices()):
        if dev['name'] == name and sd.query_hostapis(dev['hostapi'])['name'] == 'MME':
            return idx, int(dev['default_samplerate'])
    raise RuntimeError("Device not found")

try:
    idx, samplerate = get_mme_device_index_and_samplerate("ステレオ ミキサー (Realtek(R) Audio)")
    print(idx, samplerate)
except Exception as e:
    print("Error:", e)