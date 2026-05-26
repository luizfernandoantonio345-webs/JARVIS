import sounddevice as sd

devices = sd.query_devices()
print('=== DISPOSITIVOS DE AUDIO ===')
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        print('  [{}] INPUT : {}'.format(i, d['name']))
    if d['max_output_channels'] > 0:
        print('  [{}] OUTPUT: {}'.format(i, d['name']))

print()
print('Padrao input :', sd.default.device[0])
print('Padrao output:', sd.default.device[1])
