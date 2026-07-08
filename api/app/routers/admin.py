from fastapi import APIRouter

from app.db.base import init_db
from app.services.seed_importer import import_seed_data

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed-import")
def seed_import():
    init_db()
    return import_seed_data()
