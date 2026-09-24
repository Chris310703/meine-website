from . import calendar, core, fitness, garmin, habits, journal, nutrition, recovery, sleep, study, timetable, todos

ROUTERS = [
    core.router,
    garmin.router,
    fitness.router,
    sleep.router,
    recovery.router,
    calendar.router,
    timetable.router,
    study.router,
    nutrition.router,
    habits.router,
    todos.router,
    journal.router,
]
