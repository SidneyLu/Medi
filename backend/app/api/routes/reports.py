from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_current_user, get_report_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import ReportAnalyzeData, ReportDetailData, ReportType
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/analyze", response_model=ApiResponse[ReportAnalyzeData])
async def analyze_report(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
    file: UploadFile = File(...),
    report_type: ReportType = Form("other"),
) -> ApiResponse[ReportAnalyzeData]:
    content = await file.read()
    return ok(service.analyze(current_user["id"], file.filename or "report", report_type, content))


@router.get("/{report_id}", response_model=ApiResponse[ReportDetailData])
def get_report(
    report_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[ReportDetailData]:
    return ok(service.get_report(current_user["id"], report_id))
