import pandas as pd
import plotly.express as px


def line_monthly(monthly_df: pd.DataFrame):
    fig = px.line(
        monthly_df,
        x="month_start",
        y="message_count",
        color="sender",
        markers=True,
        labels={"month_start": "Month-Year", "message_count": "Message Count"},
    )
    fig.update_traces(line_shape="spline")
    fig.update_xaxes(dtick="M1", tickformat="%m-%y")  # 1 month gap
    return fig


def bar_weekday(weekday_df: pd.DataFrame):
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_df = weekday_df.copy()
    weekday_df["weekday"] = pd.Categorical(weekday_df["weekday"], categories=weekday_order, ordered=True)
    weekday_df = weekday_df.sort_values("weekday")

    fig = px.bar(
        weekday_df,
        x="weekday",
        y="message_count",
        color="sender",
        barmode="group",
        category_orders={"weekday": weekday_order},
        labels={"weekday": "Day of Week", "message_count": "Messages"},
    )
    return fig


def pie_talk_percentage(pct_df: pd.DataFrame):
    fig = px.pie(pct_df, names="sender", values="percentage", title="Talk Percentage")
    return fig