"""The three public pages: For Homeowners, For Agents and For Lenders. Each says in a few plain sentences what that group gets
and has one button that goes straight to the right sign-up."""
from flask import redirect, render_template, url_for

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
        "features": [
            ("Know what your home is worth", "See a gentle estimate of your value and the equity you have built, so you always know where you stand."),
            ("Stay ahead of the house", "Friendly seasonal reminders tell you what your home needs next, before it turns into a surprise."),
            ("Everything in one safe place", "Keep your home details, documents and photos together, ready whenever you need them."),
            ("Your team, one tap away", "Message your agent or your lender right from your dashboard. No hunting for an email."),
        ],
        "steps": ["Your agent invites you, or you create a free account.", "Add a few details about your home. It takes about two minutes.", "Enjoy a calm dashboard that keeps an eye on things for you."],
        "faq": [("Does it cost anything?", "No. It is always free for homeowners."), ("Who can see my information?", "Only you, and the agent and lender you are connected with. We never sell your information."), ("Do I need an agent to join?", "No. You can create an account on your own and connect with your agent any time."), ("How accurate is the home value?", "It is a helpful estimate, not an appraisal. Your agent can give you a closer look any time you ask.")],
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
        "features": [
            ("Invite a client in a minute", "Add a client and set up their home for them, so their dashboard feels ready the first time they open it."),
            ("Know who to reach out to", "A simple follow-up list shows who is due for a hello, and quick updates keep it warm, never pushy."),
            ("Your name, front and center", "Your photo, name and brokerage show on every client's home dashboard, all year long."),
            ("One place for the whole business", "Planner, CRM, transactions, booking and marketing tools all work together, so nothing is entered twice."),
        ],
        "steps": ["Create your free account and add your photo and brokerage.", "Invite clients or add your contacts to your CRM.", "Follow the gentle daily list and stay close to everyone you care about."],
        "faq": [("Is there a free plan?", "Yes. You can start free and upgrade any time when you want more tools."), ("Will my clients feel hounded?", "No. Messages are warm and spaced out, and you choose which automatic emails are on."), ("Can I bring my existing contacts?", "Yes. You can import a spreadsheet of contacts into your CRM."), ("How is billing handled?", "Paid plans are billed monthly and securely through Stripe. You can change or cancel from Plan and Billing.")],
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
        "features": [
            ("See who could save", "Spot clients who may benefit from a refinance or who have equity they could use."),
            ("Private scenarios", "Homeowners can share a payment or refinance scenario with you, and only the numbers they choose."),
            ("Your name stays in front of them", "Your name and contact show on every client's home dashboard, long after closing."),
            ("Warm updates in a few taps", "Send a helpful note to your clients without writing it from scratch."),
        ],
        "steps": ["Create your account and add your name and contact details.", "Connect with the agents and clients you work with.", "Reach out at the right moment, with something genuinely useful."],
        "faq": [("How long does setup take?", "About two minutes."), ("What do clients see?", "Your name and contact details, plus anything you choose to send them."), ("What can I see about a client?", "Only what they choose to share with you, such as a payment or refinance scenario."), ("What does it cost?", "You can start free. See the pricing page for paid plans.")],
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
        # One address for each page (the short one, which the menu and cards use); the longer one forwards to it
        app.add_url_rule(paths[0], endpoint=key, view_func=view)
        app.add_url_rule(paths[1], endpoint=key + "_long", view_func=(lambda k=key: redirect(url_for(k), 301)))
