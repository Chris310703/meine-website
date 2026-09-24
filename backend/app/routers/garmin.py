"""Garmin: Status, Login inkl. Zwei-Faktor-Code, Synchronisation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.garmin_sync import GarminError, manager

router = APIRouter(prefix="/api/garmin", tags=["Garmin"])


class LoginIn(BaseModel):
    email: str | None = None
    password: str | None = None


class MfaIn(BaseModel):
    code: str


class SyncIn(BaseModel):
    days: int | None = None


@router.get("/status")
def status() -> dict[str, Any]:
    return manager.status()


@router.post("/login")
def login(payload: LoginIn) -> dict[str, Any]:
    try:
        result = manager.login(payload.email, payload.password)
    except GarminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result == "ok":
        manager.start_sync()
    return {"result": result, "status": manager.status()}


@router.post("/mfa")
def mfa(payload: MfaIn) -> dict[str, Any]:
    try:
        manager.submit_mfa(payload.code)
    except GarminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    manager.start_sync()
    return {"result": "ok", "status": manager.status()}


@router.post("/logout")
def logout() -> dict[str, Any]:
    manager.logout()
    return {"result": "ok", "status": manager.status()}


@router.post("/sync")
def sync(payload: SyncIn | None = None) -> dict[str, Any]:
    started = manager.start_sync(payload.days if payload else None)
    return {"started": started, "status": manager.status()}
