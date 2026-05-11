from fastapi import APIRouter, Body

from backend.actions.browser_control import _browser_action as _browser_async
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
