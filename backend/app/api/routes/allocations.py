from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import AllocationCreate, AllocationOut
from app.db.session import get_db
from app.models.allocation import PortfolioAllocation


router = APIRouter()


@router.post("", response_model=AllocationOut)
def create_allocation(body: AllocationCreate, db: Session = Depends(get_db)):
    mode = (body.mode or "paper").strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=400, detail="mode must be paper or live")

    row = PortfolioAllocation(
        mode=mode,
        account_id=str(body.account_id),
        portfolio_id=body.portfolio_id,
        amount=float(body.amount),
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AllocationOut(
        id=row.id,
        created_at=row.created_at,
        mode=row.mode,
        account_id=row.account_id,
        portfolio_id=row.portfolio_id,
        amount=float(row.amount),
        notes=row.notes,
    )


@router.get("", response_model=list[AllocationOut])
def list_allocations(
    portfolio_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(PortfolioAllocation).order_by(PortfolioAllocation.created_at.desc())
    if portfolio_id:
        q = q.filter(PortfolioAllocation.portfolio_id == str(portfolio_id))
    rows = q.all()
    return [
        AllocationOut(
            id=r.id,
            created_at=r.created_at,
            mode=r.mode,
            account_id=r.account_id,
            portfolio_id=r.portfolio_id,
            amount=float(r.amount),
            notes=r.notes,
        )
        for r in rows
    ]

