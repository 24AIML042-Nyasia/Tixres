from server_db.models import one_minutes_metric , one_hour_metric, ten_minutes_metric


def print_rollup_rows():

    print("\nOne Min Roll Up")
    for row in one_minutes_metric():
        print(dict(row))

    print("\nTen Min Roll Up")
    for row in ten_minutes_metric():
        print(dict(row))

    print("\nOne Hour Roll Up")
    for row in one_hour_metric():
        print(dict(row))