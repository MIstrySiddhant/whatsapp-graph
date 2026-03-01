import pandas as pd
import numpy as np
import re


# 1️⃣ Daily message count
def daily_message_count(df):
    df["date"] = df["datetime"].dt.date
    return df.groupby(["date", "sender"]).size().reset_index(name="message_count")


# 3️⃣ Talk percentage
def talk_percentage(df):
    counts = df.groupby("sender").size()
    total = counts.sum()
    percentage = (counts / total * 100).round(2)
    return percentage.reset_index(name="percentage")


# 4️⃣ Average words per message
def average_words_per_message(df):
    df["word_count"] = df["message"].apply(lambda x: len(str(x).split()))
    result = df.groupby("sender")["word_count"].mean().round(2)
    return result.reset_index(name="avg_words_per_message")


# 6️⃣ Most active day of week
def most_active_day(df):
    df["weekday"] = df["datetime"].dt.day_name()
    return df.groupby(["weekday", "sender"]).size().reset_index(name="message_count")


# 8️⃣ Reply time analysis
def reply_time_analysis(df):
    df = df.sort_values("datetime").reset_index(drop=True)

    reply_times = []

    for i in range(1, len(df)):
        if df.loc[i, "sender"] != df.loc[i-1, "sender"]:
            delta = (df.loc[i, "datetime"] - df.loc[i-1, "datetime"]).total_seconds()
            reply_times.append({
                "sender": df.loc[i, "sender"],
                "reply_time_minutes": round(delta / 60, 2)
            })

    reply_df = pd.DataFrame(reply_times)
    if reply_df.empty:
        return reply_df

    return reply_df.groupby("sender")["reply_time_minutes"].mean().round(2).reset_index()


# 9️⃣ Conversation streaks
def conversation_streaks(df):
    df = df.sort_values("datetime")
    df["date"] = df["datetime"].dt.date

    unique_days = sorted(df["date"].unique())

    max_streak = 0
    current_streak = 1

    for i in range(1, len(unique_days)):
        if (unique_days[i] - unique_days[i-1]).days == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1

    return max_streak


# 1️⃣2️⃣ Emoji analysis
def emoji_analysis(df):
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"
                               u"\U0001F300-\U0001F5FF"
                               u"\U0001F680-\U0001F6FF"
                               u"\U0001F1E0-\U0001F1FF"
                               "]+", flags=re.UNICODE)

    df["emojis"] = df["message"].apply(lambda x: ''.join(emoji_pattern.findall(str(x))))

    emoji_counts = {}

    for sender in df["sender"].unique():
        sender_emojis = ''.join(df[df["sender"] == sender]["emojis"])
        counts = {}
        for e in sender_emojis:
            counts[e] = counts.get(e, 0) + 1
        emoji_counts[sender] = counts

    return emoji_counts