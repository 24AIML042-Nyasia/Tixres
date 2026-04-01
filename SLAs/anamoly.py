def zScoreSLA(az : float):
    """
    az - absolute Z score
    """
    if az >= 4:
        return "P2"
    elif az >= 3:
        return "P3"
    elif az >= 2:
        return "P3"
    elif az >= 1.5:
        return "P4"
    else:
        return None