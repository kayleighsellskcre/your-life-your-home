"""Shared loader for the route files that were split out of app.py (lender_routes.py, agent_routes.py, ...).

Each of those files uses `route(...)` where app.py used `@app.route(...)`. install(globals()) is then called from app.py,
which registers every view with its original endpoint name and runs it in app.py's namespace, so helpers such as
get_current_user or send_reminder_email are looked up there exactly as before (including anything a test swaps out).
"""
import types


class Registry:
    def __init__(self):
        self._routes = []

    def route(self, rule, **options):
        def deco(fn):
            self._routes.append((rule, options, fn))
            return fn
        return deco

    def install(self, ns):
        app = ns["app"]
        for rule, options, fn in self._routes:
            view = types.FunctionType(fn.__code__, ns, fn.__name__, fn.__defaults__, fn.__closure__)
            view.__kwdefaults__ = fn.__kwdefaults__
            view.__doc__ = fn.__doc__
            ns[fn.__name__] = view
            app.add_url_rule(rule, endpoint=fn.__name__, view_func=view, **options)
