from fastapi import FastAPI

from app.whatsapp.webhook import router as webhook_router

app = FastAPI(title="AiGymBuddy")
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
