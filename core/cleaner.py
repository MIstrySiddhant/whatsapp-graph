import pandas as pd


MEDIA_TOKENS = {
    "<media omitted>",
    "sticker omitted",
    "‎sticker omitted",
    "image omitted",
    "video omitted",
}

SYSTEM_KEYWORDS = [
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
    msg = df["message"].astype(str).str.strip().str.lower()
    return df[~msg.isin(MEDIA_TOKENS)].copy()


def filter_system(df: pd.DataFrame) -> pd.DataFrame:
    msg = df["message"].astype(str).str.lower()
    keep = pd.Series(True, index=df.index)
    for kw in SYSTEM_KEYWORDS:
        keep &= ~msg.str.contains(kw, na=False)
    return df[keep].copy()