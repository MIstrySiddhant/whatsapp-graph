import re
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px


def normalize_line(s: str) -> str:
    """
    WhatsApp exports sometimes include weird invisible spaces (narrow no-break space etc.).
    This normalizes common ones so regex matching works better.
    """
    return (
        s.replace("\u202f", " ")  # narrow no-break space
         .replace("\u00a0", " ")  # no-break space
         .replace("\ufeff", "")   # BOM
         .strip()
    )


def parse_whatsapp_file(file_path: str) -> pd.DataFrame:
    path = Path(file_path)

    # Read file with common encodings
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-16")

    lines = [normalize_line(x) for x in text.splitlines()]

    # -------- Pattern A: Bracket style --------
    # [02/02/24, 9:29:43 PM] Name: Message
    bracket_pattern = re.compile(
        r"""^\[
        (?P<date>\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}),
        \s*
        (?P<time>\d{1,2}:\d{2}(?::\d{2})?)
        \s*(?P<ampm>[APap][Mm])?
        \]\s*
        (?P<rest>.*)
        $""",
        re.VERBOSE,
    )

    # -------- Pattern B: Dash style --------
    # 13/10/23, 2:08 pm - Name: Message
    # 13/10/23, 14:08 - Name: Message
    dash_pattern = re.compile(
        r"""^
        (?P<date>\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})
        [,\s]+
        (?P<time>\d{1,2}:\d{2}(?::\d{2})?)
        \s*(?P<ampm>[APap][Mm])?
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
            # Save previous
            if current is not None:
                records.append(current)

            m = m1 if m1 else m2
            date_str = m.group("date")
            time_str = m.group("time")
            ampm = m.group("ampm")
            rest = m.group("rest")

            current = start_new_message(date_str, time_str, ampm, rest)
        else:
            # continuation line (multi-line message)
            if current is not None:
                current["message"] += "\n" + line

    if current is not None:
        records.append(current)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Build datetime string like "02/02/24 9:29:43 PM"
    dt_str = df["raw_date"].astype(str) + " " + df["raw_time"].astype(str)
    if df["ampm"].notna().any():
        dt_str = dt_str + " " + df["ampm"].fillna("")

    # Try parsing with dayfirst True/False (WhatsApp exports differ by region)
    dt_dayfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=False)

    df["datetime"] = dt_dayfirst if dt_dayfirst.notna().sum() >= dt_monthfirst.notna().sum() else dt_monthfirst
    df = df.dropna(subset=["datetime"]).copy()

    # Remove system messages (no sender)
    df = df[df["sender"].notna()].copy()

    return df


# ---------------- Streamlit App ----------------
st.set_page_config(page_title="WhatsApp Monthly Graph", layout="wide")
st.title("WhatsApp Message Graph (Month-Year)")

txt_files = sorted([p.name for p in Path(".").glob("*.txt")])

if not txt_files:
    st.error("No .txt files found. Put your WhatsApp exported .txt files in the same folder as app.py")
    st.stop()

st.sidebar.header("Select Chat File")
selected_file = st.sidebar.selectbox("Choose a chat file", txt_files)

df = parse_whatsapp_file(selected_file)

if df.empty:
    st.error(
        f"No valid WhatsApp messages found in '{selected_file}'.\n"
        "Make sure it is a WhatsApp exported chat text file."
    )
    st.stop()

st.sidebar.header("Filters")

hide_media = st.sidebar.checkbox("Hide '<Media omitted>' / 'sticker omitted'", value=True)
if hide_media:
    df = df[~df["message"].str.strip().isin(["<Media omitted>", "sticker omitted", "‎sticker omitted"])]

senders = sorted(df["sender"].unique().tolist())
selected_senders = st.sidebar.multiselect("Choose people", senders, default=senders)
df = df[df["sender"].isin(selected_senders)]

if df.empty:
    st.warning("No messages left after filtering. Select more people or disable filters.")
    st.stop()

# Group by month and sender
df["month_start"] = df["datetime"].dt.to_period("M").dt.to_timestamp()

monthly = (
    df.groupby(["month_start", "sender"])
      .size()
      .reset_index(name="message_count")
      .sort_values("month_start")
)

st.subheader(f"Graph for: {selected_file}")

fig = px.line(
    monthly,
    x="month_start",
    y="message_count",
    color="sender",
    markers=True,
    labels={"month_start": "Month-Year", "message_count": "Message Count"},
)

# Smooth curve like your sketch
fig.update_traces(line_shape="spline")

# ✅ Force 1-month gap on X-axis
fig.update_xaxes(dtick="M1", tickformat="%m-%y")

st.plotly_chart(fig, use_container_width=True)

# Monthly table
st.subheader("Monthly counts table")
monthly["month_label"] = monthly["month_start"].dt.strftime("%m-%y")
table = monthly.pivot_table(index="month_label", columns="sender", values="message_count", fill_value=0)
st.dataframe(table, use_container_width=True)

# Total message count per person
st.subheader("Total message count per person")
total_counts = df.groupby("sender").size().reset_index(name="total_messages")
total_counts = total_counts.sort_values("total_messages", ascending=False)
st.dataframe(total_counts, use_container_width=True)