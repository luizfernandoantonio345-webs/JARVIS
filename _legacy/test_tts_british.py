import asyncio
import sys
sys.path.insert(0, 'backend')

async def test_british_jarvis():
    from voice.output import speak
    
    print('Testing JARVIS British voice...')
    print()
    
    message = (
        'Good evening, Sir. All systems are operational. '
        'J.A.R.V.I.S. is online and ready for your commands.'
    )
    
    print(f'Speaking: "{message}"')
    print()
    
    ok = await speak(message)
    print()
    print(f'TTS Result: {ok}')
    
    if ok:
        print('✓ British voice working correctly')
    else:
        print('⚠ Check TTS configuration')

if __name__ == '__main__':
    asyncio.run(test_british_jarvis())
