from helpers.config_handler import load_setting, set_setting

def set_bot_enabled(enabled: bool):
    print("Setting bot enabled to: ", enabled)
    set_setting("enabled", enabled)
    return {"success": True}

def get_bot_enabled():
    return load_setting("enabled")

def set_lots_size(lots_size):
    print("Setting lots size to: ", lots_size)
    set_setting("lots_size", lots_size)
    return {"success": True}

def set_session(session):
    print("Setting session to: ", session)
    set_setting("session", session)
    return {"success": True}

def set_confidence_threshold(confidence_threshold):
    print("Setting confidence threshold to: ", confidence_threshold)
    set_setting("confidence_threshold", confidence_threshold)
    return {"success": True}

def set_paper(paper):
    print("Setting paper to: ", paper)
    set_setting("paper", paper)
    return {"success": True}