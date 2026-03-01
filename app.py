import streamlit as st
import pandas as pd
import plotly.express as px

import core


st.set_page_config(page_title="WhatsApp Analytics", layout="wide")
st.title("WhatsApp Analytics Dashboard")

# Upload
st.sidebar.header("Upload Chat File")
uploaded = st.sidebar.file_uploader("Upload WhatsApp .txt file", type=["txt"])

if uploaded is None:
    st.info("Upload a WhatsApp exported .txt file from the left sidebar.")
    st.stop()

text = core.decode_bytes(uploaded.getvalue())
df = core.parse_whatsapp_text(text)

if df.empty:
    st.error("No valid WhatsApp messages found in this file.")
    st.stop()

# Filters
st.sidebar.header("Filters")
hide_media = st.sidebar.checkbox("Hide media/stickers omitted", value=True)
hide_system = st.sidebar.checkbox("Hide WhatsApp system notices", value=True)

if hide_media:
    df = core.filter_media(df)
if hide_system:
    df = core.filter_system(df)

senders = sorted(df["sender"].unique().tolist())
selected_senders = st.sidebar.multiselect("Choose people", senders, default=senders)
df = df[df["sender"].isin(selected_senders)].copy()

if df.empty:
    st.warning("No messages left after filtering.")
    st.stop()

# Timeline slider
st.sidebar.header("Time Filter")
min_date = df["datetime"].min().date()
max_date = df["datetime"].max().date()

date_range = st.sidebar.date_input(
    "Select Date Range",
    [min_date, max_date],
    min_value=min_date,
    max_value=max_date
)

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
    df = df[
        (df["datetime"].dt.date >= start_date) &
        (df["datetime"].dt.date <= end_date)
    ].copy()

if df.empty:
    st.warning("No messages in this date range.")
    st.stop()

# ---------- Monthly graph ----------
st.subheader("Monthly Message Count (Month-Year)")
monthly = core.monthly_counts(df)

fig_month = px.line(
    monthly, x="month_start", y="message_count", color="sender", markers=True,
    labels={"month_start": "Month-Year", "message_count": "Message Count"}
)
fig_month.update_traces(line_shape="spline")
fig_month.update_xaxes(dtick="M1", tickformat="%m-%y")
st.plotly_chart(fig_month, use_container_width=True)

with st.expander("Monthly counts table"):
    monthly["month_label"] = monthly["month_start"].dt.strftime("%m-%y")
    table = monthly.pivot_table(index="month_label", columns="sender", values="message_count", fill_value=0)
    st.dataframe(table, use_container_width=True)

# ---------- Daily view ----------
st.subheader("Daily Message Count")
daily = core.daily_counts(df)
fig_day = px.line(daily, x="date", y="message_count", color="sender", labels={"date": "Date", "message_count": "Messages"})
st.plotly_chart(fig_day, use_container_width=True)

# ---------- Summary ----------
st.subheader("Summary")
c1, c2, c3 = st.columns(3)
with c1:
    st.write("**Total Messages**")
    st.dataframe(core.total_messages(df), use_container_width=True)
with c2:
    st.write("**Total Words**")
    st.dataframe(core.total_words(df), use_container_width=True)
with c3:
    st.write("**Avg Words / Message**")
    st.dataframe(core.avg_words_per_message(df), use_container_width=True)

# ---------- Talk percentage ----------
st.subheader("Talk Percentage (%)")
pct = core.talk_percentage(df)
st.plotly_chart(px.pie(pct, names="sender", values="percentage"), use_container_width=True)
st.dataframe(pct, use_container_width=True)

# ---------- Weekday bar chart ----------
st.subheader("Most Active Day of Week")
weekday_df = core.weekday_counts(df)
weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
weekday_df["weekday"] = pd.Categorical(weekday_df["weekday"], categories=weekday_order, ordered=True)
weekday_df = weekday_df.sort_values("weekday")
st.plotly_chart(px.bar(weekday_df, x="weekday", y="message_count", color="sender", barmode="group"), use_container_width=True)

# ---------- Reply time + fastest reply ----------
st.subheader("Reply Time Insights")
reply_avg = core.reply_time_avg_minutes(df)
if reply_avg.empty:
    st.write("Not enough back-and-forth messages to calculate reply times.")
else:
    st.write("**Average Reply Time (minutes)**")
    st.dataframe(reply_avg, use_container_width=True)

st.write("**Fastest Reply Ever**")
fastest = core.fastest_reply(df)
st.json(fastest if fastest else {"note": "Not enough back-and-forth to calculate."})

# ---------- Streak + silence ----------
st.subheader("Streak & Silence")
st.write(f"**Longest Active Streak:** {core.longest_active_streak_days(df)} days")

st.write("**Longest Silent Period**")
silence = core.longest_silence(df)
st.json(silence if silence else {"note": "Not enough messages to calculate."})

# ---------- Seen / ignored ----------
st.subheader("Who Leaves Who on 'Seen' More (Approximation)")
threshold = st.slider("Reply threshold (minutes)", min_value=10, max_value=720, value=120, step=10)
st.dataframe(core.seen_ignored_counts(df, threshold_minutes=threshold), use_container_width=True)

# ---------- Heatmap ----------
st.subheader("Activity Heatmap (Hour vs Day)")
heat = core.activity_heatmap_table(df)
heat_pivot = heat.pivot_table(index="weekday", columns="hour", values="count", fill_value=0)
st.plotly_chart(px.imshow(heat_pivot, aspect="auto", labels=dict(x="Hour", y="Day", color="Messages")), use_container_width=True)

# ---------- Monthly growth ----------
st.subheader("Monthly Growth Rate (Overall)")
growth = core.monthly_growth_rate(df)
growth["month_label"] = growth["month_start"].dt.strftime("%m-%y")
st.plotly_chart(px.bar(growth, x="month_label", y="growth_rate_%", labels={"month_label": "Month", "growth_rate_%": "Growth %"}), use_container_width=True)
st.dataframe(growth, use_container_width=True)

# ---------- Love Index ----------
st.subheader("Love Index 💖")
st.dataframe(core.love_index(df), use_container_width=True)

# ---------- Emoji analysis ----------
st.subheader("Top Emojis per Person")
emoji_data = core.emoji_top(df, top_n=15)
for sender, counts in emoji_data.items():
    st.write(f"**{sender}**")
    if not counts:
        st.write("No emojis found.")
    else:
        emoji_df = pd.DataFrame(list(counts.items()), columns=["emoji", "count"])
        st.dataframe(emoji_df, use_container_width=True)

# Debug
with st.expander("Debug: Parsed preview"):
    st.write("Rows:", len(df))
    st.dataframe(df[["datetime", "sender", "message"]].sort_values("datetime").head(50), use_container_width=True)