from fastapi import FastAPI
from router import router

app = FastAPI(
    title="NitHub AI Grading Service",
    description="AI grading microservice for the NitHub examination platform",
    version="1.0.0",
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "nithub-grading-service"}
