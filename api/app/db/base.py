from app.db.models import (
    Brand,
    PriceSnapshot,
    ProductAlias,
    ProductSeries,
    ProductSku,
    PromotionSnapshot,
    SellingPointSnapshot,
    SourceDocument,
    SourceSite,
    SpecSnapshot,
    TimelineEvent,
)
from app.db.session import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
