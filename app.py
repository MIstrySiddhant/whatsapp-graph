import re
import pandas as pd
import streamlit as st
import plotly.express as px


def normalize_line(s: str) -> str:
    """
    WhatsApp exports sometimes contain invisible direction marks (common on iPhone),
    and weird spaces. These break regex matching, so we remove/normalize them.
    """
    return (
        s.replace("\ufeff", "")   # BOM
         .replace("\u200e", "")   # LRM (often shown as "‎")
         .replace("\u200f", "")   # RLM
         .replace("\u061c", "")   # Arabic letter mark
         .replace("\u202f", " ")  # narrow no-break space
         .replace("\u00a0", " ")  # no-break space
         .strip()
    )


def parse_whatsapp_text(text: str) -> pd.DataFrame:
    lines = [normalize_line(x) for x in text.splitlines() if normalize_line(x)]

    # Pattern A: iPhone / bracket style
    # [02/02/24, 9:29:43 PM] Name: Message
    # [02/02/24, 9:29 PM] Name: Message
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

    # Pattern B: Android / dash style
    # 13/10/23, 2:08 pm - Name: Message
    # 13/10/23, 14:08 - Name: Message
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

    def start_new_message(date_str, time_str, ampm, rest):
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
            current = start_new_message(
                m.group("date"),
                m.group("time"),
                m.group("ampm"),
                m.group("rest"),
            )
        else:
            # multi-line continuation
            if current is not None:
                current["message"] += "\n" + line

    if current is not None:
        records.append(current)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Build datetime strings
    dt_str = df["raw_date"].astype(str) + " " + df["raw_time"].astype(str)
    if df["ampm"].notna().any():
        dt_str = dt_str + " " + df["ampm"].fillna("")

    # Auto-detect day-first vs month-first
    dt_dayfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=False)
    df["datetime"] = dt_dayfirst if dt_dayfirst.notna().sum() >= dt_monthfirst.notna().sum() else dt_monthfirst

    df = df.dropna(subset=["datetime"]).copy()

    # Keep rows that look like user messages (sender exists)
    df = df[df["sender"].notna()].copy()

    return df


# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="WhatsApp Monthly Graph", layout="wide")
st.title("WhatsApp Message Graph (Month-Year)")

st.sidebar.header("Upload Chat File")
uploaded = st.sidebar.file_uploader("Upload WhatsApp .txt file", type=["txt"])

if uploaded is None:
    st.info("Upload a WhatsApp exported chat .txt file from the left sidebar to see the graph.")
    st.stop()

raw = uploaded.getvalue()

# Decode
try:
    text = raw.decode("utf-8-sig")
except UnicodeDecodeError:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-16")

df = parse_whatsapp_text(text)

if df.empty:
    st.error("No valid WhatsApp messages found in this file. Make sure it is a WhatsApp exported chat text file.")
    st.stop()

st.sidebar.header("Filters")

hide_media = st.sidebar.checkbox("Hide media/stickers omitted", value=True)
if hide_media:
    df = df[~df["message"].str.strip().isin([
        "<Media omitted>",
        "sticker omitted",
        "‎sticker omitted",
        "image omitted",
        "video omitted"
    ])]

hide_system = st.sidebar.checkbox(
    "Hide WhatsApp system notices (encrypted, security code, etc.)",
    value=True
)

if hide_system:
    system_keywords = [
        "end-to-end encrypted",
        "security code changed",
        "changed this group's icon",
        "changed the group description",
        "changed the subject",
        "added",
        "removed",
        "left",
        "joined using this group's invite link",
        "changed their phone number",
    ]

    # Create a boolean mask that keeps only real messages
    mask = pd.Series(True, index=df.index)

    for kw in system_keywords:
        mask &= ~df["message"].str.lower().str.contains(kw.lower(), na=False)

    df = df[mask]

senders = sorted(df["sender"].unique().tolist())
selected_senders = st.sidebar.multiselect("Choose people", senders, default=senders)
df = df[df["sender"].isin(selected_senders)]

if df.empty:
    st.warning("No messages left after filtering.")
    st.stop()

# Group by month-year
df["month_start"] = df["datetime"].dt.to_period("M").dt.to_timestamp()

monthly = (
    df.groupby(["month_start", "sender"])
      .size()
      .reset_index(name="message_count")
      .sort_values("month_start")
)

st.subheader("Monthly Message Count")

fig = px.line(
    monthly,
    x="month_start",
    y="message_count",
    color="sender",
    markers=True,
    labels={"month_start": "Month-Year", "message_count": "Message Count"},
)

fig.update_traces(line_shape="spline")
fig.update_xaxes(dtick="M1", tickformat="%m-%y")  # ✅ 1 month gap only

st.plotly_chart(fig, use_container_width=True)

# Monthly table
st.subheader("Monthly counts table")
monthly["month_label"] = monthly["month_start"].dt.strftime("%m-%y")
table = monthly.pivot_table(index="month_label", columns="sender", values="message_count", fill_value=0)
st.dataframe(table, use_container_width=True)

# Total per person
st.subheader("Total message count per person")
total_counts = df.groupby("sender").size().reset_index(name="total_messages")
total_counts = total_counts.sort_values("total_messages", ascending=False)
st.dataframe(total_counts, use_container_width=True)

# ---------------- Word Count Per Person ----------------

st.subheader("Total word count per person")

# Remove extra spaces
df["clean_message"] = df["message"].str.strip()

# Count words per message
df["word_count"] = df["clean_message"].apply(
    lambda x: len(x.split()) if isinstance(x, str) else 0
)

# Group by sender
word_counts = (
    df.groupby("sender")["word_count"]
      .sum()
      .reset_index()
      .sort_values("word_count", ascending=False)
)

st.dataframe(word_counts, use_container_width=True)
# Debug section (helps verify parsing)
with st.expander("Debug: Show parsed sample (to verify correct parsing)"):
    st.write("Parsed messages:", len(df))
    st.dataframe(df[["datetime", "sender", "message"]].sort_values("datetime").head(30), use_container_width=True)