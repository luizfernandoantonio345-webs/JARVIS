from fastapi import APIRouter
from pydantic import BaseModel
from intents.confirmation_manager import list_pending_confirmations, respond_confirmation
from intents.intent_executor import execute_intent
from intents.intent_parser import parse_intent
from intents.schemas import Intent, IntentResult
from services.execute_service import run_python

router = APIRouter()


class ExecuteRequest(BaseModel):
    code: str
    timeout: int = 10


class ExecuteResponse(BaseModel):
    output: str


class IntentExecuteRequest(BaseModel):
    command: str


class IntentExecuteResponse(BaseModel):
    intent: Intent
    result: IntentResult


class ConfirmationResponse(BaseModel):
    confirmation_id: str
    approved: bool


@router.post("", response_model=ExecuteResponse)
def execute(request: ExecuteRequest):
    output = run_python(request.code, request.timeout)
    return ExecuteResponse(output=output)


@router.post("/intent", response_model=IntentExecuteResponse)
async def execute_structured_intent(request: IntentExecuteRequest):
    intent = await parse_intent(request.command)
    result = await execute_intent(intent)
    return IntentExecuteResponse(intent=intent, result=result)


@router.get("/intent/confirmations")
async def pending_intent_confirmations():
    return {"pending": [item.model_dump() for item in list_pending_confirmations()]}


@router.post("/intent/confirm")
async def confirm_intent_execution(request: ConfirmationResponse):
    ok = respond_confirmation(request.confirmation_id, request.approved)
    return {"ok": ok}
