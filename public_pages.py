"""The three public pages: For Homeowners, For Agents and For Lenders. Each says in a few plain sentences what that group gets
and has one button that goes straight to the right sign-up."""
from flask import render_template, url_for

LEGAL = {'privacy': ('Privacy Policy', 'How we handle your information, in plain words.', [('What we collect', ['Your name, email and password when you create an account.', 'The home details you choose to add, like your address, move-in date, home value and loan numbers, plus any documents or photos you upload.', 'Messages you send to your agent or lender through the site.']), ('How we use it', ['To run your account and show you your own home dashboard.', 'To connect you with your agent and lender, so they can help you.', 'To send helpful emails, like reminders and messages from your team. You can ask us to stop at any time.']), ('Who can see it', ['Your agent and lender can see what you add to your home details, and the messages you send them.', 'Payment and refinance numbers you pick in Ask my lender are shared only with your lender, and only the numbers you tick.', 'We never sell your information, and we do not share it with advertisers.']), ('Who helps us run the site', ['We use trusted services to host the site, send email and take payments. Card payments are handled securely by Stripe, and we never see or store your full card number.']), ('Questions', ['You can write to us at kayleighsellskcre@gmail.com.']), ('Your choices', ['You can update your details in Settings at any time.', 'You can ask us to delete your account and the information in it.', 'If we ever change this policy in a way that matters, we will tell you.'])]), 'terms': ('Terms of Use', 'The simple ground rules for using Your Life, Your Home.', [('Using the site', ['You must be 18 or older and give us true information when you sign up.', 'Keep your password private. You are responsible for what happens in your account.', "Please be kind and honest. We can close accounts that misuse the site or other people's information."]), ('Home values and numbers', ['Value, equity and payment numbers are estimates to help you plan. They are not an appraisal, a loan offer or financial or legal advice.', 'Talk to your agent or lender before you make a big decision.']), ('Agents and lenders', ['If you are an agent or lender, you are responsible for following the laws and licensing rules that apply to you, including how you contact clients.', 'Paid plans are billed monthly through Stripe. You can manage or cancel your plan from Plan & Billing.']), ('Your content', ['What you add is yours. You let us store it and show it to the people you connect with so the site can work.', 'We work hard to keep the site running and your information safe, but we cannot promise it will always be available or error free.']), ('Questions', ['You can write to us at kayleighsellskcre@gmail.com.']), ('Changes', ['We may update these terms as the site grows. If the change matters, we will let you know.'])])}

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
        "title": "Be the agent clients think of first",
        "intro": "Stay close to every client, without the extra work.",
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
        "title": "Be there for their next move",
        "intro": "Keep in touch long after closing.",
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


def _legal(key):
    def view():
        title, intro, sections = LEGAL[key]
        return render_template("main/legal.html", title=title, intro=intro, sections=sections)
    view.__name__ = key
    return view


def pricing():
    try:
        from stripe_payments import live_tiers
        tiers = [dict(t, key=k) for k, t in live_tiers().items()]
    except Exception:
        tiers = []
    from flask import session
    role = session.get("role") if session.get("user_id") else None
    plan_link = url_for("agent_subscription") if role == "agent" else url_for("lender_subscription") if role == "lender" else ""
    current = ""
    if role in ("agent", "lender"):
        try:
            from database import get_user_by_id
            u = get_user_by_id(session["user_id"])
            current = (dict(u).get("subscription_tier") or "free") if u else ""
        except Exception:
            current = ""
    return render_template("main/pricing.html", tiers=tiers, role=role, plan_link=plan_link, current_tier=current)


def init_app(app):
    app.add_url_rule("/privacy", endpoint="privacy", view_func=_legal("privacy"))
    app.add_url_rule("/terms", endpoint="terms", view_func=_legal("terms"))
    app.add_url_rule("/pricing", endpoint="pricing", view_func=pricing)
    for key, paths in (("for_homeowners", ("/homeowners", "/for-homeowners")), ("for_agents", ("/agents", "/for-agents")),
                       ("for_lenders", ("/lenders", "/for-lenders"))):
        view = _make(key)
        app.add_url_rule(paths[0], endpoint=key, view_func=view)
        for alt in paths[1:]:
            app.add_url_rule(alt, endpoint=key + "_alt", view_func=view)
