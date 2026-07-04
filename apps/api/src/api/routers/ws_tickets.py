from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws.broadcaster import broadcaster

router = APIRouter()


@router.websocket("/ws/tickets/{ticket_id}")
async def ticket_events_ws(websocket: WebSocket, ticket_id: str) -> None:
    await websocket.accept()
    queue = broadcaster.subscribe(ticket_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(ticket_id, queue)
