from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, get_report_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import ReportData, ReportItemsUpdateRequest, ReportListData, ReportType
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ApiResponse[ReportListData])
def list_reports(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[ReportListData]:
    return ok(service.list_reports(current_user["id"]))


@router.post("/analyze", response_model=ApiResponse[ReportData], status_code=status.HTTP_202_ACCEPTED)
async def analyze_report(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
    file: UploadFile = File(...),
    report_type: ReportType = Form("other"),
) -> ApiResponse[ReportData]:
    content = await file.read()
    # OCR + model init is CPU-heavy; keep it off the event loop so the UI stays responsive.
    report = await run_in_threadpool(
        service.analyze,
        current_user["id"],
        file.filename or "report",
        report_type,
        content,
    )
    return ok(report)

@router.get("/{report_id}", response_model=ApiResponse[ReportData])
def get_report(
    report_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[ReportData]:
    return ok(service.get_report(current_user["id"], report_id))


@router.patch("/{report_id}/items", response_model=ApiResponse[ReportData])
def update_report_items(
    report_id: str,
    payload: ReportItemsUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[ReportData]:
    return ok(service.update_items(current_user["id"], report_id, payload))


@router.post("/{report_id}/interpret", response_model=ApiResponse[ReportData])
def interpret_report(
    report_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[ReportData]:
    return ok(service.interpret(current_user["id"], report_id))


@router.delete("/{report_id}", response_model=ApiResponse[None])
def delete_report(
    report_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> ApiResponse[None]:
    service.delete_report(current_user["id"], report_id)
    return ok(None)
