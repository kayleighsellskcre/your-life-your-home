"""The three public pages: For Homeowners, For Agents and For Lenders. Each says in a few plain sentences what that group gets
and has one button that goes straight to the right sign-up."""
from flask import render_template

PAGES = {
    "for_homeowners": {
        "label": "For homeowners",
        "title": "Your home, beautifully organized",
        "intro": "A calm place to keep track of the house you love.",
        "points": [
            "See what your home is worth and how much equity you have built.",
            "Know the next thing your house needs, before it turns into a problem.",
            "Keep your home details and documents in one safe place.",
            "Reach your agent and your lender in one tap.",
        ],
        "note": "Always free for homeowners.",
        "button": "Create my free account",
        "role": "homeowner",
    },
    "for_agents": {
        "label": "For agents",
        "title": "Stay close to every client",
        "intro": "Be the agent your clients think of first, without the extra work.",
        "points": [
            "Invite a client in a minute and set up their home for them.",
            "See who is due for a follow-up, and send a friendly update with a few taps.",
            "Your name and brokerage show on every client's home dashboard.",
            "Planner, CRM, transactions and marketing tools are all in one place.",
        ],
        "note": "Start free. Upgrade any time, billed securely through Stripe.",
        "button": "Start my account",
        "role": "agent",
    },
    "for_lenders": {
        "label": "For lenders",
        "title": "Keep in touch long after closing",
        "intro": "Stay helpful to the homeowners you served, and be there when their next move comes.",
        "points": [
            "See which clients could save with a refinance, or have equity to use.",
            "Homeowners can share a payment or refinance scenario with you, privately.",
            "Your name shows on every client's home dashboard.",
            "Send a warm, useful update to your clients with a few taps.",
        ],
        "note": "Setting up takes about two minutes.",
        "button": "Start my account",
        "role": "lender",
    },
}


def _make(key):
    def view():
        return render_template("main/for_group.html", page=PAGES[key])
    view.__name__ = key
    return view


def init_app(app):
    for key, paths in (("for_homeowners", ("/homeowners", "/for-homeowners")), ("for_agents", ("/agents", "/for-agents")),
                       ("for_lenders", ("/lenders", "/for-lenders"))):
        view = _make(key)
        app.add_url_rule(paths[0], endpoint=key, view_func=view)
        for alt in paths[1:]:
            app.add_url_rule(alt, endpoint=key + "_alt", view_func=view)
