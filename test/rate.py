import sounddevice as sd

def get_device_info(name):
    results = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev['name'] == name:
            hostapi_name = sd.query_hostapis(dev['hostapi'])['name']
            samplerate = int(dev['default_samplerate'])
            results.append((idx, hostapi_name, samplerate))
    if not results:
        raise RuntimeError(f"Device '{name}' not found")
    return results

try:
    device_name = "ステレオ ミキサー (Realtek(R) Audio)"
    devices = get_device_info(device_name)
    print(f"Results for device '{device_name}':")
    for idx, hostapi, samplerate in devices:
        print(f"Index: {idx}, HostAPI: {hostapi}, Default Sample Rate: {samplerate}")
except Exception as e:
    print("Error:", e)