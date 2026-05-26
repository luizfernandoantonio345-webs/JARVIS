import sounddevice as sd
import numpy as np
import soundfile as sf

# Testar com microfone padrão (índice 1 = Intel Smart Sound)
device_index = 1

print('Teste de gravacao - Microfone padrão')
print('Gravando 3 segundos... FALE AGORA!')
print()

try:
    audio = sd.rec(int(3 * 16000), samplerate=16000,
                   channels=1, dtype='float32', device=device_index)
    sd.wait()
    
    sf.write('test_mic.wav', audio, 16000)
    nivel = np.abs(audio).max()
    
    print('Salvo em test_mic.wav')
    print('Nivel de audio:', nivel)
    print()
    
    if nivel > 0.01:
        print('✓ HEADSET FUNCIONANDO - Nível aceitável')
    elif nivel > 0.001:
        print('⚠ Nível baixo - microfone pode estar muito quieto')
        print('  Aumente o volume do headset ou fale mais alto')
    else:
        print('✗ Sem áudio - dispositivo pode estar desconectado')
        print('  Verificar: Headset está conectado?')
except Exception as e:
    print(f'✗ Erro ao gravar: {e}')
