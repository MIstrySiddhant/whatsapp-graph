import re
import pandas as pd


def normalize_line(s: str) -> str:
    # Removes iPhone invisible marks + normalizes spaces
    return (
        s.replace("\ufeff", "")   # BOM
         .replace("\u200e", "")   # LRM (often looks like "‎")
         .replace("\u200f", "")   # RLM
         .replace("\u061c", "")   # Arabic letter mark
         .replace("\u202f", " ")  # narrow no-break space
         .replace("\u00a0", " ")  # no-break space
         .strip()
    )


def decode_bytes(raw: bytes) -> str:
    # safest decode order for WhatsApp exports
    for enc in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # last resort
    return raw.decode("latin-1", errors="replace")


def parse_whatsapp_text(text: str) -> pd.DataFrame:
    lines = [normalize_line(x) for x in text.splitlines() if normalize_line(x)]

    # iPhone / bracket style:
    # [02/02/24, 9:29:43 PM] Name: Message
    bracket_pattern = re.compile(
        r"""^\[
        (?P<date>\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}),\s*
        (?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*
        (?P<ampm>[APap][Mm])?
        \]\s*
        (?P<rest>.*)
        $""",
        re.VERBOSE,
    )

    # Android / dash style:
    # 13/10/23, 2:08 pm - Name: Message
    dash_pattern = re.compile(
        r"""^
        (?P<date>\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})
        [,\s]+
        (?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*
        (?P<ampm>[APap][Mm])?
        \s*-\s*
        (?P<rest>.*)
        $""",
        re.VERBOSE,
    )

    records = []
    current = None

    def start_message(date_str, time_str, ampm, rest):
        sender = None
        message = rest
        if ": " in rest:
            sender, message = rest.split(": ", 1)
        return {
            "raw_date": date_str,
            "raw_time": time_str,
            "ampm": (ampm.upper() if ampm else None),
            "sender": sender,
            "message": message,
        }

    for line in lines:
        m1 = bracket_pattern.match(line)
        m2 = dash_pattern.match(line)

        if m1 or m2:
            if current is not None:
                records.append(current)

            m = m1 if m1 else m2
            current = start_message(m.group("date"), m.group("time"), m.group("ampm"), m.group("rest"))
        else:
            if current is not None:
                current["message"] += "\n" + line

    if current is not None:
        records.append(current)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # datetime parsing (auto dayfirst/monthfirst)
    dt_str = df["raw_date"].astype(str) + " " + df["raw_time"].astype(str)
    if df["ampm"].notna().any():
        dt_str = dt_str + " " + df["ampm"].fillna("")

    dt_dayfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=False)
    df["datetime"] = dt_dayfirst if dt_dayfirst.notna().sum() >= dt_monthfirst.notna().sum() else dt_monthfirst

    df = df.dropna(subset=["datetime"]).copy()

    # keep only rows with a sender (system lines usually have no sender)
    df = df[df["sender"].notna()].copy()

    return df