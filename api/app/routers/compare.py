from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import CompareRequest
from app.services.product_service import ProductService

router = APIRouter(tags=["compare"])


@router.post("/compare")
def compare(payload: CompareRequest, db: Session = Depends(get_db)):
    service = ProductService(db)
    return service.build_compare_table(payload.sku_ids)
