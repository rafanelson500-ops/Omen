from datetime import datetime, timedelta

def get_sleep_time(current_time):
    next_time = current_time.replace(second=0, microsecond=0) + timedelta(minutes=5-current_time.minute%5)
    return max(0, (next_time - current_time).total_seconds())

def crop_data(df, session):
    if session == "ALL":
        return df
    elif session == "RTH":
        return df.between_time("14:30", "22:00")
    elif session == "ETH":
        return df.between_time("22:55", "14:25")