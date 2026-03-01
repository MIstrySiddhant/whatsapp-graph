import re
import pandas as pd
import streamlit as st
import plotly.express as px


def normalize_line(s: str) -> str:
    return (
        s.replace("\u202f", " ")
         .replace("\u00a0", " ")
         .replace("\ufeff", "")
         .strip()
    )


def parse_whatsapp_text(text: str) -> pd.DataFrame:
    lines = [normalize_line(x) for x in text.splitlines()]

    # Pattern A: [02/02/24, 9:29:43 PM] Name: Message
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

    # Pattern B: 13/10/23, 2:08 pm - Name: Message
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
            if current is not None:
                records.append(current)

            m = m1 if m1 else m2
            current = start_new_message(m.group("date"), m.group("time"), m.group("ampm"), m.group("rest"))
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

    # dayfirst vs monthfirst auto-detect
    dt_dayfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
    dt_monthfirst = pd.to_datetime(dt_str, errors="coerce", dayfirst=False)
    df["datetime"] = dt_dayfirst if dt_dayfirst.notna().sum() >= dt_monthfirst.notna().sum() else dt_monthfirst

    df = df.dropna(subset=["datetime"]).copy()
    df = df[df["sender"].notna()].copy()  # remove system lines

    return df


# -------- Streamlit UI --------
st.set_page_config(page_title="WhatsApp Monthly Graph", layout="wide")
st.title("WhatsApp Message Graph (Month-Year)")

st.sidebar.header("Upload Chat File")
uploaded = st.sidebar.file_uploader("Upload WhatsApp .txt file", type=["txt"])

if uploaded is None:
    st.info("Upload a WhatsApp exported chat .txt file from the left sidebar to see the graph.")
    st.stop()

raw = uploaded.getvalue()

# Try decoding
try:
    text = raw.decode("utf-8")
except UnicodeDecodeError:
    text = raw.decode("utf-16")

df = parse_whatsapp_text(text)

if df.empty:
    st.error("No valid WhatsApp messages found in this file. Make sure it is a WhatsApp exported chat text file.")
    st.stop()

st.sidebar.header("Filters")

hide_media = st.sidebar.checkbox("Hide '<Media omitted>' / stickers", value=True)
if hide_media:
    df = df[~df["message"].str.strip().isin(["<Media omitted>", "sticker omitted", "‎sticker omitted"])]

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
fig.update_xaxes(dtick="M1", tickformat="%m-%y")

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