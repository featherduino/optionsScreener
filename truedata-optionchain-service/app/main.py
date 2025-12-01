from fastapi import FastAPI
from app.routers.optionchain import router as optionchain_router
from app.routers.health import router as health_router

app = FastAPI(title="TrueData OptionChain + Greeks API")

app.include_router(optionchain_router)
app.include_router(health_router)

@app.get("/")
def index():
    return {"msg": "TrueData OptionChain Microservice Running"}
