"""
Alert administration: who gets alerted (recipients) and when (rules).

/recipients    CRUD for district collectors / SDMA officers and their channels
/alert-rules   CRUD for threshold + cooldown policies
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertRule, Recipient
from app.db.session import get_db
from app.schemas.alert import AlertRuleIn, AlertRuleOut, RecipientIn, RecipientOut
from app.services import geo_data

recipients_router = APIRouter()
rules_router = APIRouter()


def _canonical_region(name: str | None) -> str | None:
    if name is None:
        return None
    try:
        return geo_data.get_region(name)["name"]
    except geo_data.UnknownRegionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


# --- Recipients -------------------------------------------------------------
@recipients_router.get("", response_model=list[RecipientOut])
def list_recipients(db: Session = Depends(get_db)) -> list[Recipient]:
    return list(db.scalars(select(Recipient).order_by(Recipient.region, Recipient.district, Recipient.name)))


@recipients_router.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
def create_recipient(body: RecipientIn, db: Session = Depends(get_db)) -> Recipient:
    data = body.model_dump()
    data["region"] = _canonical_region(body.region)
    recipient = Recipient(**data)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


@recipients_router.put("/{recipient_id}", response_model=RecipientOut)
def update_recipient(recipient_id: int, body: RecipientIn, db: Session = Depends(get_db)) -> Recipient:
    recipient = db.get(Recipient, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")
    data = body.model_dump()
    data["region"] = _canonical_region(body.region)
    for key, value in data.items():
        setattr(recipient, key, value)
    db.commit()
    db.refresh(recipient)
    return recipient


@recipients_router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipient(recipient_id: int, db: Session = Depends(get_db)) -> Response:
    recipient = db.get(Recipient, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")
    db.delete(recipient)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Rules ------------------------------------------------------------------
@rules_router.get("", response_model=list[AlertRuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[AlertRule]:
    return list(db.scalars(select(AlertRule).order_by(AlertRule.id)))


@rules_router.post("", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: AlertRuleIn, db: Session = Depends(get_db)) -> AlertRule:
    data = body.model_dump()
    data["region"] = _canonical_region(body.region)
    rule = AlertRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@rules_router.put("/{rule_id}", response_model=AlertRuleOut)
def update_rule(rule_id: int, body: AlertRuleIn, db: Session = Depends(get_db)) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    data = body.model_dump()
    data["region"] = _canonical_region(body.region)
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> Response:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
