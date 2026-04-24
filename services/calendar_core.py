import datetime
import uuid
from zoneinfo import ZoneInfo

TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")


def to_utc_naive(local_dt):
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=TIMEZONE_BR)
    return local_dt.astimezone(datetime.UTC).replace(tzinfo=None)


def to_local_datetime(utc_naive):
    if utc_naive is None:
        return None
    aware = utc_naive.replace(tzinfo=datetime.UTC)
    return aware.astimezone(TIMEZONE_BR)


def format_input_datetime(utc_naive):
    local = to_local_datetime(utc_naive)
    if local is None:
        return ""
    return local.strftime("%Y-%m-%dT%H:%M")


def format_human_datetime(utc_naive):
    local = to_local_datetime(utc_naive)
    if local is None:
        return "-"
    return local.strftime("%d/%m/%Y %H:%M")


def utc_naive_to_rfc3339(utc_naive):
    aware = utc_naive.replace(tzinfo=datetime.UTC)
    return aware.isoformat().replace("+00:00", "Z")


def parse_form_datetime(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError(
            "Formato de data/hora inválido. Use o seletor da página."
        ) from exc
    return to_utc_naive(parsed)


def parse_event_form(form):
    title = (form.get("title") or "").strip()
    if not title:
        raise ValueError("Título do evento é obrigatório.")
    if len(title) > 200:
        raise ValueError("Título do evento deve ter no máximo 200 caracteres.")

    starts_at = parse_form_datetime(form.get("starts_at"))
    ends_at = parse_form_datetime(form.get("ends_at"))
    if starts_at is None or ends_at is None:
        raise ValueError("Data e hora de início/fim são obrigatórias.")
    if ends_at <= starts_at:
        raise ValueError("A data/hora de término precisa ser maior que a de início.")

    return {
        "title": title,
        "description": (form.get("description") or "").strip() or None,
        "location": (form.get("location") or "").strip() or None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "is_all_day": bool(form.get("all_day")),
        "create_conference": bool(form.get("create_conference")),
    }


def extract_meet_link(remote):
    conference = remote.get("conferenceData") or {}
    for entry_point in conference.get("entryPoints") or []:
        if entry_point.get("entryPointType") == "video":
            return entry_point.get("uri") or None
    return remote.get("hangoutLink") or None


def google_event_payload(local_event, *, create_conference=False):
    payload = {
        "summary": local_event.title,
        "description": local_event.description or "",
        "location": local_event.location or "",
        "start": {
            "dateTime": utc_naive_to_rfc3339(local_event.starts_at),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": utc_naive_to_rfc3339(local_event.ends_at),
            "timeZone": "UTC",
        },
    }
    if create_conference:
        payload["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    return payload


def parse_google_event_datetime(payload):
    if not isinstance(payload, dict):
        return None, None

    raw_datetime = payload.get("dateTime")
    if raw_datetime:
        normalized = str(raw_datetime).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            timezone_name = str(payload.get("timeZone", "UTC")).strip() or "UTC"
            try:
                dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
            except Exception:
                dt = dt.replace(tzinfo=datetime.UTC)
        return dt.astimezone(datetime.UTC).replace(tzinfo=None), False

    raw_date = payload.get("date")
    if raw_date:
        date_value = datetime.date.fromisoformat(str(raw_date))
        timezone_name = (
            str(payload.get("timeZone") or TIMEZONE_BR.key).strip() or TIMEZONE_BR.key
        )
        try:
            event_tz = ZoneInfo(timezone_name)
        except Exception:
            event_tz = TIMEZONE_BR
        dt = datetime.datetime.combine(date_value, datetime.time.min, tzinfo=event_tz)
        return dt.astimezone(datetime.UTC).replace(tzinfo=None), True

    return None, None
