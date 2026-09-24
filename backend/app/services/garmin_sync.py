"""Garmin-Connect-Anbindung: Login (inkl. Zwei-Faktor-Code), Sync im Hintergrund, Speichern ohne Duplikate."""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..database import SessionLocal
from ..models import Activity, DailyMetrics, SleepRecord, SyncLog
from . import garmin_parse as gp

log = logging.getLogger("lifeos.garmin")


class GarminError(Exception):
    """Fehler mit verständlicher deutscher Meldung."""


class GarminNeedsLogin(GarminError):
    pass


class GarminNeedsMfa(GarminError):
    pass


def _token_file_exists() -> bool:
    return (config.GARMIN_TOKEN_DIR / "garmin_tokens.json").exists()


class GarminManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client: Any = None
        self._pending_mfa: Any = None
        self._sync_thread: threading.Thread | None = None
        self.state: dict[str, Any] = {
            "running": False,
            "phase": "",
            "progress": 0,
            "total": 0,
            "last_error": "",
            "last_message": "",
        }

    # ------------------------------------------------------------ Status
    def status(self) -> dict[str, Any]:
        with SessionLocal() as db:
            last = (
                db.query(SyncLog)
                .filter(SyncLog.service == "garmin")
                .order_by(SyncLog.started_at.desc())
                .first()
            )
            last_ok = (
                db.query(SyncLog)
                .filter(SyncLog.service == "garmin", SyncLog.status == "ok")
                .order_by(SyncLog.finished_at.desc())
                .first()
            )
        return {
            "credentials_in_env": bool(config.GARMIN_EMAIL and config.GARMIN_PASSWORD),
            "has_tokens": _token_file_exists(),
            "connected": self._client is not None or _token_file_exists(),
            "needs_mfa": self._pending_mfa is not None,
            "sync": dict(self.state),
            "last_sync": last_ok.finished_at.isoformat() if last_ok and last_ok.finished_at else None,
            "last_status": last.status if last else None,
            "last_log_message": last.message if last else "",
        }

    # ------------------------------------------------------------ Login
    def _new_garmin(self, email: str | None = None, password: str | None = None, mfa: bool = False):
        try:
            from garminconnect import Garmin
        except ImportError as exc:  # pragma: no cover - nur ohne Abhängigkeit
            raise GarminError("Die Bibliothek „garminconnect“ ist nicht installiert.") from exc
        return Garmin(email=email, password=password, return_on_mfa=mfa)

    def _login_with_tokens(self):
        garmin = self._new_garmin()
        garmin.login(str(config.GARMIN_TOKEN_DIR))
        return garmin

    def login(self, email: str | None = None, password: str | None = None) -> str:
        """Meldet sich an. Rückgabe: "ok" oder "needs_mfa"."""
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        )

        email = (email or config.GARMIN_EMAIL or "").strip()
        password = password or config.GARMIN_PASSWORD
        if not email or not password:
            raise GarminNeedsLogin(
                "Keine Garmin-Zugangsdaten gefunden. Trage GARMIN_EMAIL und GARMIN_PASSWORD in die .env ein "
                "oder melde dich unter Einstellungen → Verbindungen an."
            )
        with self._lock:
            garmin = self._new_garmin(email, password, mfa=True)
            try:
                status, _ = garmin.login()
            except GarminConnectAuthenticationError as exc:
                raise GarminError(
                    "Garmin-Anmeldung fehlgeschlagen – E-Mail oder Passwort prüfen. "
                    f"(Details: {str(exc).splitlines()[0]})"
                ) from exc
            except GarminConnectTooManyRequestsError as exc:
                raise GarminError(
                    "Garmin blockiert gerade zu viele Anmeldeversuche. Bitte ein paar Minuten warten."
                ) from exc
            except GarminConnectConnectionError as exc:
                raise GarminError(f"Garmin ist nicht erreichbar: {exc}") from exc

            if status == "needs_mfa":
                self._pending_mfa = garmin
                return "needs_mfa"
            self._finish_login(garmin)
            return "ok"

    def submit_mfa(self, code: str) -> str:
        with self._lock:
            garmin = self._pending_mfa
            if garmin is None:
                raise GarminError("Es wartet keine Anmeldung auf einen Code. Bitte zuerst neu anmelden.")
            try:
                garmin.resume_login(None, code.strip())
            except Exception as exc:
                raise GarminError(
                    f"Der Zwei-Faktor-Code wurde nicht akzeptiert ({exc}). Bitte erneut versuchen."
                ) from exc
            self._pending_mfa = None
            self._finish_login(garmin)
            return "ok"

    def _finish_login(self, garmin) -> None:
        config.GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        garmin.client.dump(str(config.GARMIN_TOKEN_DIR))
        # Neu über die Tokens anmelden, damit Profil/Anzeigename geladen sind
        self._client = self._login_with_tokens()

    def logout(self) -> None:
        with self._lock:
            self._client = None
            self._pending_mfa = None
            if config.GARMIN_TOKEN_DIR.exists():
                shutil.rmtree(config.GARMIN_TOKEN_DIR, ignore_errors=True)

    def get_client(self):
        with self._lock:
            if self._client is not None:
                return self._client
            if self._pending_mfa is not None:
                raise GarminNeedsMfa("Garmin wartet auf den Zwei-Faktor-Code (Einstellungen → Verbindungen).")
            if _token_file_exists():
                try:
                    self._client = self._login_with_tokens()
                    return self._client
                except Exception as exc:  # Tokens abgelaufen → Neu-Login versuchen
                    log.info("Garmin-Tokens ungültig: %s", exc)
            if config.GARMIN_EMAIL and config.GARMIN_PASSWORD:
                result = self.login()
                if result == "needs_mfa":
                    raise GarminNeedsMfa(
                        "Garmin verlangt einen Zwei-Faktor-Code. Gib ihn unter Einstellungen → Verbindungen ein."
                    )
                return self._client
            raise GarminNeedsLogin("Garmin ist nicht verbunden.")

    # ------------------------------------------------------------ Sync
    def start_sync(self, days: int | None = None) -> bool:
        with self._lock:
            if self.state["running"]:
                return False
            self.state.update(running=True, phase="Starte …", progress=0, total=0, last_error="")
            self._sync_thread = threading.Thread(target=self._run_sync, args=(days,), daemon=True)
            self._sync_thread.start()
            return True

    def _run_sync(self, days: int | None) -> None:
        with SessionLocal() as db:
            entry = SyncLog(service="garmin", status="läuft")
            db.add(entry)
            db.commit()
            try:
                client = self.get_client()
                count = sync_all(db, client, days=days, progress=self._progress)
                entry.status = "ok"
                entry.items = count
                entry.message = f"{count} Datensätze aktualisiert."
                self.state["last_message"] = entry.message
                # Tokens nach dem Sync sichern (evtl. erneuert)
                try:
                    client.client.dump(str(config.GARMIN_TOKEN_DIR))
                except Exception:  # pragma: no cover
                    pass
            except GarminNeedsMfa as exc:
                entry.status = "2fa"
                entry.message = str(exc)
                self.state["last_error"] = str(exc)
            except GarminError as exc:
                entry.status = "fehler"
                entry.message = str(exc)
                self.state["last_error"] = str(exc)
            except Exception as exc:  # pragma: no cover - unerwartet
                log.exception("Garmin-Sync fehlgeschlagen")
                entry.status = "fehler"
                entry.message = f"Unerwarteter Fehler: {exc}"
                self.state["last_error"] = entry.message
            finally:
                entry.finished_at = datetime.now().replace(microsecond=0)
                db.commit()
                self.state.update(running=False, phase="")

    def _progress(self, phase: str, done: int, total: int) -> None:
        self.state.update(phase=phase, progress=done, total=total)


manager = GarminManager()


def _days_to_sync(db: Session, requested: int | None) -> int:
    if requested:
        return max(1, min(int(requested), 365))
    last_ok = (
        db.query(SyncLog)
        .filter(SyncLog.service == "garmin", SyncLog.status == "ok")
        .order_by(SyncLog.finished_at.desc())
        .first()
    )
    if last_ok is None or last_ok.finished_at is None:
        return 42  # Erstsync: 6 Wochen für Trends und chronische Last
    since = (date.today() - last_ok.finished_at.date()).days
    configured = int(settings_store.get(db, "garmin_sync_days") or 14)
    return max(3, min(since + 2, configured))


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        log.info("Garmin-Abruf %s%s fehlgeschlagen: %s", getattr(fn, "__name__", fn), args, exc)
        return None


def upsert_activity(db: Session, parsed: dict[str, Any]) -> Activity:
    act = db.query(Activity).filter(Activity.garmin_id == parsed["garmin_id"]).one_or_none()
    if act is None:
        act = Activity(**parsed)
        db.add(act)
    else:
        for key, value in parsed.items():
            setattr(act, key, value)
    act.is_demo = False
    return act


def upsert_daily(db: Session, day: date, values: dict[str, Any]) -> DailyMetrics:
    row = db.get(DailyMetrics, day)
    if row is None:
        row = DailyMetrics(date=day)
        db.add(row)
    elif row.is_demo:
        # Beispielwerte vollständig ersetzen
        for column in DailyMetrics.__table__.columns.keys():
            if column not in ("date", "updated_at"):
                setattr(row, column, None)
    for key, value in values.items():
        if value is not None:
            setattr(row, key, value)
    row.is_demo = False
    return row


def upsert_sleep(db: Session, parsed: dict[str, Any]) -> SleepRecord:
    row = db.get(SleepRecord, parsed["date"])
    if row is None:
        row = SleepRecord(**parsed)
        db.add(row)
    else:
        for key, value in parsed.items():
            setattr(row, key, value)
    row.is_demo = False
    return row


def remove_demo_fitness_data(db: Session) -> None:
    for model in (Activity, DailyMetrics, SleepRecord):
        db.execute(delete(model).where(model.is_demo.is_(True)))
    db.commit()


def sync_all(db: Session, client, days: int | None = None, progress=None) -> int:
    """Holt alle Garmin-Daten der letzten `days` Tage und speichert sie."""
    n_days = _days_to_sync(db, days)
    today = date.today()
    start = today - timedelta(days=n_days - 1)
    total_steps = n_days + 1
    count = 0

    # Beim ersten echten Sync die Beispiel-Fitnessdaten entfernen
    remove_demo_fitness_data(db)

    if progress:
        progress("Aktivitäten", 0, total_steps)
    activities = _safe(client.get_activities_by_date, start.isoformat(), today.isoformat()) or []
    for raw in activities:
        parsed = gp.parse_activity(raw)
        if not parsed:
            continue
        existing = db.query(Activity).filter(Activity.garmin_id == parsed["garmin_id"]).one_or_none()
        if not gp.has_zone_data(parsed):
            if existing is not None and any(getattr(existing, f"z{z}_s") for z in range(1, 6)):
                for z in range(1, 6):
                    parsed[f"z{z}_s"] = getattr(existing, f"z{z}_s")
            else:
                zones = _safe(client.get_activity_hr_in_timezones, parsed["garmin_id"])
                parsed.update(gp.parse_hr_zones(zones))
        upsert_activity(db, parsed)
        count += 1
    db.commit()

    for i in range(n_days):
        day = start + timedelta(days=i)
        iso = day.isoformat()
        if progress:
            progress(f"Tageswerte {day.strftime('%d.%m.')}", i + 1, total_steps)
        values: dict[str, Any] = {}
        values.update(gp.parse_user_summary(_safe(client.get_user_summary, iso) or {}))
        values.update(gp.parse_hrv(_safe(client.get_hrv_data, iso)))
        readiness = None
        if hasattr(client, "get_morning_training_readiness"):
            readiness = _safe(client.get_morning_training_readiness, iso)
        if not readiness:
            readiness = _safe(client.get_training_readiness, iso)
        values.update(gp.parse_training_readiness(readiness))
        status = gp.parse_training_status(_safe(client.get_training_status, iso) or {})
        values.update({k: v for k, v in status.items() if v is not None})
        if not values.get("vo2max"):
            vo2 = gp.parse_max_metrics(_safe(client.get_max_metrics, iso))
            if vo2:
                values["vo2max"] = vo2
        if any(v is not None for v in values.values()):
            upsert_daily(db, day, values)
            count += 1
        sleep = gp.parse_sleep(_safe(client.get_sleep_data, iso) or {})
        if sleep:
            upsert_sleep(db, sleep)
            count += 1
        db.commit()

    if progress:
        progress("Fertig", total_steps, total_steps)
    return count
