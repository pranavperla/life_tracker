"""Fitbit Web API integration: OAuth2 flow and data sync."""

from __future__ import annotations

import json
import time
import logging
from datetime import date, timedelta
from urllib.parse import urlencode

import aiohttp

from config import Config
from db.database import Database
from db import models

logger = logging.getLogger(__name__)

AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"
API_BASE = "https://api.fitbit.com"

SCOPES = "activity heartrate sleep profile oxygen_saturation temperature"


def get_auth_url() -> str:
    """
    Build Fitbit OAuth2 authorize URL. Must include ?response_type=code&client_id=... or
    Fitbit shows: invalid_request - Missing response_type parameter value (usually means
    the browser opened /oauth2/authorize with no query string — use the full URL only).
    """
    cid = (Config.FITBIT_CLIENT_ID or "").strip()
    redir = (Config.FITBIT_REDIRECT_URI or "").strip()
    if not cid:
        raise ValueError(
            "FITBIT_CLIENT_ID is empty. Copy Client ID from dev.fitbit.com into .env"
        )
    if not redir:
        raise ValueError("FITBIT_REDIRECT_URI is empty in .env")

    # Tuple order is preserved — response_type must be present for Fitbit
    params = [
        ("response_type", "code"),
        ("client_id", cid),
        ("redirect_uri", redir),
        ("scope", SCOPES),
        # Valid per Fitbit: 86400, 604800, 2592000, 31536000
        ("expires_in", "31536000"),
    ]
    return f"{AUTH_URL}?{urlencode(params)}"


def _fitbit_error_message(status: int, raw: str) -> str:
    """Short string for Telegram when token exchange fails."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"HTTP {status}: {raw[:280]}"
    errs = data.get("errors")
    if isinstance(errs, list) and errs:
        msg = errs[0].get("message") or errs[0].get("errorType")
        if msg:
            return str(msg)[:400]
    return (data.get("error_description") or data.get("error") or raw)[:400]


async def exchange_code(code: str, db: Database) -> tuple[bool, str]:
    """Exchange authorization code for access/refresh tokens. Returns (ok, error_detail)."""
    data = {
        "client_id": Config.FITBIT_CLIENT_ID,
        "grant_type": "authorization_code",
        "redirect_uri": Config.FITBIT_REDIRECT_URI,
        "code": code,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with aiohttp.ClientSession() as session:
        auth = aiohttp.BasicAuth(Config.FITBIT_CLIENT_ID, Config.FITBIT_CLIENT_SECRET)
        async with session.post(TOKEN_URL, data=data, headers=headers, auth=auth) as resp:
            raw = await resp.text()
            if resp.status != 200:
                logger.error("Fitbit token exchange failed: %s", raw)
                return False, _fitbit_error_message(resp.status, raw)
            body = json.loads(raw)

    await models.save_fitbit_tokens(
        db,
        access=body["access_token"],
        refresh=body["refresh_token"],
        expires_at=time.time() + body.get("expires_in", 28800),
    )
    logger.info("Fitbit tokens saved successfully")
    return True, ""


async def _get_valid_token(db: Database) -> str | None:
    """Get a valid access token, refreshing if expired."""
    tokens = await models.get_fitbit_tokens(db)
    if not tokens:
        return None

    if time.time() < tokens["expires_at"] - 300:
        return tokens["access_token"]

    # Refresh
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": Config.FITBIT_CLIENT_ID,
    }
    async with aiohttp.ClientSession() as session:
        auth = aiohttp.BasicAuth(Config.FITBIT_CLIENT_ID, Config.FITBIT_CLIENT_SECRET)
        async with session.post(TOKEN_URL, data=data, auth=auth) as resp:
            if resp.status != 200:
                logger.error("Fitbit token refresh failed: %s", await resp.text())
                return None
            body = await resp.json()

    await models.save_fitbit_tokens(
        db,
        access=body["access_token"],
        refresh=body["refresh_token"],
        expires_at=time.time() + body.get("expires_in", 28800),
    )
    return body["access_token"]


async def _api_get(token: str, path: str) -> dict | list | None:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}{path}", headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning("Fitbit API %s returned %s: %s", path, resp.status, await resp.text())
            return None


async def sync_fitbit_data(db: Database, target_date: date | None = None) -> bool:
    """Pull sleep, activity, and heart rate data from Fitbit for a given date."""
    token = await _get_valid_token(db)
    if not token:
        logger.warning("No valid Fitbit token, skipping sync")
        return False

    d = target_date or date.today()
    ds = d.isoformat()
    data: dict = {"date": ds}

    # Sleep
    sleep_resp = await _api_get(token, f"/1.2/user/-/sleep/date/{ds}.json")
    if sleep_resp and sleep_resp.get("summary"):
        summary = sleep_resp["summary"]
        data["sleep_hours"] = round(summary.get("totalMinutesAsleep", 0) / 60, 2)
        stages = summary.get("stages", {})
        data["deep_sleep_mins"] = stages.get("deep", 0)
        data["rem_sleep_mins"] = stages.get("rem", 0)

        # Sleep score (from sleep logs if available)
        if sleep_resp.get("sleep"):
            for log in sleep_resp["sleep"]:
                if log.get("efficiency"):
                    data["sleep_score"] = log["efficiency"]
                    break

    # Activity
    activity_resp = await _api_get(token, f"/1/user/-/activities/date/{ds}.json")
    if activity_resp and activity_resp.get("summary"):
        summary = activity_resp["summary"]
        data["steps"] = summary.get("steps", 0)
        data["calories_burned"] = summary.get("caloriesOut", 0)
        data["active_zone_mins"] = summary.get("activeScore", 0)
        # Fitbit's active zone minutes may be under a different key
        if "activeZoneMinutes" in summary:
            data["active_zone_mins"] = summary["activeZoneMinutes"].get("totalMinutes", 0)

    # Resting heart rate
    hr_resp = await _api_get(token, f"/1/user/-/activities/heart/date/{ds}/1d.json")
    if hr_resp:
        hr_data = hr_resp.get("activities-heart", [])
        if hr_data:
            value = hr_data[0].get("value", {})
            data["resting_hr"] = value.get("restingHeartRate")

    # SpO2
    spo2_resp = await _api_get(token, f"/1/user/-/spo2/date/{ds}.json")
    if spo2_resp and spo2_resp.get("value"):
        data["spo2"] = spo2_resp["value"].get("avg")

    # Skin temperature
    temp_resp = await _api_get(token, f"/1/user/-/temp/skin/date/{ds}.json")
    if temp_resp and temp_resp.get("tempSkin"):
        for entry in temp_resp["tempSkin"]:
            if entry.get("value"):
                data["skin_temp_variation"] = entry["value"].get("nightlyRelative")
                break

    # HRV
    hrv_resp = await _api_get(token, f"/1/user/-/hrv/date/{ds}.json")
    if hrv_resp and hrv_resp.get("hrv"):
        for entry in hrv_resp["hrv"]:
            if entry.get("value"):
                data["hrv"] = entry["value"].get("dailyRmssd")
                break

    if len(data) > 1:  # more than just date
        await models.upsert_fitbit_data(db, data)
        logger.info("Fitbit data synced for %s: %s", ds, list(data.keys()))
        return True

    logger.info("No Fitbit data available for %s", ds)
    return False


async def sync_recent(db: Database, days: int = 3) -> int:
    """Sync the last N days of Fitbit data to catch any missed days."""
    count = 0
    for i in range(days):
        d = date.today() - timedelta(days=i)
        if await sync_fitbit_data(db, d):
            count += 1
    return count
