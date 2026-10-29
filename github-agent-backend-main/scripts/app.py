from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
from agent import analyze_repo
import os
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(title="Repo Audit Agent API")

executor = ThreadPoolExecutor(max_workers=2)

class AnalyzeRequest(BaseModel):
    repo: str
    out: str = "reports/report.json"

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    loop = asyncio.get_event_loop()
    if not req.repo.startswith("http"):
        raise HTTPException(status_code=400, detail="repo must be a URL")
    out_path = req.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # Run blocking analyze_repo in threadpool
    report = await loop.run_in_executor(executor, analyze_repo, req.repo, out_path)
    return {"status": "done", "report_path": out_path}
