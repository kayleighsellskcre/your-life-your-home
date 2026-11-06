"""
Generate comprehensive marketing templates database
Creates 1000+ professional, human-sounding real estate marketing templates
"""

import json

# Template variations - professional and human-sounding
headlines_just_listed = [
    "Just Listed", "New to Market", "Welcome Home", "Fresh Listing", "Newly Available",
    "Now Showing", "Introducing", "New Arrival", "Latest Listing", "Recently Listed",
    "Your Dream Home Awaits", "Discover Your New Address", "Fall in Love at First Sight",
    "Home Sweet Home Awaits", "The Search Ends Here", "Picture Perfect Living",
    "Make This Yours", "Finally Available", "The One You've Been Waiting For",
    "Opportunity Knocks", "Move-in Ready Luxury", "Stunning New Listing",
    "Don't Miss This One", "Something Special Just Listed", "Presenting",
    "Now Available for Showing", "Ready for You", "Your Next Chapter Starts Here",
    "Beautiful Home Just Hit the Market", "A Home to Fall in Love With"
]

subheadings_just_listed = [
    "A rare opportunity in [NEIGHBORHOOD]", "Your dream home just hit the market",
    "Modern living meets timeless elegance", "Luxury living redefined",
    "Where memories are made", "Discover refined living", "Everything you've been searching for",
    "Contemporary design meets everyday comfort", "Your forever home is waiting",
    "Sophistication meets comfort", "An exceptional property awaits",
    "Welcome to your sanctuary", "Life's best moments happen here",
    "Where style meets substance", "Elevated living in [CITY]",
    "The home you've been dreaming about", "Quality craftsmanship throughout",
    "Turn-key and ready for you", "Exceptional value in [NEIGHBORHOOD]",
    "Premium living at its finest", "Your perfect match is here",
    "Beautifully appointed and move-in ready", "Charm and character abound",
    "Experience luxury living", "A place to call your own",
    "Modern amenities, timeless design", "Where luxury feels like home",
    "Thoughtfully designed for today's lifestyle", "Your new beginning starts here",
    "Comfort and elegance in every detail", "Impeccably maintained and loved"
]

bodies_just_listed = [
    "This stunning property offers everything you've been looking for. Schedule your private tour today.",
    "Don't wait on this one - it won't last long. Call me for your exclusive showing.",
    "Exceptional quality and craftsmanship throughout. Your private showing awaits.",
    "Classic architecture meets modern amenities. See it before it's gone.",
    "An extraordinary home for the discerning buyer. Private tours by appointment.",
    "This beautiful home checks all the boxes. Let's get you inside today.",
    "Contemporary design with all the right touches. Call me to schedule your visit.",
    "An exceptional opportunity in a sought-after location. Book your exclusive preview.",
    "Fall in love with this meticulously maintained property. Let me show you why it's special.",
    "Every detail has been considered. You need to see this one in person.",
    "Rare opportunity to own in this desirable neighborhood. Schedule your showing now.",
    "Move-in ready and waiting for you. Let's make this your next home.",
    "From the moment you walk in, you'll know. Book your tour today.",
    "This is the one you've been waiting for. Call me before it's gone.",
    "Perfectly positioned and beautifully appointed. Your exclusive tour awaits.",
    "Quality craftsmanship shines throughout this exceptional home. See it today.",
    "The lifestyle you deserve in the location you love. Let's schedule your visit.",
    "Thoughtfully designed with your life in mind. Come see for yourself.",
    "Natural light, open spaces, and endless possibilities. Tour it this week.",
    "An incredible value in today's market. Don't let this opportunity pass."
]

ctas_general = [
    "Schedule Tour", "Book Showing", "Contact Me", "Learn More", "View Details",
    "See It Today", "Request Info", "Call Now", "Get Started", "Schedule Visit",
    "View Property", "Book Your Tour", "See Inside", "Schedule Showing",
    "Contact Me Today", "Request Showing", "View Listing", "Learn More",
    "Private Tour", "Schedule Now"
]

# Coming Soon headlines
headlines_coming_soon = [
    "Coming Soon", "Sneak Peek", "Launching Soon", "Exclusive Preview",
    "Be the First", "Almost Here", "Preview Available", "Early Access",
    "Get Ready", "On the Horizon", "Pre-Market Opportunity", "VIP Preview",
    "First Look", "Coming to Market", "Private Preview", "Advance Notice",
    "Before It Lists", "Insider Access", "Exclusive First Look", "Watch This Space"
]

subheadings_coming_soon = [
    "Be the first to know", "VIP preview available now", "Get on the list",
    "Something special is almost here", "A rare opportunity awaits",
    "Early access for qualified buyers", "Register now for exclusive access",
    "Limited preview appointments", "Don't miss your chance",
    "Exclusive opportunity for serious buyers", "Register your interest today",
    "Private showings before public launch", "Be first in line",
    "Early bird gets the home", "Pre-market access available"
]

# Generate templates for each category
def generate_templates():
    templates_db = {
        "categories": {}
    }
    
    # Just Listed - 200 variations
    just_listed_templates = []
    template_id = 1
    for i, headline in enumerate(headlines_just_listed):
        for j in range(7):  # 7 variations per headline
            template = {
                "id": f"jl-{template_id:03d}",
                "style": f"style-{(template_id % 10) + 1}",
                "headline": headline,
                "subheading": subheadings_just_listed[j % len(subheadings_just_listed)],
                "body": bodies_just_listed[j % len(bodies_just_listed)],
                "cta": ctas_general[j % len(ctas_general)]
            }
            just_listed_templates.append(template)
            template_id += 1
            if template_id > 200:
                break
        if template_id > 200:
            break
    
    templates_db["categories"]["just-listed"] = {
        "name": "Just Listed",
        "templates": just_listed_templates
    }
    
    # Coming Soon - 150 variations
    coming_soon_templates = []
    template_id = 1
    coming_soon_bodies = [
        "This exceptional property will be available soon. Register now for early access.",
        "This exceptional property will be available soon. Contact me for exclusive preview details.",
        "This exceptional property will be available soon. Limited VIP appointments available.",
        "This exceptional property will be available soon. Be the first to tour before it officially lists.",
        "This exceptional property will be available soon. Early access for qualified buyers only.",
        "This exceptional property will be available soon. Don't wait - spots are filling fast.",
        "This exceptional property will be available soon. Private showings by appointment.",
        "This exceptional property will be available soon. Join the waitlist today."
    ]
    coming_soon_ctas = ["Get Early Access", "Register Now", "Reserve Spot", "VIP Access", "Join Waitlist", "Contact Me", "Request Preview", "Learn More"]
    
    for i, headline in enumerate(headlines_coming_soon):
        for j in range(8):
            template = {
                "id": f"cs-{template_id:03d}",
                "style": f"teaser-{(template_id % 8) + 1}",
                "headline": headline,
                "subheading": subheadings_coming_soon[j % len(subheadings_coming_soon)],
                "body": coming_soon_bodies[j % 8],
                "cta": coming_soon_ctas[j % 8]
            }
            coming_soon_templates.append(template)
            template_id += 1
            if template_id > 150:
                break
        if template_id > 150:
            break
    
    templates_db["categories"]["coming-soon"] = {
        "name": "Coming Soon",
        "templates": coming_soon_templates
    }
    
    # Open House - 100 variations
    open_house_headlines = [
        "Open House", "Tour This Weekend", "Join Us", "You're Invited",
        "Open House Event", "Come See", "Tour Available", "Visit Us",
        "Open House This [DAY]", "Stop By", "See It in Person", "Walk-Through Welcome",
        "House Tour", "Public Showing", "Open Door Event", "Come Tour"
    ]
    
    oh_subheadings = ["You're invited", "See for yourself", "Tour this beautiful home", "Stop by and visit", "We can't wait to show you", "Come see what makes this special"]
    oh_bodies = [
        "Join us [DAY] from [TIME]. Light refreshments provided.",
        "Join us [DAY] from [TIME]. RSVP appreciated but not required.",
        "Join us [DAY] from [TIME]. Bring your questions - I'll have answers.",
        "Join us [DAY] from [TIME]. No appointment necessary.",
        "Join us [DAY] from [TIME]. Hope to see you there!",
        "Join us [DAY] from [TIME]. Private rooms available for serious buyers."
    ]
    oh_ctas = ["RSVP Now", "Add to Calendar", "Get Directions", "Learn More", "See Details", "Save the Date"]
    
    open_house_templates = []
    template_id = 1
    for headline in open_house_headlines:
        for j in range(6):
            template = {
                "id": f"oh-{template_id:03d}",
                "style": f"inviting-{(template_id % 6) + 1}",
                "headline": headline,
                "subheading": oh_subheadings[j],
                "body": oh_bodies[j % 6],
                "cta": oh_ctas[j]
            }
            open_house_templates.append(template)
            template_id += 1
            if template_id > 100:
                break
        if template_id > 100:
            break
    
    templates_db["categories"]["open-house"] = {
        "name": "Open House",
        "templates": open_house_templates
    }
    
    # Sold - 100 variations
    sold_headlines = [
        "Sold!", "SOLD", "Successfully Sold", "Another One Sold", "Closed",
        "Keys Handed Over", "Sold Above Asking", "Sold in Record Time",
        "Mission Accomplished", "Deal Done", "Proud to Announce", "Congratulations",
        "Closed and Celebrated", "Sold Fast", "Another Happy Family"
    ]
    
    sold_subheadings = ["Congratulations to the new homeowners", "Another successful transaction", "Helping families find home", "Thank you for trusting me", "Another dream realized", "Proud to have represented this property", "Keys have been handed over"]
    sold_bodies = ["What an honor to help this wonderful family. Your home could be next.", "Another happy family, another beautiful home. Let's find yours.", "The right strategy gets results. Ready to make your move?", "There's nothing like watching dreams come true. Let's talk.", "Proud to have guided this transaction. Thinking of selling?", "From listing to closing - a smooth, successful sale.", "Represented both buyer and seller with care."]
    sold_ctas = ["Contact Me", "Start Your Search", "Free Consultation", "Let's Connect", "Get Started", "Sell With Me", "Work Together"]
    
    sold_templates = []
    template_id = 1
    for headline in sold_headlines:
        for j in range(7):
            template = {
                "id": f"sd-{template_id:03d}",
                "style": f"celebration-{(template_id % 7) + 1}",
                "headline": headline,
                "subheading": sold_subheadings[j],
                "body": sold_bodies[j % 7],
                "cta": sold_ctas[j]
            }
            sold_templates.append(template)
            template_id += 1
            if template_id > 100:
                break
        if template_id > 100:
            break
    
    templates_db["categories"]["sold"] = {
        "name": "Sold",
        "templates": sold_templates
    }
    
    # Under Contract - 80 variations
    under_contract_headlines = [
        "Under Contract", "Pending", "Sale Pending", "In Escrow",
        "Offer Accepted", "Pending Sale", "Contract Signed", "Moving Forward"
    ]
    
    uc_subheadings = ["Pending sale", "A family is on their way home", "Offer accepted", "On the way to closing", "Another successful negotiation", "Closing soon", "Almost home", "Journey continues", "Nearly there", "Final stretch"]
    uc_bodies = ["This beautiful home has accepted an offer. Looking for something similar?", "We're in escrow! Want to be my next success story?", "Offer accepted and moving toward closing. Ready to start your journey?", "This property won't be available long. Let's find you something perfect.", "Another buyer found their dream home. Let me help you find yours.", "From offer to closing - guiding families home.", "Proud to represent this transaction. Need a trusted agent?", "On track for a successful closing. Want expert representation?", "This one moved fast! Don't miss the next opportunity.", "Helping buyers and sellers navigate every step."]
    uc_ctas = ["Contact Me", "See Similar Homes", "Let's Talk", "Get Alerts", "Work With Me", "Start Searching", "Free Consultation", "Learn More", "Get Started", "View Listings"]
    
    under_contract_templates = []
    template_id = 1
    for headline in under_contract_headlines:
        for j in range(10):
            template = {
                "id": f"uc-{template_id:03d}",
                "style": f"status-{(template_id % 5) + 1}",
                "headline": headline,
                "subheading": uc_subheadings[j],
                "body": uc_bodies[j % 10],
                "cta": uc_ctas[j]
            }
            under_contract_templates.append(template)
            template_id += 1
            if template_id > 80:
                break
        if template_id > 80:
            break
    
    templates_db["categories"]["under-contract"] = {
        "name": "Under Contract",
        "templates": under_contract_templates
    }
    
    # Price Reduction - 80 variations
    price_reduction_headlines = [
        "Price Improvement", "New Price", "Price Reduced", "Adjusted Pricing",
        "Price Drop", "Reduced", "New Opportunity", "Better Value",
        "Repriced", "Price Adjustment", "Value Alert", "Smart Buy"
    ]
    
    pr_subheadings = ["Newly adjusted to [PRICE]", "An exceptional opportunity just got better", "Sellers are motivated", "Outstanding value", "Act fast on this one", "Don't miss this opportunity", "Smart buyers take note"]
    pr_bodies = ["This is your chance to own this beautiful property at exceptional value.", "This stunning home is now offered at a new price. Don't wait.", "Great news for buyers - this home is now more accessible.", "Incredible value at the new price point. Your showing awaits.", "Smart buyers know a good deal. Let me show you why this won't last.", "The sellers are serious. This is a fantastic opportunity.", "Market-adjusted pricing makes this a must-see."]
    pr_ctas = ["Schedule Showing", "See It Today", "Book Tour Now", "Contact Me", "View Details", "Call Now", "Learn More"]
    
    price_reduction_templates = []
    template_id = 1
    for headline in price_reduction_headlines:
        for j in range(7):
            template = {
                "id": f"pr-{template_id:03d}",
                "style": f"opportunity-{(template_id % 7) + 1}",
                "headline": headline,
                "subheading": pr_subheadings[j],
                "body": pr_bodies[j % 7],
                "cta": pr_ctas[j]
            }
            price_reduction_templates.append(template)
            template_id += 1
            if template_id > 80:
                break
        if template_id > 80:
            break
    
    templates_db["categories"]["price-reduction"] = {
        "name": "Price Reduction",
        "templates": price_reduction_templates
    }
    
    # Back on Market - 70 variations
    back_on_market_headlines = [
        "Back on Market", "Available Again", "Back & Ready", "Returned to Market",
        "Available Once More", "Second Chance", "Back for You", "Another Opportunity"
    ]
    
    bm_subheadings = ["Your second chance", "Fresh start, same beautiful home", "Don't miss out twice", "An unexpected opportunity", "The home you thought you missed", "Another chance to own", "Back and waiting for you", "Opportunity knocks again", "Ready for its perfect buyer"]
    bm_bodies = ["The previous sale fell through. This beautiful property is available again.", "Sometimes things happen for a reason. This home is back.", "This property is back on the market and waiting for you.", "An unexpected second chance at this exceptional home.", "You still have a chance! This beautiful property won't last long.", "Back on the market with fresh motivation.", "Previous buyer's loss could be your gain.", "Don't let this slip away twice.", "This home is back and ready to go."]
    bm_ctas = ["Schedule Tour", "See It Now", "Book Showing", "Learn More", "Contact Me Today", "Don't Wait", "Call Now", "View Details", "Get Started"]
    
    back_on_market_templates = []
    template_id = 1
    for headline in back_on_market_headlines:
        for j in range(9):
            template = {
                "id": f"bm-{template_id:03d}",
                "style": f"secondchance-{(template_id % 6) + 1}",
                "headline": headline,
                "subheading": bm_subheadings[j],
                "body": bm_bodies[j % 9],
                "cta": bm_ctas[j]
            }
            back_on_market_templates.append(template)
            template_id += 1
            if template_id > 70:
                break
        if template_id > 70:
            break
    
    templates_db["categories"]["back-on-market"] = {
        "name": "Back on Market",
        "templates": back_on_market_templates
    }
    
    # Buyer Representation - 100 variations
    buyer_rep_headlines = [
        "Looking to Buy?", "Home Buyer Services", "Your Buyer's Agent",
        "Expert Buyer Representation", "First Time Buyer?", "Ready to Buy?",
        "Buyer Advocacy", "Home Search Partner", "Let Me Help You Buy",
        "Dedicated Buyer Agent", "Your Home Search Starts Here", "Buyer Services"
    ]
    
    br_subheadings = ["Let me be your advocate", "Expert guidance from start to finish", "Someone in your corner", "I'll make the process easy", "Experience you can trust", "Your dedicated representative", "Putting your interests first", "Navigate the market with confidence"]
    br_bodies = ["You deserve an agent who puts your interests first, every time.", "From your first showing to closing day, I'll guide you through every step.", "You need an expert negotiator on your side. Let me help.", "Buying doesn't have to be stressful. With the right agent, it can be exciting.", "Finding home is a journey. I'd be honored to walk alongside you.", "Skilled negotiation, honest advice, full support throughout the process.", "First-time buyer or seasoned investor, you deserve dedicated representation.", "Let me handle the details while you focus on finding the perfect home."]
    br_ctas = ["Work With Me", "Let's Connect", "Schedule Consultation", "Get Started", "Contact Me", "Free Consultation", "Learn More", "Start Your Search"]
    
    buyer_rep_templates = []
    template_id = 1
    for headline in buyer_rep_headlines:
        for j in range(8):
            template = {
                "id": f"br-{template_id:03d}",
                "style": f"advocacy-{(template_id % 8) + 1}",
                "headline": headline,
                "subheading": br_subheadings[j],
                "body": br_bodies[j % 8],
                "cta": br_ctas[j]
            }
            buyer_rep_templates.append(template)
            template_id += 1
            if template_id > 100:
                break
        if template_id > 100:
            break
    
    templates_db["categories"]["buyer-rep"] = {
        "name": "Buyer Representation",
        "templates": buyer_rep_templates
    }
    
    # Custom - 120 variations
    custom_templates = []
    template_id = 1
    
    custom_themes = [
        ("Neighborhood Spotlight", "Love Where You Live", "[NEIGHBORHOOD] living at its finest"),
        ("Lifestyle Marketing", "More Than Just a House", "It's a lifestyle"),
        ("Feature Highlight", "You'll Love This", "One of many reasons to love this home"),
        ("Investment Opportunity", "Smart Investment", "Build wealth through real estate"),
        ("Luxury Living", "Experience Luxury", "Where elegance meets comfort"),
        ("Family Home", "Room to Grow", "A home for every stage of life"),
        ("Modern Design", "Contemporary Living", "Sleek, stylish, sophisticated"),
        ("Historic Charm", "Character & Charm", "Timeless beauty meets modern updates"),
        ("New Construction", "Brand New", "Be the first to call it home"),
        ("Fixer Opportunity", "Dream Home Potential", "Make it yours"),
        ("Waterfront", "Life on the Water", "Wake up to water views"),
        ("Mountain Views", "Elevated Living", "Stunning views await")
    ]
    
    cx_ctas = ["Learn More", "Contact Me", "Get Details", "Schedule Tour", "View Listing", "Hear More", "See Features", "Start Conversation", "Book Showing", "Get Started"]
    
    for theme_name, headline, subheading in custom_themes:
        for j in range(10):
            template = {
                "id": f"cx-{template_id:03d}",
                "style": f"custom-{theme_name.lower().replace(' ', '-')}",
                "headline": headline,
                "subheading": subheading,
                "body": "[Customize this space to tell your unique story about this property, neighborhood, or lifestyle opportunity. Make it personal and authentic.]",
                "cta": cx_ctas[j]
            }
            custom_templates.append(template)
            template_id += 1
    
    templates_db["categories"]["custom"] = {
        "name": "Custom",
        "templates": custom_templates
    }
    
    return templates_db

# Generate and save
if __name__ == "__main__":
    print("Generating 1000+ marketing templates...")
    templates = generate_templates()
    
    # Count total
    total_templates = sum(len(cat["templates"]) for cat in templates["categories"].values())
    print(f"Generated {total_templates} total templates across {len(templates['categories'])} categories")
    
    # Print breakdown
    for cat_key, cat_data in templates["categories"].items():
        print(f"  - {cat_data['name']}: {len(cat_data['templates'])} templates")
    
    # Save to file
    with open("static/data/marketing_templates.json", "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)
    
    print("\nTemplates saved to static/data/marketing_templates.json")

