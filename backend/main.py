
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import yaml
from .optimizer import optimize_from_dict

app = FastAPI(title="Carbon-aware LLM Placement API v2")

class OptimizeRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    yaml: Optional[str] = None

@app.post("/optimize")
async def optimize(req: OptimizeRequest):
    if req.yaml:
        try:
            cfg = yaml.safe_load(req.yaml)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    elif req.config:
        cfg = req.config
    else:
        raise HTTPException(status_code=400, detail="Provide 'config' JSON or 'yaml' text")
    try:
        result = optimize_from_dict(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result
