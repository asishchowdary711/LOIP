import json
import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import ValidationError
from loip.schemas.decision import LoanApplication, OnboardingDecision
from loip.pipelines.onboarding import OnboardingPipeline

router = APIRouter(prefix="/onboard", tags=["Onboarding"])
pipeline = OnboardingPipeline(mock_mode=True)

@router.post("", response_model=OnboardingDecision)
async def onboard_application(
    application: str = Form(...),
    documents: list[UploadFile] = File(...)
):
    try:
        app_data = json.loads(application)
        loan_app = LoanApplication(**app_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid application data: {str(e)}")
        
    images = []
    for doc in documents:
        contents = await doc.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is not None:
            images.append(img)
            
    if not images:
        raise HTTPException(status_code=400, detail="No valid images provided")
        
    try:
        decision = await pipeline.execute(loan_app, images, app_data)
        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
