import sys, os, importlib, traceback, pathlib, json

sys.path.insert(0, 'backend')
os.chdir('C:/Users/cibernetico/JARVIS')

modules = [
    'config', 'main',
    'routes.health', 'routes.chat', 'routes.voice',
    'routes.agents', 'routes.autonomy', 'routes.memory',
    'routes.dashboard', 'routes.behavior', 'routes.computer',
    'services.chat_service', 'services.llm_service',
    'services.memory_service',
    'agents.master_orchestrator',
    'memory.persistent_memory',
    'voice_v2.output', 'voice_v2.resilient_loader',
    'voice_v2.pipeline', 'voice_v2.input',
    'autonomy.controller', 'autonomy.event_detector',
    'core.intent_classifier',
    'actions.computer_control', 'actions.browser_control',
    'actions.screen_processor', 'actions.send_message',
    'actions.weather_report', 'actions.youtube_video',
    'actions.reminder', 'actions.code_helper',
    'actions.file_controller', 'actions.web_search',
    'actions.save_memory', 'actions.game_updater',
    'actions.flight_finder', 'actions.agent_task',
    'actions.desktop_control', 'actions.dev_agent',
    'actions.file_processor', 'actions.open_app',
    'actions.computer_settings',
]

results = {'ok': [], 'fail': []}
for m in modules:
    try:
        importlib.import_module(m)
        results['ok'].append(m)
        print(f'  ✅ {m}')
    except Exception as e:
        results['fail'].append({'module': m, 'error': str(e)[:100]})
        print(f'  ❌ {m} — {str(e)[:80]}')

print(f'\n=== {len(results["ok"])} OK | {len(results["fail"])} FAIL ===')
with open('auditoria_resultado.json', 'w') as f:
    json.dump(results, f, indent=2)
print('Salvo em auditoria_resultado.json')