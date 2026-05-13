from fastapi import APIRouter, Body

from backend.actions.browser_control import _browser_action as _browser_async
from backend.actions.send_message import send_message
from backend.actions.weather_report import weather_action
from backend.actions.youtube_video import youtube_video
from backend.actions.reminder import reminder
from backend.actions.code_helper import code_helper
from backend.actions.file_controller import file_controller
from backend.actions.web_search import web_search
from backend.actions.save_memory import save_memory, load_user_memory, get_memory_summary
from backend.actions.game_updater import game_updater
from backend.actions.flight_finder import flight_finder
from backend.actions.agent_task import agent_task, get_queue
from backend.actions.computer_control import computer_control
from backend.actions.computer_settings import computer_settings
from backend.actions.desktop_control import desktop_control
from backend.actions.dev_agent import dev_agent
from backend.actions.file_processor import file_processor
from backend.actions.open_app import open_app
from backend.actions.screen_processor import screen_process

router = APIRouter()


@router.post("/control")
async def control(params: dict = Body(...)):
    return {"result": computer_control(params)}


@router.post("/browser")
async def browser(params: dict = Body(...)):
    return {"result": await _browser_async(params)}


@router.post("/screen")
async def screen(params: dict = Body(...)):
    return {"result": screen_process(params)}


@router.post("/desktop")
async def desktop(params: dict = Body(...)):
    return {"result": desktop_control(params)}


@router.post("/settings")
async def settings(params: dict = Body(...)):
    return {"result": computer_settings(params)}


@router.post("/open-app")
async def open_application(params: dict = Body(...)):
    return {"result": open_app(params)}


@router.post("/files")
async def files(params: dict = Body(...)):
    return {"result": file_processor(params)}


@router.post("/dev")
async def dev(params: dict = Body(...)):
    return {"result": dev_agent(params)}


@router.post("/message")
async def message(params: dict = Body(...)):
    return {"result": send_message(params)}


@router.post("/weather")
async def weather(params: dict = Body(...)):
    return {"result": weather_action(params)}


@router.post("/youtube")
async def youtube(params: dict = Body(...)):
    return {"result": youtube_video(params)}


@router.post("/reminder")
async def set_reminder(params: dict = Body(...)):
    return {"result": reminder(params)}


@router.post("/code")
async def code(params: dict = Body(...)):
    return {"result": code_helper(params)}


@router.post("/filemanager")
async def filemanager(params: dict = Body(...)):
    return {"result": file_controller(params)}


@router.post("/websearch")
async def websearch(params: dict = Body(...)):
    return {"result": web_search(params)}


@router.post("/memory")
async def memory_save(params: dict = Body(...)):
    return {"result": save_memory(params)}


@router.get("/memory/summary")
async def memory_summary():
    return get_memory_summary()


@router.get("/memory/context")
async def memory_context():
    return {"context": load_user_memory()}


@router.post("/games")
async def games(params: dict = Body(...)):
    return {"result": game_updater(params)}


@router.post("/flights")
async def flights(params: dict = Body(...)):
    return {"result": flight_finder(params)}


@router.post("/task")
async def task(params: dict = Body(...)):
    return {"result": agent_task(params)}


@router.get("/tasks")
async def list_tasks():
    return {"tasks": get_queue().list_tasks()}
