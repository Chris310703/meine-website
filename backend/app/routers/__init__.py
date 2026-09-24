from . import calendar, core, fitness, garmin, recovery, sleep, study, timetable

ROUTERS = [
    core.router,
    garmin.router,
    fitness.router,
    sleep.router,
    recovery.router,
    calendar.router,
    timetable.router,
    study.router,
]
