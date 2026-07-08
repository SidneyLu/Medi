from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    search: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = ProductService(db)
    return service.list_products(search=search, brand=brand, category=category)


@router.get("/{sku_id}")
def get_product(sku_id: int, db: Session = Depends(get_db)):
    service = ProductService(db)
    detail = service.get_product_detail(sku_id)
    if not detail:
        raise HTTPException(status_code=404, detail="product not found")
    return detail


@router.get("/{sku_id}/timeline")
def get_timeline(sku_id: int, db: Session = Depends(get_db)):
    service = ProductService(db)
    return service.list_timeline(sku_id)
