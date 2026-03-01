import re
import pandas as pd


# --------------------------
# Parsing (iPhone + Android)
# --------------------------
def _normalize_line(s: str) -> str:
    return (
        s.replace("\ufeff", "")
         .replace("\u200e", "")
         .replace("\u200f", "")
         .replace("\u061c", "")
         .replace("\u202f", " ")
         .replace("\u00a0", " ")
         .strip()
    )


def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_whatsapp_text(text: str) -> pd.DataFrame:
    lines = [_normalize_line(x) for x in text.splitlines()]
    lines = [x for x in lines if x]

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

    dt_str = df["raw_date"].astype(str) + " " + df["raw_time"].astype(str)
    if df["ampm"].notna().any():
        dt_str = dt_str + " " + df["ampm"].fillna("")

    dt_dayfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=False)
    df["datetime"] = dt_dayfirst if dt_dayfirst.notna().sum() >= dt_monthfirst.notna().sum() else dt_monthfirst

    df = df.dropna(subset=["datetime"]).copy()
    df = df[df["sender"].notna()].copy()

    df["sender"] = df["sender"].astype(str).str.strip()
    df["message"] = df["message"].astype(str)

    return df


# --------------------------
# Cleaning
# --------------------------
_MEDIA_TOKENS = {
    "<media omitted>", "media omitted",
    "sticker omitted", "‎sticker omitted",
    "image omitted", "video omitted",
}

_SYSTEM_KEYWORDS = [
    "end-to-end encrypted",
    "messages and calls are end-to-end encrypted",
    "security code changed",
    "changed this group's icon",
    "changed the group description",
    "changed the subject",
    "joined using this group's invite link",
    "changed their phone number",
]


def filter_media(df: pd.DataFrame) -> pd.DataFrame:
    msg = df["message"].str.strip().str.lower()
    return df[~msg.isin(_MEDIA_TOKENS)].copy()


def filter_system(df: pd.DataFrame) -> pd.DataFrame:
    msg = df["message"].str.lower()
    keep = pd.Series(True, index=df.index)
    for kw in _SYSTEM_KEYWORDS:
        keep &= ~msg.str.contains(kw, na=False)
    return df[keep].copy()


# --------------------------
# Analytics
# --------------------------
def monthly_counts(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["month_start"] = d["datetime"].dt.to_period("M").dt.to_timestamp()
    out = d.groupby(["month_start", "sender"]).size().reset_index(name="message_count")
    return out.sort_values("month_start")


def daily_counts(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["date"] = d["datetime"].dt.date
    out = d.groupby(["date", "sender"]).size().reset_index(name="message_count")
    return out.sort_values("date")


def total_messages(df: pd.DataFrame) -> pd.DataFrame:
    out = df.groupby("sender").size().reset_index(name="total_messages")
    return out.sort_values("total_messages", ascending=False)


def total_words(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["word_count"] = d["message"].apply(lambda x: len(str(x).split()))
    out = d.groupby("sender")["word_count"].sum().reset_index(name="total_words")
    return out.sort_values("total_words", ascending=False)


def avg_words_per_message(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["word_count"] = d["message"].apply(lambda x: len(str(x).split()))
    out = d.groupby("sender")["word_count"].mean().round(2).reset_index(name="avg_words_per_message")
    return out.sort_values("avg_words_per_message", ascending=False)


def talk_percentage(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby("sender").size()
    total = counts.sum()
    pct = (counts / total * 100).round(2)
    return pct.reset_index(name="percentage")


def weekday_counts(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["weekday"] = d["datetime"].dt.day_name()
    out = d.groupby(["weekday", "sender"]).size().reset_index(name="message_count")
    return out


def reply_time_avg_minutes(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values("datetime").reset_index(drop=True)
    rows = []
    for i in range(1, len(d)):
        if d.loc[i, "sender"] != d.loc[i - 1, "sender"]:
            delta_min = (d.loc[i, "datetime"] - d.loc[i - 1, "datetime"]).total_seconds() / 60.0
            rows.append({"sender": d.loc[i, "sender"], "reply_time_minutes": round(delta_min, 2)})
    rep = pd.DataFrame(rows)
    if rep.empty:
        return rep
    out = rep.groupby("sender")["reply_time_minutes"].mean().round(2).reset_index()
    return out.sort_values("reply_time_minutes")


def longest_active_streak_days(df: pd.DataFrame) -> int:
    d = df.copy()
    d["date"] = d["datetime"].dt.date
    days = sorted(d["date"].unique())
    if not days:
        return 0
    max_streak = 1
    streak = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1
    return max_streak


def longest_silence(df: pd.DataFrame):
    d = df.sort_values("datetime").reset_index(drop=True)
    if len(d) < 2:
        return None
    max_gap = -1
    start_dt = None
    end_dt = None
    for i in range(1, len(d)):
        gap = (d.loc[i, "datetime"] - d.loc[i - 1, "datetime"]).total_seconds()
        if gap > max_gap:
            max_gap = gap
            start_dt = d.loc[i - 1, "datetime"]
            end_dt = d.loc[i, "datetime"]
    return {"gap_hours": round(max_gap / 3600, 2), "from": start_dt, "to": end_dt}


def fastest_reply(df: pd.DataFrame):
    d = df.sort_values("datetime").reset_index(drop=True)
    fastest = None
    best = None
    for i in range(1, len(d)):
        if d.loc[i, "sender"] != d.loc[i - 1, "sender"]:
            gap = (d.loc[i, "datetime"] - d.loc[i - 1, "datetime"]).total_seconds()
            if best is None or gap < best:
                best = gap
                fastest = {
                    "responder": d.loc[i, "sender"],
                    "reply_time_seconds": round(gap, 2),
                    "reply_time_minutes": round(gap / 60, 2),
                    "time": d.loc[i, "datetime"],
                }
    return fastest


def seen_ignored_counts(df: pd.DataFrame, threshold_minutes: int = 120) -> pd.DataFrame:
    d = df.sort_values("datetime").reset_index(drop=True)
    ignored = {s: 0 for s in d["sender"].unique()}

    for i in range(len(d) - 1):
        s1 = d.loc[i, "sender"]
        s2 = d.loc[i + 1, "sender"]
        delta_min = (d.loc[i + 1, "datetime"] - d.loc[i, "datetime"]).total_seconds() / 60.0

        if s1 != s2:
            if delta_min > threshold_minutes:
                ignored[s1] += 1
        else:
            ignored[s1] += 1

    out = pd.DataFrame(list(ignored.items()), columns=["sender", "ignored_count"])
    return out.sort_values("ignored_count", ascending=False)


def activity_heatmap_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["hour"] = d["datetime"].dt.hour
    d["weekday"] = d["datetime"].dt.day_name()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    d["weekday"] = pd.Categorical(d["weekday"], categories=weekday_order, ordered=True)

    return d.groupby(["weekday", "hour"]).size().reset_index(name="count")


def monthly_growth_rate(df: pd.DataFrame) -> pd.DataFrame:
    m = monthly_counts(df)
    total = m.groupby("month_start")["message_count"].sum().reset_index()
    total["growth_rate_%"] = (total["message_count"].pct_change() * 100).round(2)
    return total


def love_index(df: pd.DataFrame) -> pd.DataFrame:
    love_keywords = ["love", "miss you", "i miss you", "❤️", "❤", "😘", "😍", "baby", "jaan", "darling"]
    results = {}
    for sender in df["sender"].unique():
        msgs = df[df["sender"] == sender]["message"].str.lower()
        score = 0
        for kw in love_keywords:
            score += msgs.str.contains(re.escape(kw.lower()), na=False).sum()
        results[sender] = int(score)
    out = pd.DataFrame(list(results.items()), columns=["sender", "love_score"])
    return out.sort_values("love_score", ascending=False)


def emoji_top(df: pd.DataFrame, top_n: int = 15):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "]+",
        flags=re.UNICODE,
    )
    result = {}
    for sender in df["sender"].unique():
        text = " ".join(df[df["sender"] == sender]["message"].astype(str))
        emojis = "".join(emoji_pattern.findall(text))
        counts = {}
        for e in emojis:
            counts[e] = counts.get(e, 0) + 1
        top = dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n])
        result[sender] = top
    return result