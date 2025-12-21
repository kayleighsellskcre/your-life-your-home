print('>>> THIS IS THE REAL app.py BEING RUN <<<')

import os
import boto3
from functools import wraps
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import sqlite3
import json
from types import SimpleNamespace
from PIL import Image
import secrets
import pandas as pd
import io

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    session,
    flash,
    abort,
    send_from_directory,
    jsonify,
    Response,
    make_response,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------- R2 STORAGE CLIENT ----------------
R2_CLIENT = None
if all(
    key in os.environ
    for key in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]
):
    R2_CLIENT = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )


# ---------------- SIMPLE IMAGE PROCESSING (NO BACKGROUND REMOVAL) ----------------
def remove_white_background(image_path):
    """Just convert to PNG format - no background removal."""
    try:
        img = Image.open(image_path)

        # Convert to RGB if needed (keep as-is)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Save as PNG
        img.save(image_path, "PNG", optimize=True)

        print(f"✓ Processed fixture: {Path(image_path).name}")
        return True

    except Exception as e:
        print(f"✗ Failed: {Path(image_path).name} - {e}")
        return False


# ---------------- HELPER FUNCTIONS FOR FILE UPLOADS ----------------
def handle_profile_file_upload(file_field_name: str, folder: str = "profiles", role_prefix: str = ""):
    """
    Consolidated helper for handling profile photo/logo uploads.
    Returns the file URL/key or None if no file was uploaded.
    """
    if file_field_name not in request.files:
        return None
    
    file = request.files[file_field_name]
    if not file or not file.filename:
        return None
    
    try:
        if is_r2_enabled() and R2_CLIENT:
            # Upload to R2 cloud storage (persists on Railway)
            r2_result = upload_file_to_r2(file, file.filename, folder=folder)
            file_url = r2_result.get("url") or r2_result.get("key")
            print(f"{role_prefix}PROFILE: File uploaded to R2: {file_url}")
            return file_url
        else:
            # Fallback to local storage (development)
            safe_name = secure_filename(file.filename)
            unique_name = f"{uuid4().hex}_{safe_name}"
            save_path = BASE_DIR / "static" / "uploads" / folder / unique_name
            save_path.parent.mkdir(parents=True, exist_ok=True)
            file.save(save_path)
            file_path = str(Path("uploads") / folder / unique_name).replace("\\", "/")
            print(f"{role_prefix}PROFILE: File saved locally: {file_path}")
            return file_path
    except Exception as e:
        print(f"{role_prefix}PROFILE: Error uploading file: {e}")
        flash(f"Error uploading {file_field_name}: {str(e)}", "error")
        return None


def preserve_existing_profile_media(user_id: int, professional_photo: Optional[str] = None, 
                                     brokerage_logo: Optional[str] = None):
    """
    Preserve existing profile photos/logos if new ones aren't being uploaded.
    Returns tuple: (final_photo, final_logo)
    """
    from database import get_user_profile
    
    existing_profile = get_user_profile(user_id)
    if existing_profile:
        # Convert Row to dict if needed
        if hasattr(existing_profile, 'keys') and not isinstance(existing_profile, dict):
            existing_profile = dict(existing_profile)
        elif not isinstance(existing_profile, dict):
            existing_profile = {}
        
        # Preserve existing photos if not uploading new ones
        final_photo = professional_photo if professional_photo else existing_profile.get("professional_photo")
        final_logo = brokerage_logo if brokerage_logo else existing_profile.get("brokerage_logo")
        
        return final_photo, final_logo
    
    return professional_photo, brokerage_logo


# ---------------- YOUR PLATFORM DATABASES ----------------
from database import (
    init_db,
    get_connection,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_homeowner_snapshot_for_user,
    upsert_homeowner_snapshot,
    upsert_homeowner_snapshot_full,
    add_homeowner_note,
    list_homeowner_notes,
    add_homeowner_document,
    list_homeowner_documents,
    add_homeowner_project,
    list_homeowner_projects,
    get_homeowner_project,
    update_homeowner_project,
    delete_homeowner_project,
    get_homeowner_note_by_id,
    update_homeowner_note,
    delete_homeowner_note,
    upsert_next_move_plan,
    get_next_move_plan,
    add_homeowner_question,
    add_agent_contact,
    list_agent_contacts,
    add_agent_transaction,
    get_agent_transaction,
    add_lender_loan,
    list_lender_loans,
    add_message_template,
    list_message_templates,
    add_marketing_template,
    list_marketing_templates,
    delete_homeowner_document,
    update_homeowner_document_file,
    get_homeowner_document_for_user,
    add_timeline_event,
    list_timeline_events,
    delete_timeline_event,
    add_simple_note,
    list_simple_notes,
    delete_simple_note,
    add_design_board_note,
    get_design_boards_for_user,
    get_design_board_details,
    delete_design_board,
    update_homeowner_note_photos,
    remove_photos_from_board,
    remove_fixtures_from_board,
    duplicate_design_board,
    update_board_privacy,
    update_board_colors,
    update_board_template,
    add_property,
    get_user_properties,
    get_property_by_id,
    set_primary_property,
    get_primary_property,
    delete_property,
    get_homeowner_snapshot_for_property,
    upsert_homeowner_snapshot_for_property,
    add_lender_borrower,
    list_lender_borrowers,
    get_agent_contact,
    update_agent_contact,
    get_lender_borrower,
    update_lender_borrower,
    add_crm_interaction,
    list_crm_interactions,
    log_automated_email,
    get_contacts_for_automated_email,
    add_crm_task,
    list_crm_tasks,
    update_crm_task,
    delete_crm_task,
    add_crm_deal,
    list_crm_deals,
    update_crm_deal,
    delete_crm_deal,
    add_crm_relationship,
    list_crm_relationships,
    delete_crm_relationship,
    add_crm_saved_view,
    list_crm_saved_views,
    delete_crm_saved_view,
)

# ---------------- R2 STORAGE HELPERS ----------------
from r2_storage import (
    upload_file_to_r2,
    get_file_url_from_r2,
    delete_file_from_r2,
    is_r2_enabled,
)

# ---------------- FLASK APP INIT ----------------

# Initialize DBs so platform loads with no manual trigger
init_db()

app = Flask(__name__)
app.secret_key = os.environ.get("YLH_SECRET_KEY", "change-this-secret-key")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 30  # 30 days for persistent sessions

# Context processor to make professionals available to all homeowner templates
def hex_to_color_name(hex_code):
    """Convert hex color code to official Sherwin-Williams color name."""
    if not hex_code:
        return hex_code
    
    # Normalize hex code (remove #, convert to uppercase)
    hex_clean = hex_code.strip().upper().replace('#', '')
    if len(hex_clean) == 3:
        hex_clean = ''.join([c*2 for c in hex_clean])
    hex_clean = '#' + hex_clean
    
    # Complete Sherwin-Williams Color Database (323 official colors)
    # Extracted from the create board area to ensure accuracy
    color_map = {
        # WHITES
        '#EDEAE0': 'Alabaster', '#F3F1EC': 'Extra White', '#EFEEE8': 'Pure White',
        '#F4F0E8': 'Polar Bear', '#F0EBE1': 'Greek Villa', '#F3F2ED': 'Snowbound',
        '#F7F5F0': 'High Reflective White', '#F0EDE4': 'Westhighland White',
        '#F2EFE7': 'Cotton White', '#F1EDE3': 'White Duck', '#F5F2E9': 'Divine White',
        '#EAE7DD': 'City Loft', '#EFECE3': 'Moderne White', '#F1EEE6': 'Origami White',
        '#F0EDE5': 'Roman Column', '#EFE9DD': 'Pearly White', '#F2EBDB': 'Creamy',
        '#E8DDCC': 'Navajo White', '#E9E0D1': 'Antique White', '#F0E8D9': 'Vanilla Milkshake',
        '#F5F0E6': 'Steamed Milk', '#F4F1EA': 'Ethereal White', '#F6F3EC': 'Marshmallow',
        '#F2EFE8': 'Cloud White', '#F3EFE6': 'Eider White', '#F0ECE2': 'Swiss Coffee',
        '#EFEADE': 'Ivory Tower', '#F1EAE0': 'Cashmere', '#F4F0E7': 'Twinkle',
        '#F3EEE5': 'Summer White', '#F2EDE4': 'White Flour', '#F0ECE3': 'Zurich White',
        '#F1EBE1': 'Pearl Oyster', '#F3EDE3': 'Morning Delight', '#F0EAE0': 'White Heron',
        '#F2ECE2': 'Cotton Seed', '#F0E9DF': 'Nacre', '#F2EDE5': 'China White',
        '#F0EBE3': 'White Lilac', '#EFEAE2': 'White Raisin', '#F3EEE6': 'Gauze',
        '#F1ECE4': 'Opaline', '#EFE9DE': 'Vanilla Mocha', '#F0EAE1': 'Crisp Linen',
        '#EFE8DC': 'Buff', '#F2EDE6': 'Paperwhite', '#F1EBE2': 'Grecian Ivory',
        '#EFE9DE': 'Palish Peach', '#F3EEE7': 'Panda White', '#F1ECE4': 'Nouveau Narrative',
        
        # NEUTRALS & BEIGES
        '#D6C8B8': 'Accessible Beige', '#E2DACF': 'Natural Linen', '#CFC0A8': 'Kilim Beige',
        '#D5C7B8': 'Balanced Beige', '#C8BAAC': 'Perfect Greige', '#D7CCBB': 'Nomadic Desert',
        '#DDD3C1': 'Wool Skein', '#E5D8C5': 'Sand Beach', '#E9E3D7': 'Aesthetic White',
        '#E7DDD3': 'Shoji White', '#EBE5DC': 'Canvas Tan', '#DAD0C0': 'Naturale',
        '#E4DCCE': 'Patience', '#CFC0AE': 'Shiitake', '#D8CCBA': 'Utterly Beige',
        '#E1D6C6': 'Softer Tan', '#D5C7B3': 'Whole Wheat', '#D9CCBA': 'Believable Buff',
        '#CEC0B0': 'Smoky Sand', '#D0C2B2': 'Nantucket Dune', '#D4CEC3': 'Gateway Gray',
        '#CBC0B2': 'On the Rocks', '#D9C7B5': 'Sanderling', '#E5D5C3': 'Cottage Cream',
        '#E1D3BF': 'Crisp Linen', '#DFD4C1': 'Loggia', '#CEC0AF': 'Relaxed Khaki',
        '#E7DED1': 'Relaxed White', '#DFD1BD': 'Bagel', '#D3C4B0': 'Universal Khaki',
        
        # GRAYS
        '#D5CFC1': 'Agreeable Gray', '#C9CCC4': 'Repose Gray', '#C2BDB1': 'Worldly Gray',
        '#D1CEC4': 'Colonnade Gray', '#C5C5BD': 'Mindful Gray', '#B8B5AF': 'Requisite Gray',
        '#BFB9AE': 'Anonymous', '#D0CCC2': 'Pediment', '#C7C3B9': 'Useful Gray',
        '#D2CFC8': 'Gossamer Veil', '#D9D6CD': 'Incredible White', '#CAC6BC': 'Aesthetic',
        '#BEB9AE': 'Versatile Gray', '#C6C3BA': 'Popular Gray', '#D3D0C7': 'Passive',
        '#C2C0BA': 'Big Chill', '#C4BFB5': 'Alpaca', '#C9C6BC': 'Collonade Gray',
        '#C4C0B7': 'Twilight Gray', '#B6B3AB': 'Gray Clouds', '#ACA9A0': 'Dorian Gray',
        '#BBB7AD': 'Mega Greige', '#ADA9A0': 'Pavestone', '#B9B5AB': 'Perfect Greige',
        '#C8C5BD': 'Gray Screen', '#B3AFA6': 'Argos', '#CFD1CD': 'Light French Gray',
        '#C2C5C1': 'Silverplate', '#B5B8B4': 'Gray Shingle', '#ADB1AD': 'Front Porch',
        '#A6AAA6': 'Unusual Gray', '#9FA3A0': 'Magnetic Gray', '#989C99': 'Online',
        '#919594': 'Software', '#8A8E8D': 'Grays Harbor', '#838786': 'Mount Etna',
        '#C4C5C0': 'Classic French Gray', '#BDBDB8': 'Ellie Gray', '#D6D7D2': 'Site White',
        '#CFCFC9': 'Moderne White', '#B3B4AF': 'Conservative Gray', '#ACACA7': 'Serious Gray',
        '#A5A5A0': 'Functional Gray', '#9E9E99': 'Cityscape', '#989893': 'Westchester Gray',
        '#91918C': 'Attitude Gray',
        
        # GREENS & SAGE
        '#D1D9CA': 'Sea Salt', '#8F9E8A': 'Evergreen Fog', '#B8C5B4': 'Clary Sage',
        '#C9D4CB': 'Comfort Gray', '#A5B2A0': 'Softened Green', '#8B9B8A': 'Retreat',
        '#B5BFB3': 'Acacia Haze', '#7D8C7A': 'Dried Thyme', '#B2BFB0': 'Svelte Sage',
        '#C2CFBC': 'Contented', '#C7D4C7': 'Filmy Green', '#B8C8B6': 'Liveable Green',
        '#D1DCC9': 'Lacewing', '#B1C0A8': 'Gratifying Green', '#C5D1C3': 'Rare Gray',
        '#ADBCA8': 'Celadon', '#94A88B': 'Basil', '#A3B59D': 'Restful',
        '#99AA94': 'Haven', '#8FA087': 'Nurture Green', '#7E9078': 'Artichoke',
        '#6E8266': 'Relish', '#4D6A4B': 'Woodland Green', '#5F7A5D': 'Garden Grove',
        '#6D886B': 'Privilege Green', '#7E9879': 'Bonsai Tint', '#8FA68C': 'Nurture Green',
        '#A3B5A0': 'Jardin Day', '#B2C3B0': 'Jocular Green', '#C1D2C0': 'Spirited Green',
        '#D0E0CF': 'Lighter Mint', '#B9D4BC': 'Mint Condition', '#728A70': 'Vogue Green',
        '#869885': 'Garden Sage', '#9AA799': 'Jade Dragon', '#AEB6AD': 'Halcyon Green',
        '#C2C5C0': 'Oyster Bay', '#C7C8C3': 'Collonade Gray',
        
        # BLUES & AQUAS
        '#B5C4C7': 'Rain', '#C4D4D9': 'Topsail', '#A8BCC4': 'Quietude',
        '#B8CAD1': 'Spa', '#89A3AE': 'Interesting Aqua', '#7B95A3': 'Refuge',
        '#A0B5BF': 'Jetstream', '#B8C9D2': 'Atmospheric', '#A5BAC7': 'Sleepy Blue',
        '#9DB0BC': 'Meditative', '#CAD9E1': 'Mountain Air', '#C2D4DE': 'Mild Blue',
        '#D4E4E8': 'Hint of Mint', '#B5CAD6': 'Byte Blue', '#9EAEB9': 'North Star',
        '#8FA2B0': 'Resolute Blue', '#3E5671': 'Needlepoint Navy', '#26465A': 'Naval',
        '#29465F': 'Loyal Blue', '#2E4F66': 'Anchors Aweigh', '#7799A0': 'Cascade Green',
        '#8BAAB5': 'Pool Blue', '#A0BBC8': 'Powder Blue', '#B5CDDB': 'Copen Blue',
        '#CADEE8': 'Aviary Blue', '#5A8CA0': 'Blissful Blue', '#4C7C93': 'Georgian Bay',
        '#3E6C86': 'Secure Blue', '#7095A8': 'Stream', '#84A5B7': 'Leisure Blue',
        '#98B6C6': 'Windy Blue', '#ACC7D5': 'Languid Blue', '#C0D8E4': 'Rhythmic Blue',
        '#5577AA': 'Jacaranda', '#4466A8': 'Blue Chip', '#33559A': 'Dignity Blue',
        '#224488': 'Honorable Blue', '#113366': 'Commodore',
        
        # WARM TONES & CREAMS
        '#F2E8DA': 'Napery', '#F1E5D5': 'Ivory Lace', '#E8DCC9': 'Wool Skein',
        '#E3D4BE': 'Toasted Pine Nut', '#E2D5C0': 'Buff', '#D9CAB3': 'Crewel Tan',
        '#D5C6AF': 'Mannered Gold', '#E7DAC7': 'Rice Grain', '#F0E3D1': 'Nacre',
        '#EFE2D0': 'Honied White', '#DCCDB7': 'Rustic City', '#D8C9B2': 'Bittersweet Stem',
        '#E8DCC8': 'Sand Dollar', '#E5D8C4': 'Navajo White', '#E2D5C1': 'Oyster Bar',
        '#DFD1BD': 'Latte', '#DBCEB9': 'Whole Wheat', '#D8CAB6': 'Softer Tan',
        '#D5C7B2': 'Macadamia', '#D1C3AE': 'Nomadic Desert', '#CEC0AB': 'Sand Beach',
        '#CABCA7': 'Pavilion Beige', '#C7B9A4': 'Ramie', '#C3B5A0': 'Tony Taupe',
        '#C0B29D': 'Tavern Taupe', '#BCAE99': 'Doeskin', '#B9AB96': 'Khaki Shade',
        '#B5A792': 'Corkboard', '#E6D9C8': 'Dhurrie Beige', '#E3D6C5': 'Toasted Pine Nut',
        '#DFD2C1': 'Crewel Tan', '#DCCFBE': 'Mannered Gold', '#D8CBBA': 'Diverse Beige',
        '#D5C8B7': 'Wool Skein', '#D1C4B3': 'Smoky Beige', '#CEC1AF': 'Sanderling',
        '#CABDAC': 'Stone Lion', '#C7BAA8': 'Brandon Beige', '#C3B6A5': 'Balanced Beige',
        '#C0B3A1': 'Taupe Tone', '#BCAF9E': 'Versatile Gray', '#B9AC9A': 'Pathway',
        '#B5A897': 'Tea Chest', '#B2A593': 'Harmonic Tan',
        
        # DARK & DRAMATIC
        '#3A3A38': 'Iron Ore', '#3E3E3D': 'Black Magic', '#3C3A35': 'Urbane Bronze',
        '#6B685F': 'Muddled Basil', '#57675D': 'Jasper', '#4E5D53': 'Pewter Green',
        '#2F2F30': 'Tricorn Black', '#3B3935': 'Black Bean', '#635F58': 'Peppercorn',
        '#393937': 'Andiron', '#31353D': 'Inkwell', '#32383F': 'Caviar',
        '#2E3134': 'Cyberspace', '#3E3E3C': 'Domino', '#504C48': 'Gauntlet Gray',
        '#4B4542': 'Sealskin', '#6C6861': 'Grizzle Gray', '#736E67': 'Mink',
        '#6D6864': 'Garret Gray', '#7A6E63': 'Brainstorm Bronze', '#6B6259': 'Urbane Bronze',
        '#635F57': 'Black Fox', '#5D5955': 'Thunderous', '#5A5550': 'Sable',
        '#585551': 'Anew Gray', '#6B6A5F': 'Muddled Basil', '#3C4A3E': 'Rookwood Dark Green',
        '#384337': 'Foxhall Green', '#2A4030': 'Shamrock', '#2C3D32': 'Roycroft Bottle Green',
        
        # ACCENT COLORS - REDS & PINKS
        '#8E2C2A': 'Real Red', '#99322F': 'Fireweed', '#A43833': 'Red Bay',
        '#AF3E38': 'Positive Red', '#BA443C': 'Tanager', '#C54A41': 'Habanero Chile',
        '#E57A6E': 'Coral', '#EA8A7F': 'Charisma', '#EF9A90': 'Dishy Coral',
        '#F4AAA1': 'Jovial', '#F9BAB2': 'Mellow Coral', '#F5E5E3': 'Touching White',
        '#D9B1B1': 'Rose Colored', '#E4C8C8': 'Rose Embroidery',
        
        # ACCENT COLORS - YELLOWS & GOLDS
        '#C89D34': 'Gold Rush', '#D3A83A': 'Nugget', '#DEB340': 'Golden Fleece',
        '#E9BE46': 'Glitzy Gold', '#F4C94C': 'Fun Yellow', '#F9D452': 'Lively Yellow',
        '#FEDF58': 'Confident Yellow', '#F5E682': 'Daffodil', '#F9EA8C': 'Lucent Yellow',
        '#FDEE96': 'Banana Cream', '#FFF2A0': 'Butter Up', '#FFF6AA': 'Lantern Light',
        
        # ACCENT COLORS - PURPLES & LAVENDERS
        '#6A5B7B': 'Kimono Violet', '#5C4D66': 'Plummy', '#4E3F51': 'Dewberry',
        '#766889': 'Fabulous Grape', '#8A7A9E': 'Venture Violet', '#9E8DB3': 'Brave Purple',
        '#B3A0C8': 'Novel Lilac', '#C7B3DD': 'Rhapsody Lilac', '#DBC6F2': 'Inspired Lilac',
        '#E8D9F5': 'Elation', '#F4EDFA': 'Potentially Purple', '#C7B5D8': 'Spangle',
        
        # ACCENT COLORS - ORANGES & TERRACOTTA
        '#A54826': 'Cayenne', '#B5532C': 'Determined Orange', '#C55E32': 'Copper Mountain',
        '#D56938': 'Husky Orange', '#E5743E': 'Energetic Orange', '#F57F44': 'Tango',
        '#FA8A4A': 'Outgoing Orange', '#FE9550': 'Surprise Amber', '#FFA056': 'Kumquat',
        '#FFAB5C': 'Succulent Peach', '#FFB662': 'Tangerine', '#FFC168': 'Exciting Orange',
    }
    
    # Fallback for common custom colors not in Sherwin-Williams database
    fallback_map = {
        '#F6E9DF': 'Cream',  # Custom cream color
        '#B79F82': 'Taupe',  # Custom taupe color
        '#6B6A45': 'Olive Green',  # Custom olive (close to Muddled Basil)
        '#3A352C': 'Charcoal',  # Custom charcoal (close to Urbane Bronze)
    }
    
    # Check exact match in main database first
    if hex_clean in color_map:
        return color_map[hex_clean]
    
    # Check fallback map
    if hex_clean in fallback_map:
        return fallback_map[hex_clean]
    
    # Try to find closest match by RGB distance (for custom colors)
    try:
        r1 = int(hex_clean[1:3], 16)
        g1 = int(hex_clean[3:5], 16)
        b1 = int(hex_clean[5:7], 16)
        
        closest_name = None
        min_distance = float('inf')
        
        # Search through all Sherwin-Williams colors
        for hex_val, name in color_map.items():
            if hex_val.startswith('#'):
                r2 = int(hex_val[1:3], 16)
                g2 = int(hex_val[3:5], 16)
                b2 = int(hex_val[5:7], 16)
                
                distance = ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)**0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_name = name
        
        # If very close (within 15 color units), use the closest Sherwin-Williams name
        if min_distance < 15:
            return closest_name
    except:
        pass
    
    # Fallback: return hex code if no match found
    return hex_code


@app.context_processor
def inject_professionals():
    """Make professionals data available to all templates - CRITICAL FOR DASHBOARD DISPLAY."""
    from database import get_homeowner_professionals
    professionals = []
    user = get_current_user()
    if user and user.get("role") == "homeowner" and user.get("id"):
        try:
            homeowner_id = user.get("id")
            profs_raw = get_homeowner_professionals(homeowner_id)
            print(f"CONTEXT PROCESSOR: Loading professionals for homeowner {homeowner_id} - found {len(profs_raw)}")
            
            for prof in profs_raw:
                if hasattr(prof, 'keys'):
                    prof_dict = dict(prof)
                    # Ensure professional_role is set correctly
                    if not prof_dict.get('professional_role'):
                        prof_dict['professional_role'] = prof_dict.get('professional_type') or prof_dict.get('role') or prof_dict.get('user_id')
                    
                    # Ensure we have the professional_id
                    if not prof_dict.get('professional_id'):
                        prof_dict['professional_id'] = prof_dict.get('user_id')
                    
                    professionals.append(prof_dict)
                    print(f"CONTEXT PROCESSOR: Added professional - role: {prof_dict.get('professional_role')}, name: {prof_dict.get('name')}, id: {prof_dict.get('professional_id')}, phone: {prof_dict.get('phone')}")
                else:
                    professionals.append(prof)
            
            if not professionals:
                print(f"CONTEXT PROCESSOR WARNING: No professionals found for homeowner {homeowner_id}")
                # Try to get from agent_id column as fallback
                from database import get_user_by_id
                homeowner_user = get_user_by_id(homeowner_id)
                if homeowner_user:
                    homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') and not isinstance(homeowner_user, dict) else homeowner_user
                    agent_id = homeowner_dict.get("agent_id")
                    if agent_id:
                        print(f"CONTEXT PROCESSOR: Found agent_id {agent_id} in user record, attempting to load...")
                        try:
                            from database import get_user_by_id, get_user_profile
                            agent_user = get_user_by_id(agent_id)
                            if agent_user:
                                agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                                agent_profile = get_user_profile(agent_id)
                                prof_data = {
                                    'professional_id': agent_id,
                                    'professional_role': 'agent',
                                    'name': agent_dict.get('name'),
                                    'email': agent_dict.get('email'),
                                    'user_id': agent_id
                                }
                                if agent_profile:
                                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
                                    prof_data.update({
                                        'professional_photo': profile_dict.get('professional_photo'),
                                        'brokerage_logo': profile_dict.get('brokerage_logo'),
                                        'brokerage_name': profile_dict.get('brokerage_name'),
                                        'phone': profile_dict.get('phone'),
                                        'team_name': profile_dict.get('team_name'),
                                        'website_url': profile_dict.get('website_url'),
                                        'bio': profile_dict.get('bio'),
                                    })
                                professionals.append(prof_data)
                                print(f"CONTEXT PROCESSOR: Added agent from agent_id column - {prof_data.get('name')}")
                        except Exception as fallback_error:
                            print(f"CONTEXT PROCESSOR: Fallback failed - {str(fallback_error)}")
        except Exception as e:
            import traceback
            print(f"CONTEXT PROCESSOR ERROR: {traceback.format_exc()}")
    else:
        if user:
            print(f"CONTEXT PROCESSOR: User is not a homeowner - role: {user.get('role')}, id: {user.get('id')}")
        else:
            print(f"CONTEXT PROCESSOR: No user logged in")
    
    return dict(professionals=professionals, hex_to_color_name=hex_to_color_name)

# ---------------- AJAX PLANNER ROUTE ----------------
@app.route("/homeowner/reno/planner/ajax-add", methods=["POST"])
def homeowner_reno_planner_ajax_add():
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json() or {}
    name = data.get("project_name", "").strip()
    budget = data.get("project_budget")
    status = data.get("project_status", "Planning").strip()
    category = data.get("project_category", "Other").strip()  # Get category, default to "Other"
    board_name = data.get("board_name", "").strip()
    summary = data.get("project_summary", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Project name required"}), 400

    # Convert budget to string (function expects string, not float)
    budget_str = str(budget) if budget else ""

    # Get notes from JSON data
    notes = data.get("project_notes", "").strip()
    
    # If a board_name is provided, save as a design board note as well
    board_save_error = None
    board_save_success = False
    if board_name:
        note_title = name
        # Include budget and status in details - create a comprehensive note
        note_details_parts = []
        
        # Add summary if available
        if summary:
            note_details_parts.append(summary)
        elif notes:
            note_details_parts.append(notes)
        else:
            note_details_parts.append(f"Project: {name}")
        
        # Add budget information
        if budget:
            try:
                budget_float = float(budget) if budget else 0
                note_details_parts.append(f"\n\n💰 Estimated Cost: ${budget_float:,.0f}")
            except (ValueError, TypeError):
                if budget_str:
                    note_details_parts.append(f"\n\n💰 Estimated Cost: ${budget_str}")
        
        # Add status
        if status:
            note_details_parts.append(f"\n📋 Status: {status}")
        
        # Add category if available
        if category and category != "Other":
            note_details_parts.append(f"\n📁 Category: {category}")
        
        note_details = "\n".join(note_details_parts)
        
        try:
            # add_design_board_note will create the board if it doesn't exist
            note_id = add_design_board_note(
                user_id=user_id, 
                project_name=board_name, 
                title=note_title,
                details=note_details,
                photos=[],
                files=[],
                vision_statement=None,
                color_palette=None,
                board_template="collage",
                label_style="sans-serif",
                is_private=0,
                fixtures=[],
            )
            board_save_success = True
            print(f"[COST ESTIMATE SAVE] Successfully saved to mood board '{board_name}' (note_id: {note_id})")
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"[COST ESTIMATE SAVE ERROR] Could not save to board '{board_name}': {error_msg}")
            print(traceback.format_exc())
            board_save_error = error_msg

    # Always save to renovation planner, even if board save fails
    try:
        # Fix: Add category parameter and correct argument order
        # Function signature: user_id, name, category, status, budget, notes
        add_homeowner_project(user_id, name, category, status, budget_str, notes)
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[COST ESTIMATE SAVE ERROR] Could not save to planner: {error_msg}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"Could not save project: {error_msg}"}), 500
    
    # Return success response with details
    response_data = {
        "success": True,
        "saved_to_planner": True,
        "saved_to_board": board_save_success
    }
    
    if board_save_success:
        response_data["message"] = f"Successfully saved to Renovation Planner and Mood Board '{board_name}'"
    elif board_save_error:
        response_data["warning"] = f"Project saved to Renovation Planner, but could not save to mood board '{board_name}': {board_save_error}"
    else:
        response_data["message"] = "Successfully saved to Renovation Planner"
    
    return jsonify(response_data)


# ---------------- TRANSACTION HELPERS IMPORT ----------------
from transaction_helpers import (
    get_db,
    add_transaction_participant,
    create_transaction,
    get_agent_transactions,
    delete_transaction,
    get_transaction_detail,
    get_transaction_documents,
    get_transaction_participants,
    get_transaction_timeline,
    get_transaction_document_status,
)

# ---------------- GLOBAL BRAND CONFIG ----------------
FRONT_BRAND_NAME = "Your Life, Your Home"
CLOUD_CMA_URL = os.environ.get(
    "CLOUD_CMA_URL",
    "https://app.cloudcma.com/api_widget/0183b47b7401642c6ec736103095ebbb/show?post_url=https://app.cloudcma.com&source_url=ua",
)
BASE_DIR = Path(__file__).resolve().parent

# Homeowner document storage
HOMEOWNER_DOCS_DIR = BASE_DIR / "static" / "uploads" / "homeowner_docs"
HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Timeline upload storage
UPLOAD_TIMELINE = BASE_DIR / "uploads" / "timeline"
UPLOAD_TIMELINE.mkdir(parents=True, exist_ok=True)


# Helper to get current user id
def get_current_user_id() -> int:
    """Fallback to demo user for now."""
    return session.get("user_id") or 1


def get_current_user() -> Optional[dict]:
    """Get current logged-in user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    
    try:
        # Ensure user_id is integer
        user_id = int(user_id)
        row = get_user_by_id(user_id)
        
        if not row:
            # User not found in database - clear invalid session
            session.clear()
            return None
        
        # Convert Row to dict
        if hasattr(row, 'keys') and not isinstance(row, dict):
            return dict(row)
        
        return row if isinstance(row, dict) else None
    except (ValueError, TypeError) as e:
        # Invalid user_id in session - clear it
        print(f"ERROR get_current_user: Invalid user_id '{user_id}' - {str(e)}")
        session.clear()
        return None
    except Exception as e:
        print(f"ERROR get_current_user: Error getting user {user_id} - {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None


def require_homeowner_access(homeowner_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """
    Check if the current user can access a homeowner's data.
    Returns (user, error_message).
    If error_message is None, access is granted.
    """
    from database import can_access_homeowner
    
    user = get_current_user()
    if not user:
        return None, "Please log in to access this page."
    
    user_role = user.get("role")
    user_id = user.get("id")
    
    # Homeowners can only access their own data
    if user_role == "homeowner":
        if user_id != homeowner_id:
            return None, "You can only access your own dashboard."
        return user, None
    
    # Agents and lenders can access their linked homeowners
    if user_role in ("agent", "lender"):
        if can_access_homeowner(user_id, user_role, homeowner_id):
            return user, None
        return None, "You don't have access to this homeowner's data."
    
    return None, "Invalid user role."


# ---------------- AGENT TRANSACTION ROUTES ----------------
@app.route("/agent/transactions/<int:tx_id>/participants/add", methods=["POST"])
def agent_add_participant(tx_id):
    """Add a participant to an agent transaction."""
    name = request.form.get("participant_name", "").strip()
    email = request.form.get("participant_email", "").strip()
    role = request.form.get("participant_role", "").strip()

    if not name or not email or not role:
        flash("All participant fields are required.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))

    try:
        add_transaction_participant(tx_id, name, email, role)
        flash("Participant added successfully!", "success")
    except Exception as e:
        flash(f"Error adding participant: {e}", "error")

    return redirect(url_for("agent_transaction_detail", tx_id=tx_id))


# -------------------------------------------------
# EMAIL REMINDER AUTOMATION (GMAIL SMTP + APScheduler)
# -------------------------------------------------
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")


def send_reminder_email(to_email, subject, body):
    """Send a reminder email using SMTP."""
    if not EMAIL_USER or not EMAIL_PASS:
        print(f"⚠ Email not configured - cannot send to {to_email}")
        return False
    
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        print(f"✓ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"✗ Failed to send email to {to_email}: {e}")
        return False


def send_new_lead_notification(agent_id, homeowner_name, homeowner_email, referral_token=None, signup_timestamp=None):
    """Send email notification to agent when a new lead signs up."""
    if not EMAIL_USER or not EMAIL_PASS:
        print(f"⚠ Email not configured - cannot send lead notification")
        return False
    
    try:
        from database import get_user_by_id, get_user_profile
        
        # Get agent information
        agent_user = get_user_by_id(agent_id)
        if not agent_user:
            print(f"⚠ Agent {agent_id} not found - cannot send notification")
            return False
        
        agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
        agent_email = agent_dict.get('email')
        agent_name = agent_dict.get('name', 'Agent')
        
        if not agent_email:
            print(f"⚠ Agent {agent_id} has no email - cannot send notification")
            return False
        
        # Get agent profile for additional info
        agent_profile = get_user_profile(agent_id)
        brokerage_name = ""
        if agent_profile:
            profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
            brokerage_name = profile_dict.get('brokerage_name', '')
        
        # Build email subject and body
        from flask import request
        base_url = request.url_root.rstrip('/') if hasattr(request, 'url_root') else 'https://itsyourlifeyourhome.com'
        
        subject = f"🎉 New Lead: {homeowner_name} signed up!"
        
        body = f"""New Lead Notification

A new homeowner has signed up and been added to your CRM!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LEAD INFORMATION:
• Name: {homeowner_name}
• Email: {homeowner_email}
• Signup Date: {signup_timestamp or 'Just now'}

REFERRAL SOURCE:
• Referral Token: {referral_token if referral_token and referral_token != 'default' else 'Default Assignment'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This lead has been automatically added to your CRM with stage "new".

You can view and manage this contact in your CRM dashboard:
{base_url}/agent/crm

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is an automated notification from Your Life • Your Home.
"""
        
        # Send the email
        success = send_reminder_email(agent_email, subject, body)
        
        if success:
            print(f"✓ New lead notification sent to {agent_name} ({agent_email})")
            # Log the email in the database
            try:
                from database import log_automated_email
                # We need the contact_id, but we don't have it here
                # For now, just log that we sent the notification
                print(f"✓ Lead notification logged for agent {agent_id}")
            except Exception as log_error:
                print(f"⚠ Could not log email notification: {log_error}")
        
        return success
        
    except Exception as e:
        import traceback
        print(f"✗ Error sending new lead notification: {e}")
        print(traceback.format_exc())
        return False


def get_due_reminders():
    """TODO: Replace with real DB logic to fetch due reminders."""
    return []


def send_due_reminders():
    reminders = get_due_reminders()
    for r in reminders:
        if r.get("email"):
            send_reminder_email(r["email"], r["subject"], r["body"])


# ====================== CRM AUTOMATED EMAIL FUNCTIONS ======================

def get_birthday_contacts():
    """Get contacts with birthdays today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    
    contacts = []
    # Get agent contacts
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, agent_user_id, name, email, birthday
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' 
          AND auto_birthday = 1
          AND birthday LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    # Get lender borrowers
    cur.execute(
        """
        SELECT id, lender_user_id, name, email, birthday
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' 
          AND auto_birthday = 1
          AND birthday LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    return contacts


def get_anniversary_contacts():
    """Get contacts with home anniversaries today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    # Agent contacts
    cur.execute(
        """
        SELECT id, agent_user_id, name, email, home_anniversary, property_address
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' 
          AND auto_anniversary = 1
          AND home_anniversary LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email'],
            'property_address': row['property_address']
        })
    
    # Lender borrowers
    cur.execute(
        """
        SELECT id, lender_user_id, name, email, home_anniversary, property_address
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' 
          AND auto_anniversary = 1
          AND home_anniversary LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email'],
            'property_address': row['property_address']
        })
    
    conn.close()
    return contacts


def send_birthday_emails():
    """Send birthday emails to contacts."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    contacts = get_birthday_contacts()
    for contact in contacts:
        subject = f"🎂 Happy Birthday, {contact['name']}!"
        body = f"""Hi {contact['name']},

Wishing you a wonderful birthday filled with joy and happiness!

Thank you for being part of our community.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'birthday', contact['email'], subject, 'sent'
            )


def send_anniversary_emails():
    """Send home anniversary emails."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    contacts = get_anniversary_contacts()
    for contact in contacts:
        property_info = f" at {contact.get('property_address', 'your home')}" if contact.get('property_address') else ""
        subject = f"🏠 Happy Home Anniversary, {contact['name']}!"
        body = f"""Hi {contact['name']},

Congratulations on your home anniversary{property_info}!

We hope you're enjoying your home and creating wonderful memories.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'anniversary', contact['email'], subject, 'sent'
            )


def send_seasonal_checklists():
    """Send seasonal home maintenance checklists."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    month = datetime.now().month
    
    # Determine season
    if month in [12, 1, 2]:
        season = "Winter"
        checklist = """Winter Home Maintenance Checklist:
• Check heating system and change filters
• Inspect roof for ice dams
• Seal windows and doors
• Test smoke and carbon monoxide detectors
• Clean gutters and downspouts
• Insulate pipes to prevent freezing
• Check weatherstripping
• Service snow removal equipment"""
    elif month in [3, 4, 5]:
        season = "Spring"
        checklist = """Spring Home Maintenance Checklist:
• Clean gutters and downspouts
• Inspect roof for winter damage
• Service air conditioning system
• Check exterior paint and siding
• Clean windows and screens
• Inspect deck and patio
• Fertilize lawn and garden
• Check irrigation system"""
    elif month in [6, 7, 8]:
        season = "Summer"
        checklist = """Summer Home Maintenance Checklist:
• Service air conditioning
• Check and clean outdoor spaces
• Inspect and clean pool/spa if applicable
• Check for pest issues
• Maintain landscaping
• Inspect exterior for damage
• Check outdoor lighting
• Prepare for storm season"""
    else:  # 9, 10, 11
        season = "Fall"
        checklist = """Fall Home Maintenance Checklist:
• Clean gutters and downspouts
• Inspect roof and chimney
• Service heating system
• Seal windows and doors
• Check insulation
• Winterize outdoor plumbing
• Rake leaves and maintain yard
• Test smoke detectors"""
    
    # Get contacts with seasonal emails enabled
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT id, agent_user_id, name, email
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' AND auto_seasonal = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    cur.execute(
        """
        SELECT id, lender_user_id, name, email
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' AND auto_seasonal = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    
    # Send to all contacts (only once per season - you may want to track this)
    for contact in contacts:
        subject = f"🍂 {season} Home Maintenance Checklist"
        body = f"""Hi {contact['name']},

Here's your {season.lower()} home maintenance checklist to keep your home in great shape:

{checklist}

Stay safe and enjoy the season!

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'seasonal', contact['email'], subject, 'sent'
            )


def send_equity_updates():
    """Send equity update emails based on frequency."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    
    # Only send on 1st of month for monthly, 1st of odd months for bimonthly, etc.
    if today.day != 1:
        return
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    # Monthly contacts
    if today.month % 1 == 0:  # Every month
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address, 
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'monthly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Bimonthly contacts (odd months)
    if today.month % 2 == 1:
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address,
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'bimonthly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Quarterly contacts (Jan, Apr, Jul, Oct)
    if today.month in [1, 4, 7, 10]:
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address,
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'quarterly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Same for lender borrowers
    if today.month % 1 == 0:
        cur.execute(
            """
            SELECT id, lender_user_id, name, email, property_address,
                   loan_amount, loan_rate
            FROM lender_borrowers
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'monthly'
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'lender_borrower', 'professional_id': row['lender_user_id']})
    
    conn.close()
    
    for contact in contacts:
        equity = contact.get('equity_estimate', 0)
        property_val = contact.get('property_value', 0)
        subject = f"💰 Your Home Equity Update - {today.strftime('%B %Y')}"
        body = f"""Hi {contact['name']},

Here's your monthly equity update:

Property: {contact.get('property_address', 'Your Home')}
Estimated Value: ${property_val:,.0f}
Estimated Equity: ${equity:,.0f}

Your home equity continues to grow! This represents significant wealth you've built.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'equity', contact['email'], subject, 'sent'
            )


def send_holiday_greetings():
    """Send holiday greeting emails."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    
    # Only send on specific holidays
    holidays = {
        (12, 25): "Merry Christmas",
        (12, 31): "Happy New Year",
        (7, 4): "Happy 4th of July",
        (11, 25): "Happy Thanksgiving",  # Approximate
    }
    
    holiday = holidays.get((today.month, today.day))
    if not holiday:
        return
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT id, agent_user_id, name, email
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' AND auto_holidays = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    cur.execute(
        """
        SELECT id, lender_user_id, name, email
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' AND auto_holidays = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    
    for contact in contacts:
        subject = f"🎄 {holiday}, {contact['name']}!"
        body = f"""Hi {contact['name']},

{holiday}! We hope you have a wonderful celebration with family and friends.

Thank you for being part of our community.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'holiday', contact['email'], subject, 'sent'
            )


def update_home_values_daily():
    """Automatically update home values daily using Homebot-style appreciation formulas."""
    from database import get_connection, get_user_properties, get_homeowner_snapshot_for_property, upsert_homeowner_snapshot_for_property
    from datetime import datetime, timedelta
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Get all homeowners with snapshots
        cur.execute("""
            SELECT DISTINCT user_id, property_id 
            FROM homeowner_snapshots 
            WHERE value_estimate IS NOT NULL OR loan_balance IS NOT NULL
        """)
        snapshots = cur.fetchall()
        conn.close()
        
        updated_count = 0
        for row in snapshots:
            user_id = row['user_id']
            property_id = row['property_id'] if row['property_id'] else None
            
            if not property_id:
                continue
                
            # Get current snapshot
            snapshot = get_homeowner_snapshot_for_property(user_id, property_id)
            if not snapshot:
                continue
            
            # Apply Homebot-style daily appreciation (3.5% annual = ~0.0096% daily)
            # Only update if value hasn't been refreshed in last 24 hours
            last_refresh = snapshot.get('last_value_refresh')
            if last_refresh:
                try:
                    last_date = datetime.fromisoformat(last_refresh.replace('Z', '+00:00'))
                    if (datetime.now() - last_date.replace(tzinfo=None)).days < 1:
                        continue  # Skip if updated in last 24 hours
                except:
                    pass
            
            current_value = snapshot.get('value_estimate')
            if current_value and current_value > 0:
                # Daily appreciation: 1.035^(1/365) - 1 ≈ 0.000094% per day
                daily_rate = (1.035 ** (1/365)) - 1
                new_value = current_value * (1 + daily_rate)
                
                # Update snapshot with new value (preserve other fields)
                upsert_homeowner_snapshot_for_property(
                    user_id=user_id,
                    property_id=property_id,
                    value_estimate=new_value,
                )
                updated_count += 1
        
        print(f"✓ Daily value update: {updated_count} properties updated")
    except Exception as e:
        print(f"Error in daily value update: {e}")


def start_scheduler():
    """Start background scheduler safely without blocking app startup."""
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(send_due_reminders, "cron", hour=12, minute=0)
        # CRM automated emails
        scheduler.add_job(send_birthday_emails, "cron", hour=9, minute=0)  # 9 AM daily
        scheduler.add_job(send_anniversary_emails, "cron", hour=9, minute=5)  # 9:05 AM daily
        scheduler.add_job(send_seasonal_checklists, "cron", day=1, hour=10, minute=0)  # 1st of month, 10 AM
        scheduler.add_job(send_equity_updates, "cron", day=1, hour=10, minute=5)  # 1st of month, 10:05 AM
        scheduler.add_job(send_holiday_greetings, "cron", hour=9, minute=10)  # 9:10 AM daily
        # Automatic daily home value updates (Homebot-style)
        scheduler.add_job(update_home_values_daily, "cron", hour=2, minute=0)  # 2 AM daily
        scheduler.start()
        print("✓ Reminder scheduler started with CRM automation and daily value updates.")
    except Exception as e:
        print(f"⚠ Scheduler error: {e}")(f"⚠ Scheduler could not start (non-critical): {e}")


# Start scheduler when app starts (non-blocking)
try:
    start_scheduler()
except Exception as e:
    print(f"⚠ Scheduler initialization failed (non-critical): {e}")


# -------------------------------------------------
# SHARED UTILS
# -------------------------------------------------
def json_or_list(value):
    """Convert DB string/json text into a Python list safely."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [ln.strip() for ln in value.splitlines() if ln.strip()]
    return []


def _row_get(row, key, default=None):
    """Safe getter that supports dicts, sqlite rows, objects."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        pass
    return getattr(row, key, default)


# -------------------------------------------------
# HOMEOWNER SNAPSHOT + CRM METRICS
# -------------------------------------------------
def calculate_appreciated_value(
    initial_value: float, purchase_date: str, annual_rate: float = 0.035
) -> float:
    """
    Calculate home value with automatic appreciation over time.
    """
    if not initial_value or not purchase_date:
        return initial_value

    try:
        if isinstance(purchase_date, str):
            purchase_dt = datetime.strptime(purchase_date.split()[0], "%Y-%m-%d")
        else:
            purchase_dt = purchase_date

        today = datetime.now()
        years_elapsed = (today - purchase_dt).days / 365.25
        appreciated_value = initial_value * ((1 + annual_rate) ** years_elapsed)
        return round(appreciated_value, 2)
    except Exception as e:
        print(f"Error calculating appreciation: {e}")
        return initial_value


def get_homeowner_snapshot_or_default(user_row: Optional[dict]):
    if not user_row:
        return {
            "name": "Friend",
            "value_estimate": None,
            "equity_estimate": None,
            "loan_rate": None,
            "loan_payment": None,
            "loan_balance": None,
            "next_steps": [
                "Check home value + equity.",
                "Upload documents to keep things organized.",
                "Plan your Next-Home move anytime.",
            ],
        }

    snap = get_homeowner_snapshot_for_user(user_row["id"])
    if not snap:
        base = get_homeowner_snapshot_or_default(None)
        base["name"] = user_row.get("name", "Friend")
        return base

    value_estimate = snap["value_estimate"]
    equity_estimate = snap["equity_estimate"]

    return {
        "name": user_row.get("name", "Friend"),
        "value_estimate": value_estimate,
        "equity_estimate": equity_estimate,
        "loan_rate": snap["loan_rate"],
        "loan_payment": snap["loan_payment"],
        "loan_balance": snap["loan_balance"],
        "loan_start_date": snap.get("loan_start_date"),
        "last_value_refresh": snap.get("last_value_refresh"),
        "next_steps": [
            "Review equity growth.",
            "Consider refinancing or payment changes.",
            "Use renovation + next-move planners anytime.",
        ],
    }


def get_agent_dashboard_metrics(user_id):
    if not user_id:
        return {
            "new_leads": 0,
            "active_transactions": 0,
            "followups_today": 0,
        }
    contacts = list_agent_contacts(user_id)
    transactions = get_agent_transactions(user_id)
    
    # Convert Row objects to dicts if needed
    contacts_list = []
    for c in contacts:
        if hasattr(c, 'keys'):
            contacts_list.append(dict(c))
        else:
            contacts_list.append(c)
    
    return {
        "new_leads": sum((c1.get("stage") or "") == "new" for c1 in contacts_list),
        "active_transactions": len(transactions) if transactions else 0,
        "followups_today": max(len(contacts_list) // 2, 0),
    }


def get_lender_dashboard_metrics(user_id):
    if not user_id:
        return {
            "new_applications": 0,
            "loans_in_process": 0,
            "nurture_contacts": 0,
        }
    borrowers = list_lender_borrowers(user_id)
    loans = list_lender_loans(user_id)
    
    # Convert Row objects to dicts if needed
    borrowers_list = []
    for b in borrowers:
        if hasattr(b, 'keys'):
            borrowers_list.append(dict(b))
        else:
            borrowers_list.append(b)
    
    return {
        "new_applications": sum(
            (b1.get("status") or "") == "preapproval" for b1 in borrowers_list
        ),
        "loans_in_process": len(loans) if loans else 0,
        "nurture_contacts": max(len(borrowers_list) // 2, 0),
    }


# -------------------------------------------------
# MAIN / AUTH
# -------------------------------------------------
@app.route("/r/<referral_code>")
def referral_landing(referral_code):
    """
    Public landing page for agent/lender referral links (legacy support).
    Redirects to new signup flow with ref token.
    """
    # For backward compatibility, redirect old referral codes to new signup flow
    return redirect(url_for("signup", role="homeowner", ref=referral_code))
    
    # Convert to dict if needed
    if hasattr(professional, 'keys'):
        prof_dict = dict(professional)
    else:
        prof_dict = professional if professional else {}
    
    return render_template(
        "public/referral_landing.html",
        brand_name=FRONT_BRAND_NAME,
        professional=prof_dict,
        referral_code=referral_code
    )


@app.route("/")
def index():
    """
    Landing page with three paths:
    - Homeowner dashboard
    - Agent dashboard
    - Lender dashboard
    
    Tracks default agent assignment for visitors without referral tokens.
    """
    # Track default agent assignment for anonymous visitors
    referral_token = request.args.get("ref")
    if not referral_token and not session.get("user_id"):
        from database import get_or_create_default_agent
        default_agent_id = get_or_create_default_agent()
        session["default_agent_id"] = default_agent_id
        session["referral_token"] = None  # Mark as default assignment
    
    return render_template(
        "main/index.html",
        brand_name=FRONT_BRAND_NAME,
        cloud_cma_url=CLOUD_CMA_URL,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Sign up for any role: homeowner | agent | lender
    For homeowners: Uses referral token if provided, otherwise assigns to default agent (Kayleigh Biggs)
    For agents/lenders: No referral token required
    """
    role = request.args.get("role", "homeowner")
    if role not in ("homeowner", "agent", "lender"):
        role = "homeowner"
    
    # Get referral token from query parameter or session
    referral_token = request.args.get("ref") or request.form.get("ref_token") or session.get("referral_token")
    
    # For homeowners without referral token, use default agent (no error, just assign)
    if role == "homeowner" and not referral_token:
        from database import get_or_create_default_agent
        default_agent_id = get_or_create_default_agent()
        # Store in session for tracking
        if not session.get("default_agent_id"):
            session["default_agent_id"] = default_agent_id
        session["referral_token"] = None  # Mark as default assignment

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role_from_form = request.form.get("role", "").strip()
        referral_token_from_form = request.form.get("ref_token") or referral_token

        # Determine role: prioritize form value, then URL parameter, default to homeowner
        if role_from_form in ("agent", "lender", "homeowner"):
            role = role_from_form
        elif role in ("agent", "lender", "homeowner"):
            role = role  # Use URL parameter
        else:
            role = "homeowner"  # Default fallback

        # Validate required fields
        if not name:
            flash("Please enter your full name.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not password:
            flash("Please enter a password.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))

        password_hash = generate_password_hash(password)
        
        # For homeowners, validate referral token and get agent_id/lender_id
        agent_id = None
        lender_id = None
        
        if role == "homeowner":
            from database import get_referral_link_by_token, get_or_create_default_agent
            
            # If no referral token, use default agent (from session if available, otherwise create/get)
            if not referral_token_from_form:
                agent_id = session.get("default_agent_id") or get_or_create_default_agent()
                if not session.get("default_agent_id"):
                    session["default_agent_id"] = agent_id
                referral_token_from_form = "default"  # Mark as default assignment
            else:
                referral_link = get_referral_link_by_token(referral_token_from_form)
                
                if not referral_link:
                    # Fallback to default agent if token is invalid
                    agent_id = session.get("default_agent_id") or get_or_create_default_agent()
                    if not session.get("default_agent_id"):
                        session["default_agent_id"] = agent_id
                    referral_token_from_form = "default"
                else:
                    # Extract agent_id and lender_id from referral link
                    # Convert Row to dict if needed
                    if hasattr(referral_link, 'keys') and not isinstance(referral_link, dict):
                        referral_link = dict(referral_link)
                    
                    agent_id = referral_link.get("agent_id") if referral_link.get("agent_id") else None
                    lender_id = referral_link.get("lender_id") if referral_link.get("lender_id") else None
                    
                    print(f"SIGNUP: Referral link found - agent_id: {agent_id}, lender_id: {lender_id}")
                    
                    # If referral link has no agent or lender, use default agent
                    if not agent_id and not lender_id:
                        agent_id = get_or_create_default_agent()
                        referral_token_from_form = "default"
                        print(f"SIGNUP: No agent/lender in referral link, using default agent {agent_id}")

        # Debug: Print signup attempt
        print(f"DEBUG Signup: role={role}, email={email}, name={name}, agent_id={agent_id}, lender_id={lender_id}")
        
        # Use retry logic for database operations to handle locking
        max_retries = 5
        retry_count = 0
        user_id = None
        last_error = None
        
        while retry_count < max_retries:
            try:
                user_id = create_user(name, email, password_hash, role, agent_id=agent_id, lender_id=lender_id)
                print(f"DEBUG Signup: User created successfully with ID {user_id}")
                
                # Verify the account was actually created by querying the database
                from database import get_user_by_email
                verify_user = get_user_by_email(email)
                if not verify_user:
                    raise ValueError("Account creation failed - user not found in database after creation")
                
                # Convert Row to dict if needed
                if hasattr(verify_user, 'keys') and not isinstance(verify_user, dict):
                    verify_user = dict(verify_user)
                
                # Verify the password hash matches
                if not verify_user.get("password_hash"):
                    raise ValueError("Account creation failed - password hash not set")
                
                print(f"DEBUG Signup: Account verified - user exists with ID {verify_user.get('id')}")
                user_id = verify_user.get('id')  # Use verified user ID
                break  # Success, exit retry loop
                
            except sqlite3.OperationalError as e:
                last_error = e
                error_str = str(e).lower()
                if "locked" in error_str and retry_count < max_retries - 1:
                    retry_count += 1
                    import time
                    wait_time = 0.5 * retry_count  # Exponential backoff: 0.5s, 1s, 1.5s, 2s
                    print(f"DEBUG Signup: Database locked, retrying in {wait_time}s ({retry_count}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Re-raise if not a lock issue or max retries reached
                    print(f"DEBUG Signup: OperationalError - {str(e)}")
                    if "locked" in error_str:
                        flash("The database is temporarily busy. Please wait a moment and try again.", "error")
                    else:
                        flash(f"Database error: {str(e)}. Please try again.", "error")
                    import traceback
                    print(f"Database operational error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except ValueError as e:
                print(f"DEBUG Signup: ValueError - {str(e)}")
                flash(str(e), "error")
                return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except sqlite3.IntegrityError as e:
                # Check if it's a unique constraint violation (duplicate email)
                print(f"DEBUG Signup: IntegrityError - {str(e)}")
                if "UNIQUE constraint failed" in str(e) or "email" in str(e).lower():
                    # Check if the existing account is incomplete (no password_hash)
                    from database import get_user_by_email, update_user_password
                    existing_user = get_user_by_email(email)
                    
                    if existing_user:
                        # Convert Row to dict if needed
                        if hasattr(existing_user, 'keys') and not isinstance(existing_user, dict):
                            existing_user = dict(existing_user)
                        
                        # Check if account is incomplete (missing password_hash)
                        if not existing_user.get("password_hash"):
                            print(f"DEBUG Signup: Found incomplete account for {email}, completing it...")
                            try:
                                # Check if role matches - if not, we can't complete it
                                existing_role = existing_user.get("role")
                                if existing_role and existing_role != role:
                                    print(f"DEBUG Signup: Role mismatch - existing: {existing_role}, requested: {role}")
                                    flash(f"This email is registered as a {existing_role}, not a {role}. Please sign in instead.", "error")
                                    return redirect(url_for("login", role=existing_role))
                                
                                # Update the incomplete account with password, name, and role/agent_id/lender_id if needed
                                update_user_password(
                                    existing_user["id"],
                                    password_hash,
                                    name if name else existing_user.get("name"),
                                    role if role else existing_role,
                                    agent_id if role == "homeowner" else None,
                                    lender_id if role == "homeowner" else None
                                )
                                
                                # Verify the update worked
                                verify_user = get_user_by_email(email)
                                if verify_user:
                                    # Convert Row to dict if needed
                                    if hasattr(verify_user, 'keys') and not isinstance(verify_user, dict):
                                        verify_user = dict(verify_user)
                                    
                                    if verify_user.get("password_hash"):
                                        user_id = existing_user["id"]
                                        print(f"DEBUG Signup: Incomplete account completed successfully - ID {user_id}")
                                        # Break out of retry loop and continue with signup flow
                                        break
                                    else:
                                        raise ValueError("Account update failed - password hash still not set")
                                else:
                                    raise ValueError("Account update failed - user not found after update")
                            except Exception as update_error:
                                print(f"DEBUG Signup: Error completing incomplete account - {str(update_error)}")
                                flash("An error occurred while completing your account. Please try again.", "error")
                                return redirect(url_for("signup", role=role, ref=referral_token_from_form))
                        else:
                            # Account exists - ALWAYS UPDATE PASSWORD (password reset feature)
                            print(f"SIGNUP: Account exists - updating password for {email}")
                            try:
                                from database import update_user_password
                                update_user_password(
                                    existing_user["id"],
                                    password_hash,
                                    name if name else existing_user.get("name"),
                                    role if role else existing_user.get("role")
                                )
                                print(f"SIGNUP: Password updated successfully for user {existing_user['id']}")
                                flash("Your password has been updated! Please log in with your new password.", "success")
                                return redirect(url_for("login", role=role))
                            except Exception as update_error:
                                print(f"SIGNUP ERROR: Failed to update password - {str(update_error)}")
                                import traceback
                                print(traceback.format_exc())
                                flash("Error updating password. Please try again or contact support.", "error")
                                return redirect(url_for("signup", role=role))
                    else:
                        # Email constraint failed but user not found - this shouldn't happen
                        print(f"DEBUG Signup: IntegrityError but user not found - {str(e)}")
                        flash("That email is already in use. Please sign in instead.", "error")
                        return redirect(url_for("login", role=role))
                else:
                    flash(f"An error occurred while creating your account. Please try again.", "error")
                    import traceback
                    print(f"Database error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except Exception as e:
                last_error = e
                print(f"DEBUG Signup: Exception - {type(e).__name__}: {str(e)}")
                # For non-lock errors, don't retry
                if "locked" not in str(e).lower():
                    flash(f"An error occurred: {str(e)}. Please try again.", "error")
                    import traceback
                    print(f"Unexpected error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
                # If it's a lock error but not OperationalError, retry
                if retry_count < max_retries - 1:
                    retry_count += 1
                    import time
                    wait_time = 0.5 * retry_count
                    print(f"DEBUG Signup: Retrying after error ({retry_count}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    flash(f"An error occurred: {str(e)}. Please try again.", "error")
                    import traceback
                    print(f"Unexpected error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not user_id:
            # If we get here, all retries failed
            error_msg = f"Unable to create account. {str(last_error) if last_error else 'Please try again in a moment.'}"
            if last_error and "locked" in str(last_error).lower():
                flash("The database is temporarily busy. Please wait a moment and try again.", "error")
            else:
                flash(error_msg, "error")
            print(f"DEBUG Signup: All retries failed. Last error: {last_error}")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))

        # CRITICAL: Create client relationship AND CRM contact - MUST WORK
        if role == "homeowner":
            print(f"\n{'='*60}")
            print(f"SIGNUP: Setting up homeowner relationships")
            print(f"  Homeowner ID: {user_id}")
            print(f"  Agent ID: {agent_id}")
            print(f"  Lender ID: {lender_id}")
            print(f"  Referral Token: {referral_token_from_form}")
            print(f"{'='*60}\n")
            
            from database import (
                create_client_relationship, 
                add_agent_contact, 
                list_agent_contacts,
                get_user_by_id
            )
            
            relationships_created = []
            crm_contacts_created = []
            
            # Handle agent relationship
            if agent_id:
                try:
                    # Verify agent exists
                    agent_user = get_user_by_id(agent_id)
                    if not agent_user:
                        print(f"SIGNUP ERROR: Agent {agent_id} not found!")
                        flash(f"Error: Agent not found. Please contact support.", "error")
                    else:
                        agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                        print(f"SIGNUP: Agent verified - {agent_dict.get('name')} (ID: {agent_id})")
                        
                        # Create client relationship - CRITICAL
                        try:
                            relationship_id = create_client_relationship(
                                homeowner_id=user_id,
                                professional_id=agent_id,
                                professional_role="agent",
                                referral_code=referral_token_from_form if referral_token_from_form != "default" else None
                            )
                            relationships_created.append(f"agent relationship (ID: {relationship_id})")
                            print(f"SIGNUP SUCCESS: Created client relationship - homeowner {user_id} -> agent {agent_id} (relationship ID: {relationship_id})")
                        except Exception as rel_error:
                            print(f"SIGNUP ERROR: Failed to create client relationship - {str(rel_error)}")
                            import traceback
                            print(traceback.format_exc())
                            flash(f"Warning: Could not link to agent. Please contact support.", "error")
                        
                        # Create CRM contact - CRITICAL
                        try:
                            # Check if contact already exists
                            existing_contacts = list_agent_contacts(agent_id)
                            contact_exists = False
                            existing_contact_id = None
                            for existing in existing_contacts:
                                existing_dict = dict(existing) if hasattr(existing, 'keys') and not isinstance(existing, dict) else existing
                                if existing_dict.get("email") and existing_dict.get("email").lower() == email.lower():
                                    contact_exists = True
                                    existing_contact_id = existing_dict.get("id")
                                    print(f"SIGNUP: CRM contact already exists for {email} (ID: {existing_contact_id})")
                                    break
                            
                            if not contact_exists:
                                contact_id = add_agent_contact(
                                    agent_user_id=agent_id,
                                    name=name,
                                    email=email,
                                    phone="",
                                    stage="new",
                                    best_contact=email if email else "",
                                    last_touch="",
                                    birthday="",
                                    home_anniversary="",
                                    address="",
                                    notes=f"Signed up via referral link on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                    tags="referral",
                                    property_address="",
                                    property_value=None,
                                    equity_estimate=None
                                )
                                crm_contacts_created.append(f"CRM contact (ID: {contact_id})")
                                print(f"SIGNUP SUCCESS: Created CRM contact {contact_id} for agent {agent_id}")
                                
                                # VERIFY: Check that contact was actually created
                                verify_contacts = list_agent_contacts(agent_id)
                                found_contact = False
                                for vc in verify_contacts:
                                    vc_dict = dict(vc) if hasattr(vc, 'keys') and not isinstance(vc, dict) else vc
                                    if vc_dict.get("id") == contact_id:
                                        found_contact = True
                                        print(f"SIGNUP VERIFICATION: CRM contact {contact_id} confirmed in agent's CRM")
                                        break
                                
                                if not found_contact:
                                    print(f"SIGNUP VERIFICATION ERROR: CRM contact {contact_id} NOT found in agent's CRM after creation!")
                                    flash(f"Warning: Contact created but verification failed. Please contact support.", "error")
                                
                                # SEND EMAIL NOTIFICATION TO AGENT
                                signup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                try:
                                    send_new_lead_notification(
                                        agent_id=agent_id,
                                        homeowner_name=name,
                                        homeowner_email=email,
                                        referral_token=referral_token_from_form if referral_token_from_form != "default" else None,
                                        signup_timestamp=signup_time
                                    )
                                    print(f"SIGNUP: Email notification sent to agent {agent_id}")
                                except Exception as email_error:
                                    print(f"SIGNUP WARNING: Could not send email notification - {str(email_error)}")
                                    # Don't fail signup if email fails
                            else:
                                print(f"SIGNUP: CRM contact already exists (ID: {existing_contact_id}), skipping creation")
                                crm_contacts_created.append(f"CRM contact (ID: {existing_contact_id}, already existed)")
                        except Exception as crm_error:
                            print(f"SIGNUP ERROR: Failed to create CRM contact - {str(crm_error)}")
                            import traceback
                            print(traceback.format_exc())
                            flash(f"Warning: Could not add you to agent's CRM. Please contact support.", "error")
                except Exception as agent_error:
                    print(f"SIGNUP ERROR: Agent setup failed - {str(agent_error)}")
                    import traceback
                    print(traceback.format_exc())
                    flash(f"Error linking to agent. Please contact support.", "error")
            
            # Handle lender relationship
            if lender_id:
                try:
                    relationship_id = create_client_relationship(
                        homeowner_id=user_id,
                        professional_id=lender_id,
                        professional_role="lender",
                        referral_code=referral_token_from_form if referral_token_from_form != "default" else None
                    )
                    relationships_created.append(f"lender relationship (ID: {relationship_id})")
                    print(f"SIGNUP SUCCESS: Created client relationship - homeowner {user_id} -> lender {lender_id}")
                except Exception as lender_error:
                    print(f"SIGNUP ERROR: Failed to create lender relationship - {str(lender_error)}")
                    import traceback
                    print(traceback.format_exc())
            
            # Final verification - verify relationships were actually created
            from database import get_homeowner_professionals
            try:
                verify_profs = get_homeowner_professionals(user_id)
                print(f"SIGNUP VERIFICATION: Found {len(verify_profs)} professionals for homeowner {user_id}")
                for vp in verify_profs:
                    vp_dict = dict(vp) if hasattr(vp, 'keys') and not isinstance(vp, dict) else vp
                    print(f"  - {vp_dict.get('professional_role')}: {vp_dict.get('name')} (ID: {vp_dict.get('professional_id')})")
            except Exception as verify_error:
                print(f"SIGNUP VERIFICATION ERROR: {str(verify_error)}")
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"SIGNUP: Relationship Summary")
            print(f"  Relationships created: {len(relationships_created)}")
            for rel in relationships_created:
                print(f"    - {rel}")
            print(f"  CRM contacts created: {len(crm_contacts_created)}")
            for crm in crm_contacts_created:
                print(f"    - {crm}")
            print(f"{'='*60}\n")
            
            # Success message
            if referral_token_from_form == "default":
                flash("Welcome! You've been connected to Kayleigh Biggs at Worth Clark Realty.", "success")
            else:
                if relationships_created and crm_contacts_created:
                    flash("Welcome! You've been connected to your professional team and added to their CRM.", "success")
                elif relationships_created:
                    flash("Welcome! You've been connected to your professional team.", "success")
                else:
                    flash("Account created, but there was an issue linking to your agent. Please contact support.", "error")

        # Auto-login after signup (permanent session for convenience)
        session.permanent = True
        session["user_id"] = user_id
        session["role"] = role
        session["name"] = name or "Friend"
        
        # Success message for agents/lenders
        if role == "agent":
            flash("Account created successfully! Welcome to Your Life Your Home.", "success")
        elif role == "lender":
            flash("Account created successfully! Welcome to Your Life Your Home.", "success")
        
        # Save email to localStorage (will be handled by JavaScript)
        response = redirect(url_for("agent_dashboard") if role == "agent"
                           else url_for("lender_dashboard") if role == "lender"
                           else url_for("homeowner_overview"))
        
        # Set cookie to trigger JavaScript to save email
        response.set_cookie("save_email", email, max_age=365*24*60*60)
        
        return response

    return render_template(
        "auth/signup.html", 
        role=role, 
        brand_name=FRONT_BRAND_NAME,
        referral_code=referral_token  # Keep for backward compatibility in template
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """REWRITTEN: Simple, direct login that always works."""
    role = request.args.get("role") or request.form.get("role")
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "").strip()
        
        if not email or not password:
            flash("Please fill in email and password.", "error")
            return redirect(url_for("login", role=selected_role))
        
        if not selected_role:
            flash("Please select your role.", "error")
            return redirect(url_for("login"))
        
        # Get user
        try:
            user_row = get_user_by_email(email)
        except Exception as e:
            print(f"LOGIN ERROR: {str(e)}")
            flash("Database error. Please try again.", "error")
            return redirect(url_for("login", role=selected_role))
        
        if not user_row:
            flash("Email or password did not match.", "error")
            return redirect(url_for("login", role=selected_role))
        
        # Convert to dict
        user = dict(user_row) if hasattr(user_row, 'keys') and not isinstance(user_row, dict) else (user_row if isinstance(user_row, dict) else {})
        
        user_id = user.get("id")
        user_role = str(user.get("role") or "").strip().lower()
        stored_hash = user.get("password_hash")
        
        # Check password hash exists
        if not stored_hash or not stored_hash.strip():
            flash("Account incomplete. Please sign up again with the same email to set your password.", "error")
            return redirect(url_for("signup", role=selected_role))
        
        # Verify password - SIMPLE DIRECT CHECK
        password_correct = False
        try:
            password_correct = check_password_hash(stored_hash, password)
        except Exception as e:
            print(f"LOGIN PASSWORD CHECK ERROR: {str(e)}")
            # If check fails, try to regenerate hash and update
            try:
                new_hash = generate_password_hash(password)
                from database import update_user_password
                update_user_password(user_id, new_hash)
                password_correct = True  # Allow login after reset
                flash("Your password has been reset. Please log in again.", "success")
            except:
                pass
        
        if not password_correct:
            # Offer immediate password reset
            flash("Password incorrect. You can reset it by signing up again with the same email.", "error")
            return redirect(url_for("signup", role=selected_role))
        
        # Check role
        if user_role != str(selected_role).strip().lower():
            flash(f"This account is registered as a {user.get('role', 'user').title()}. Please select the correct role.", "error")
            return redirect(url_for("login", role=user.get("role", "homeowner")))
        
        # Set session
        session.clear()
        session.permanent = request.form.get("remember") == "on"
        session["user_id"] = int(user_id)
        session["name"] = str(user.get("name") or "User")
        session["role"] = str(user.get("role"))
        session.modified = True
        
        # Redirect
        redirect_map = {
            "homeowner": url_for("homeowner_overview"),
            "agent": url_for("agent_dashboard"),
            "lender": url_for("lender_dashboard")
        }
        redirect_url = redirect_map.get(user_role, url_for("index"))
        
        response = redirect(redirect_url)
        response.set_cookie("save_email", email, max_age=365*24*60*60 if session.permanent else None)
        return response
    
    return render_template("auth/login.html", role=role)


@app.route("/debug/check-account/<email>")
def debug_check_account(email):
    """Debug route to check account details - REMOVE IN PRODUCTION"""
    try:
        user_row = get_user_by_email(email.lower().strip())
        if not user_row:
            return jsonify({"error": "User not found", "email": email})
        
        if hasattr(user_row, 'keys') and not isinstance(user_row, dict):
            user = dict(user_row)
        else:
            user = user_row if isinstance(user_row, dict) else {}
        
        # Check relationships
        from database import get_homeowner_professionals
        professionals = []
        if user.get("role") == "homeowner":
            try:
                profs = get_homeowner_professionals(user.get("id"))
                for prof in profs:
                    prof_dict = dict(prof) if hasattr(prof, 'keys') and not isinstance(prof, dict) else prof
                    professionals.append({
                        "id": prof_dict.get("professional_id"),
                        "name": prof_dict.get("name"),
                        "role": prof_dict.get("professional_role"),
                        "email": prof_dict.get("email")
                    })
            except Exception as e:
                professionals = [{"error": str(e)}]
        
        return jsonify({
            "found": True,
            "id": user.get("id"),
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
            "agent_id": user.get("agent_id"),
            "lender_id": user.get("lender_id"),
            "has_password_hash": bool(user.get("password_hash")),
            "password_hash_length": len(user.get("password_hash", "")),
            "password_hash_preview": user.get("password_hash", "")[:50] + "..." if user.get("password_hash") else None,
            "password_hash_starts_with": user.get("password_hash", "")[:10] if user.get("password_hash") else None,
            "professionals": professionals
        })
    except Exception as e:
        return jsonify({"error": str(e), "email": email})


@app.route("/debug/sync-homeowner-to-crm/<int:homeowner_id>")
def debug_sync_homeowner_to_crm(homeowner_id):
    """Sync an existing homeowner to their agent's CRM - REMOVE IN PRODUCTION"""
    try:
        from database import get_user_by_id, list_agent_contacts, add_agent_contact, get_homeowner_professionals
        
        homeowner = get_user_by_id(homeowner_id)
        if not homeowner:
            return jsonify({"error": "Homeowner not found"}), 404
        
        homeowner_dict = dict(homeowner) if hasattr(homeowner, 'keys') and not isinstance(homeowner, dict) else homeowner
        if homeowner_dict.get("role") != "homeowner":
            return jsonify({"error": "User is not a homeowner"}), 400
        
        # Get agent from relationships (more reliable than agent_id column)
        professionals = get_homeowner_professionals(homeowner_id)
        agent_id = None
        for prof in professionals:
            prof_dict = dict(prof) if hasattr(prof, 'keys') and not isinstance(prof, dict) else prof
            if prof_dict.get("professional_role") == "agent":
                agent_id = prof_dict.get("professional_id") or prof_dict.get("user_id")
                break
        
        # Fallback to agent_id column if no relationship found
        if not agent_id:
            agent_id = homeowner_dict.get("agent_id")
        
        if not agent_id:
            return jsonify({"error": "Homeowner has no linked agent"}), 400
        
        # Check if contact already exists
        existing_contacts = list_agent_contacts(agent_id)
        contact_exists = False
        for existing in existing_contacts:
            existing_dict = dict(existing) if hasattr(existing, 'keys') and not isinstance(existing, dict) else existing
            if existing_dict.get("email") and existing_dict.get("email").lower() == homeowner_dict.get("email", "").lower():
                contact_exists = True
                break
        
        if contact_exists:
            return jsonify({"message": "Contact already exists in CRM", "homeowner_id": homeowner_id, "agent_id": agent_id})
        
        # Create CRM contact
        contact_id = add_agent_contact(
            agent_user_id=agent_id,
            name=homeowner_dict.get("name", ""),
            email=homeowner_dict.get("email", ""),
            phone="",
            stage="new",
            best_contact=homeowner_dict.get("email", "") if homeowner_dict.get("email") else "",
            last_touch="",
            birthday="",
            home_anniversary="",
            address="",
            notes=f"Synced from homeowner account on {datetime.now().strftime('%Y-%m-%d')}",
            tags="referral",
            property_address="",
            property_value=None,
            equity_estimate=None
        )
        
        return jsonify({
            "success": True,
            "message": f"Homeowner {homeowner_id} synced to agent {agent_id}'s CRM",
            "contact_id": contact_id
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/debug/check-crm-contacts/<int:agent_id>")
def debug_check_crm_contacts(agent_id):
    """Debug route to check all contacts for an agent - REMOVE IN PRODUCTION"""
    try:
        from database import list_agent_contacts, get_user_by_id, get_connection
        
        # Get agent info
        agent = get_user_by_id(agent_id)
        if not agent:
            return jsonify({"error": "Agent not found"}), 404
        
        agent_dict = dict(agent) if hasattr(agent, 'keys') and not isinstance(agent, dict) else agent
        
        # Get all contacts (no filter)
        all_contacts = list_agent_contacts(agent_id, stage_filter=None)
        
        # Get contacts by stage
        new_contacts = list_agent_contacts(agent_id, stage_filter="new")
        active_contacts = list_agent_contacts(agent_id, stage_filter="active")
        
        # Convert to dicts
        contacts_data = []
        for contact in all_contacts:
            contact_dict = dict(contact) if hasattr(contact, 'keys') and not isinstance(contact, dict) else contact
            contacts_data.append({
                'id': contact_dict.get('id'),
                'name': contact_dict.get('name'),
                'email': contact_dict.get('email'),
                'stage': contact_dict.get('stage'),
                'created_at': contact_dict.get('created_at'),
                'tags': contact_dict.get('tags'),
            })
        
        return jsonify({
            "agent": {
                "id": agent_id,
                "name": agent_dict.get('name'),
                "email": agent_dict.get('email'),
            },
            "total_contacts": len(all_contacts),
            "new_contacts": len(new_contacts),
            "active_contacts": len(active_contacts),
            "all_contacts": contacts_data,
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/debug/sync-all-homeowners-to-crm")
def debug_sync_all_homeowners_to_crm():
    """Sync ALL existing homeowners to their agents' CRMs - REMOVE IN PRODUCTION"""
    try:
        from database import get_connection, list_agent_contacts, add_agent_contact, get_homeowner_professionals
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, agent_id FROM users WHERE role = 'homeowner'")
        homeowners = cur.fetchall()
        conn.close()
        
        results = []
        for homeowner_row in homeowners:
            homeowner = dict(homeowner_row) if hasattr(homeowner_row, 'keys') and not isinstance(homeowner_row, dict) else homeowner_row
            homeowner_id = homeowner.get("id")
            
            # Get agent from relationships
            professionals = get_homeowner_professionals(homeowner_id)
            agent_id = None
            for prof in professionals:
                prof_dict = dict(prof) if hasattr(prof, 'keys') and not isinstance(prof, dict) else prof
                if prof_dict.get("professional_role") == "agent":
                    agent_id = prof_dict.get("professional_id") or prof_dict.get("user_id")
                    break
            
            if not agent_id:
                agent_id = homeowner.get("agent_id")
            
            if not agent_id:
                results.append({"homeowner_id": homeowner_id, "status": "skipped", "reason": "no agent"})
                continue
            
            # Check if contact exists
            existing_contacts = list_agent_contacts(agent_id)
            contact_exists = False
            for existing in existing_contacts:
                existing_dict = dict(existing) if hasattr(existing, 'keys') and not isinstance(existing, dict) else existing
                if existing_dict.get("email") and existing_dict.get("email").lower() == homeowner.get("email", "").lower():
                    contact_exists = True
                    break
            
            if contact_exists:
                results.append({"homeowner_id": homeowner_id, "status": "exists", "agent_id": agent_id})
                continue
            
            # Create contact
            try:
                contact_id = add_agent_contact(
                    agent_user_id=agent_id,
                    name=homeowner.get("name", ""),
                    email=homeowner.get("email", ""),
                    phone="",
                    stage="new",
                    best_contact=homeowner.get("email", "") if homeowner.get("email") else "",
                    last_touch="",
                    birthday="",
                    home_anniversary="",
                    address="",
                    notes=f"Synced from homeowner account on {datetime.now().strftime('%Y-%m-%d')}",
                    tags="referral",
                    property_address="",
                    property_value=None,
                    equity_estimate=None
                )
                results.append({"homeowner_id": homeowner_id, "status": "created", "contact_id": contact_id, "agent_id": agent_id})
            except Exception as e:
                results.append({"homeowner_id": homeowner_id, "status": "error", "error": str(e)})
        
        return jsonify({
            "success": True,
            "total_homeowners": len(homeowners),
            "results": results
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Password reset - allows users to reset their password by email"""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if not email or not new_password:
            flash("Please fill in email and new password.", "error")
            return redirect(url_for("reset_password"))
        
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password"))
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("reset_password"))
        
        try:
            user_row = get_user_by_email(email)
            if not user_row:
                flash("Account not found. Please check your email.", "error")
                return redirect(url_for("reset_password"))
            
            user = dict(user_row) if hasattr(user_row, 'keys') and not isinstance(user_row, dict) else (user_row if isinstance(user_row, dict) else {})
            user_id = user.get("id")
            new_hash = generate_password_hash(new_password)
            
            from database import update_user_password
            update_user_password(user_id, new_hash)
            
            flash("Password reset successful! Please log in with your new password.", "success")
            return redirect(url_for("login", role=user.get("role", "homeowner")))
        except Exception as e:
            print(f"RESET PASSWORD ERROR: {str(e)}")
            import traceback
            print(traceback.format_exc())
            flash("Error resetting password. Please try again.", "error")
            return redirect(url_for("reset_password"))
    
    return render_template("auth/reset_password.html")


@app.route("/debug/reset-password", methods=["POST"])
def debug_reset_password():
    """TEMPORARY: Reset password for debugging - REMOVE IN PRODUCTION"""
    try:
        data = request.get_json() or request.form
        email = (data.get("email") or "").strip().lower()
        new_password = data.get("password") or data.get("new_password")
        
        if not email or not new_password:
            return jsonify({"error": "Email and password required"}), 400
        
        user_row = get_user_by_email(email)
        if not user_row:
            return jsonify({"error": "User not found"}), 404
        
        if hasattr(user_row, 'keys') and not isinstance(user_row, dict):
            user = dict(user_row)
        else:
            user = user_row if isinstance(user_row, dict) else {}
        
        user_id = user.get("id")
        new_hash = generate_password_hash(new_password)
        
        from database import update_user_password
        update_user_password(user_id, new_hash)
        
        return jsonify({
            "success": True,
            "message": f"Password reset for user {user_id}",
            "email": email
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/logout")
def logout():
    """Logout and clear session."""
    user_id = session.get("user_id")
    session.clear()
    session.modified = True  # Ensure session is saved
    print(f"LOGOUT: User {user_id} logged out")
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


# -------------------------------------------------
# HOMEOWNER ROUTES
# -------------------------------------------------
@app.route("/homeowner")
@app.route("/homeowner/<int:homeowner_id>")
def homeowner_overview(homeowner_id: Optional[int] = None):
    """
    Overview dashboard (My Home Base).
    Shows agent/lender info if homeowner was referred.
    If homeowner_id is provided, it's an agent/lender viewing a homeowner's dashboard.
    """
    from database import get_homeowner_professionals, get_user_by_id
    
    # Determine which homeowner to show
    if homeowner_id:
        # Agent/lender viewing a specific homeowner
        user, error = require_homeowner_access(homeowner_id)
        if error:
            flash(error, "error")
            return redirect(url_for("agent_dashboard" if user and user.get("role") == "agent" else "lender_dashboard"))
        homeowner_user = get_user_by_id(homeowner_id)
        if not homeowner_user or homeowner_user["role"] != "homeowner":
            flash("Homeowner not found.", "error")
            return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
        homeowner_user = dict(homeowner_user)
        viewing_as_professional = True
        is_guest = False
    else:
        # Homeowner viewing their own dashboard (or guest)
        user = get_current_user()
        if not user:
            # Guest mode - allow viewing but not saving
            is_guest = True
            homeowner_user = None
            homeowner_id = None
            viewing_as_professional = False
        elif user.get("role") != "homeowner":
            flash("This page is for homeowners only.", "error")
            return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
        else:
            # Authenticated homeowner
            is_guest = False
            homeowner_user = user
            homeowner_id = user["id"]
            viewing_as_professional = False
    
    # CRITICAL: Explicitly load professionals for this homeowner
    professionals_list = []
    if homeowner_id:
        try:
            profs_raw = get_homeowner_professionals(homeowner_id)
            print(f"HOMEOWNER DASHBOARD: Loading professionals for homeowner {homeowner_id} - found {len(profs_raw)}")
            for prof in profs_raw:
                if hasattr(prof, 'keys'):
                    prof_dict = dict(prof)
                    if not prof_dict.get('professional_role'):
                        prof_dict['professional_role'] = prof_dict.get('professional_type') or 'agent'
                    if not prof_dict.get('professional_id'):
                        prof_dict['professional_id'] = prof_dict.get('user_id')
                    professionals_list.append(prof_dict)
                    print(f"HOMEOWNER DASHBOARD: Professional - {prof_dict.get('name')} ({prof_dict.get('professional_role')})")
                else:
                    professionals_list.append(prof)
            
            if not professionals_list:
                print(f"HOMEOWNER DASHBOARD WARNING: No professionals found for homeowner {homeowner_id}")
                # Fallback: check agent_id column
                if homeowner_user:
                    homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') and not isinstance(homeowner_user, dict) else homeowner_user
                    agent_id = homeowner_dict.get("agent_id")
                    if agent_id:
                        print(f"HOMEOWNER DASHBOARD: Found agent_id {agent_id} in user record, loading...")
                        try:
                            from database import get_user_by_id, get_user_profile
                            agent_user = get_user_by_id(agent_id)
                            if agent_user:
                                agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                                agent_profile = get_user_profile(agent_id)
                                prof_data = {
                                    'professional_id': agent_id,
                                    'professional_role': 'agent',
                                    'name': agent_dict.get('name'),
                                    'email': agent_dict.get('email'),
                                    'user_id': agent_id
                                }
                                if agent_profile:
                                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
                                    prof_data.update({
                                        'professional_photo': profile_dict.get('professional_photo'),
                                        'brokerage_logo': profile_dict.get('brokerage_logo'),
                                        'brokerage_name': profile_dict.get('brokerage_name'),
                                        'phone': profile_dict.get('phone'),
                                        'team_name': profile_dict.get('team_name'),
                                        'website_url': profile_dict.get('website_url'),
                                        'bio': profile_dict.get('bio'),
                                    })
                                professionals_list.append(prof_data)
                                print(f"HOMEOWNER DASHBOARD: Added agent from agent_id column - {prof_data.get('name')}")
                        except Exception as fallback_error:
                            print(f"HOMEOWNER DASHBOARD: Fallback failed - {str(fallback_error)}")
        except Exception as prof_error:
            import traceback
            print(f"HOMEOWNER DASHBOARD ERROR loading professionals: {traceback.format_exc()}")
    
    # Get snapshot (only for authenticated homeowners) - use property-specific for consistency with equity overview
    snapshot = None
    if homeowner_user:
        from database import get_primary_property, get_homeowner_snapshot_for_property
        primary_property = get_primary_property(homeowner_id)
        if primary_property:
            property_id = primary_property.get('id')
            snapshot = get_homeowner_snapshot_for_property(homeowner_id, property_id)
            # Calculate equity if we have value and loan balance (same formula as equity overview)
            if snapshot and snapshot.get('value_estimate') and snapshot.get('loan_balance'):
                snapshot['equity_estimate'] = snapshot.get('value_estimate') - snapshot.get('loan_balance')
        if not snapshot:
            # Fallback to user-level snapshot
            snapshot = get_homeowner_snapshot_or_default(homeowner_user)
    else:
        # Guest mode - create empty snapshot
        snapshot = {
            "value_estimate": None,
            "equity_estimate": None,
            "loan_rate": None,
            "loan_payment": None,
            "loan_balance": None,
        }
    
    # Use the professionals_list we loaded earlier, or fallback to empty list
    professionals = professionals_list if professionals_list else []
    
    # Final verification before rendering
    if homeowner_id and not professionals:
        print(f"HOMEOWNER DASHBOARD FINAL WARNING: No professionals found for homeowner {homeowner_id} - dashboard will show empty team section")

    return render_template(
        "homeowner/overview.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
        professionals=professionals,
        homeowner=homeowner_user,
        viewing_as_professional=viewing_as_professional,
        current_user=user,
        is_guest=is_guest,
    )


@app.route("/homeowner/recent-activity")
def homeowner_recent_activity():
    return render_template(
        "homeowner/recent_activity.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ----- SAVED NOTES / DESIGN BOARDS -----
@app.route("/homeowner/saved-notes", methods=["GET", "POST"])
def homeowner_saved_notes():
    """
    Manage premium mood boards for homeowners with advanced features like
    color palettes, vision statements, templates, and drag-and-drop uploads.
    """
    user = get_current_user()
    if not user:
        flash("Please log in to create boards.", "warning")
        return redirect(url_for("login"))
    
    user_id = user.get("id")
    if not user_id:
        flash("User ID not found. Please log in again.", "error")
        return redirect(url_for("login"))
    
    print(f"[DEBUG][SAVED NOTES] user_id: {user_id}, user: {user.get('email', 'unknown')}")
    raw_boards = get_design_boards_for_user(user_id)
    print(
        f"[DEBUG][SAVED NOTES] get_design_boards_for_user({user_id}) returned: {raw_boards}"
    )

    design_dir = BASE_DIR / "static" / "uploads" / "design_boards"
    design_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        print(f"\n{'='*80}")
        print(f"[BOARD POST] POST request received!")
        print(f"[BOARD POST] Form keys: {list(request.form.keys())}")
        print(f"[BOARD POST] Files keys: {list(request.files.keys())}")
        for key, value in request.form.items():
            if len(str(value)) < 100:
                print(f"[BOARD POST]   {key}: {value}")
            else:
                print(f"[BOARD POST]   {key}: {str(value)[:100]}...")
        print(f"{'='*80}\n")
        
        action = request.form.get("action") or "create_board"
        print(f"[BOARD POST] Action: {action}")

        # ---------- CREATE BOARD ----------
        if action == "create_board":
            board_name = (request.form.get("board_name") or "").strip()
            vision_statement = (request.form.get("vision_statement") or "").strip()
            board_title = (request.form.get("board_title") or "").strip()
            board_notes = (request.form.get("board_notes") or "").strip()
            board_links = (request.form.get("board_links") or "").strip()

            if not board_name:
                flash("Please provide a board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Photos
            saved_photos = []
            files = request.files.getlist("board_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")

            # Fixtures
            saved_fixtures = []
            fixture_files = request.files.getlist("board_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_fixtures.append(rel_path)
                except Exception:
                    flash(f"Could not save fixture: {safe_name}", "error")

            colors = request.form.getlist("colors[]")
            color_palette = [c for c in colors if c]
            
            # Get estimated_budget and project_status
            estimated_budget = (request.form.get("estimated_budget") or "").strip()
            project_status = (request.form.get("project_status") or "").strip()
            
            # Build details with budget and status if provided
            details_parts = []
            if board_notes:
                details_parts.append(board_notes)
            if estimated_budget:
                details_parts.append(f"\n\nEstimated Budget: ${estimated_budget}")
            if project_status:
                details_parts.append(f"Status: {project_status}")
            if board_links:
                details_parts.append(f"\n\nLinks:\n{board_links}")
            
            combined_details = "\n".join(details_parts) if details_parts else None

            # Validate required fields before attempting to save
            if not board_name or not board_name.strip():
                flash("Board name is required.", "error")
                return redirect(url_for("homeowner_saved_notes"))
            
            print(f"[BOARD CREATE] Attempting to create board:")
            print(f"  - user_id: {user_id}")
            print(f"  - board_name: {board_name}")
            print(f"  - title: {board_title}")
            print(f"  - details length: {len(combined_details) if combined_details else 0}")
            print(f"  - photos count: {len(saved_photos)}")
            print(f"  - fixtures count: {len(saved_fixtures)}")
            print(f"  - color_palette: {color_palette}")
            
            try:
                # Ensure we have valid data
                if not user_id:
                    raise ValueError("User ID is missing. Please log in again.")
                if not board_name or not board_name.strip():
                    raise ValueError("Board name is required.")
                
                print(f"[BOARD CREATE] Calling add_design_board_note with:")
                print(f"  user_id={user_id} (type: {type(user_id)})")
                print(f"  project_name='{board_name}'")
                print(f"  title='{board_title}'")
                print(f"  details='{combined_details[:100] if combined_details else None}...'")
                print(f"  photos={len(saved_photos)} items")
                print(f"  fixtures={len(saved_fixtures)} items")
                print(f"  color_palette={color_palette}")
                
                board_id = add_design_board_note(
                    user_id=user_id,
                    project_name=board_name.strip(),
                    title=board_title.strip() if board_title and board_title.strip() else None,
                    tags=None,
                    details=combined_details if combined_details and combined_details.strip() else None,
                    links=None,
                    photos=saved_photos if saved_photos else [],
                    files=[],
                    vision_statement=vision_statement.strip() if vision_statement and vision_statement.strip() else None,
                    color_palette=color_palette if color_palette else [],
                    board_template="collage",
                    label_style="sans-serif",
                    is_private=0,
                    fixtures=saved_fixtures if saved_fixtures else [],
                )
                
                if not board_id:
                    raise ValueError("Board was created but no ID was returned from database.")
                
                print(f"[BOARD CREATE SUCCESS] Board '{board_name}' created with ID {board_id}")
                
                # Verify the board was actually created by querying the database
                from database import list_homeowner_notes
                all_notes = list_homeowner_notes(user_id)
                matching_notes = [n for n in all_notes if n.get('project_name') == board_name or (hasattr(n, 'project_name') and n.project_name == board_name)]
                print(f"[BOARD CREATE VERIFY] Found {len(matching_notes)} notes with project_name='{board_name}'")
                
                verify_boards = get_design_boards_for_user(user_id)
                print(f"[BOARD CREATE VERIFY] All boards for user: {list(verify_boards.keys())}")
                
                if board_name not in verify_boards:
                    print(f"[BOARD CREATE WARNING] Board '{board_name}' not found in get_design_boards_for_user result!")
                    print(f"[BOARD CREATE WARNING] This might be a query issue, but the board should still exist.")
                
                # Force a small delay to ensure database commit is complete
                import time
                time.sleep(0.1)
                
                # Re-query boards to ensure they're fresh
                fresh_boards = get_design_boards_for_user(user_id)
                print(f"[BOARD CREATE] Fresh boards query after creation: {list(fresh_boards.keys())}")
                
                flash("✨ Beautiful board created!", "success")
                return redirect(url_for("homeowner_saved_notes", view=board_name))
            except ValueError as ve:
                print(f"[BOARD CREATE VALIDATION ERROR] {str(ve)}")
                flash(f"Validation error: {str(ve)}", "error")
                return redirect(url_for("homeowner_saved_notes"))
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"[BOARD CREATE ERROR] Failed to create board '{board_name}': {str(e)}")
                print(f"[BOARD CREATE ERROR] Error type: {type(e).__name__}")
                print(error_trace)
                flash(f"Could not create the board: {str(e)}", "error")
                return redirect(url_for("homeowner_saved_notes"))

        # ---------- EDIT BOARD ----------
        if action == "edit_board":
            board_name = (request.form.get("board_name") or "").strip()
            if not board_name:
                flash("Missing board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Remove photos
            remove_photos_list = request.form.getlist("remove_photos")
            if remove_photos_list:
                try:
                    remove_photos_from_board(user_id, board_name, remove_photos_list)
                    for p in remove_photos_list:
                        try:
                            ppath = BASE_DIR / "static" / p
                            if ppath.exists():
                                ppath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("Could not remove some photos.", "error")

            # Remove fixtures
            remove_fixtures_list = request.form.getlist("remove_fixtures")
            if remove_fixtures_list:
                try:
                    remove_fixtures_from_board(
                        user_id, board_name, remove_fixtures_list
                    )
                    for f in remove_fixtures_list:
                        try:
                            fpath = BASE_DIR / "static" / f
                            if fpath.exists():
                                fpath.unlink()
                        except Exception as file_error:
                            print(f"[FIXTURE REMOVAL] Could not delete file {f}: {file_error}")
                    flash("Fixtures removed successfully!", "success")
                except Exception as e:
                    import traceback
                    print(f"[FIXTURE REMOVAL ERROR] Failed to remove fixtures: {str(e)}")
                    print(traceback.format_exc())
                    flash(f"Could not remove some fixtures: {str(e)}", "error")

            # New photos
            new_photos = []
            files = request.files.getlist("new_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")

            # New fixtures
            new_fixtures = []
            fixture_files = request.files.getlist("new_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_fixtures.append(rel_path)
                except Exception:
                    flash(f"Could not save fixture: {safe_name}", "error")

            edit_title = (request.form.get("edit_title") or "").strip()
            edit_notes = (request.form.get("edit_notes") or "").strip()

            # New colors
            new_colors = request.form.getlist("new_colors[]")
            if new_colors:
                color_palette = [c for c in new_colors if c]
                try:
                    update_board_colors(user_id, board_name, color_palette)
                except Exception:
                    pass

            if new_photos or new_fixtures or edit_title or edit_notes:
                try:
                    # Get existing photos and fixtures to merge with new ones
                    existing_details_list = get_design_board_details(user_id, board_name)
                    existing_photos = []
                    existing_fixtures = []
                    
                    if existing_details_list and len(existing_details_list) > 0:
                        # Get all photos and fixtures from all notes in this board
                        for detail in existing_details_list:
                            detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
                            
                            # Get existing photos
                            existing_photos_json = detail_dict.get("photos") if isinstance(detail_dict, dict) else detail_dict.get("photos", None)
                            if existing_photos_json:
                                try:
                                    parsed_photos = json.loads(existing_photos_json) if isinstance(existing_photos_json, str) else existing_photos_json
                                    if isinstance(parsed_photos, list):
                                        existing_photos.extend(parsed_photos)
                                except Exception:
                                    pass
                            
                            # Get existing fixtures
                            existing_fixtures_json = detail_dict.get("fixtures") if isinstance(detail_dict, dict) else detail_dict.get("fixtures", None)
                            if existing_fixtures_json:
                                try:
                                    parsed_fixtures = json.loads(existing_fixtures_json) if isinstance(existing_fixtures_json, str) else existing_fixtures_json
                                    if isinstance(parsed_fixtures, list):
                                        existing_fixtures.extend(parsed_fixtures)
                                except Exception:
                                    pass
                    
                    # Merge existing with new (remove duplicates)
                    all_photos = list(dict.fromkeys(existing_photos + new_photos))  # Preserves order, removes duplicates
                    all_fixtures = list(dict.fromkeys(existing_fixtures + new_fixtures))
                    
                    # Add new note with merged photos and fixtures
                    add_design_board_note(
                        user_id=user_id,
                        project_name=board_name,
                        title=edit_title,
                        details=edit_notes,
                        photos=all_photos,
                        files=[],
                        fixtures=all_fixtures,
                    )
                    flash("Board updated successfully!", "success")
                    # Redirect to board detail page if we're coming from there
                    if request.referrer and '/design-boards/' in request.referrer:
                        return redirect(url_for('homeowner_design_board_view', board_name=board_name))
                    return redirect(url_for("homeowner_saved_notes", view=board_name))
                except Exception as e:
                    import traceback
                    print(f"[BOARD EDIT ERROR] Failed to update board: {str(e)}")
                    print(traceback.format_exc())
                    flash(f"Could not update board: {str(e)}", "error")
                    # Redirect to board detail page if we're coming from there
                    if request.referrer and '/design-boards/' in request.referrer:
                        return redirect(url_for('homeowner_design_board_view', board_name=board_name))

            return redirect(url_for("homeowner_saved_notes", view=board_name))

        # ---------- DELETE BOARD ----------
        if action == "delete_board":
            board_name = (request.form.get("board_name") or "").strip()
            print(f"[BOARD DELETE] Attempting to delete board: '{board_name}' for user {user_id}")
            if not board_name:
                flash("Board name is required for deletion.", "error")
                return redirect(url_for("homeowner_saved_notes"))
            
            try:
                # Get board details to delete associated files
                details_list = get_design_board_details(user_id, board_name)
                if details_list and len(details_list) > 0:
                    details = details_list[0]  # Get first detail record
                    
                    # Convert sqlite3.Row to dict (sqlite3.Row doesn't have .get() method)
                    details_dict = dict(details)
                    
                    # Delete photos
                    photos = details_dict.get("photos")
                    if photos:
                        try:
                            photos_list = json.loads(photos) if isinstance(photos, str) else photos
                            if isinstance(photos_list, list):
                                for photo in photos_list:
                                    try:
                                        file_path = BASE_DIR / "static" / photo
                                        if file_path.exists():
                                            file_path.unlink()
                                            print(f"[BOARD DELETE] Deleted photo: {photo}")
                                    except Exception as e:
                                        print(f"[BOARD DELETE] Error deleting photo {photo}: {e}")
                        except Exception as e:
                            print(f"[BOARD DELETE] Error parsing photos: {e}")
                    
                    # Delete fixtures
                    fixtures = details_dict.get("fixtures")
                    if fixtures:
                        try:
                            fixtures_list = json.loads(fixtures) if isinstance(fixtures, str) else fixtures
                            if isinstance(fixtures_list, list):
                                for fixture in fixtures_list:
                                    try:
                                        file_path = BASE_DIR / "static" / fixture
                                        if file_path.exists():
                                            file_path.unlink()
                                            print(f"[BOARD DELETE] Deleted fixture: {fixture}")
                                    except Exception as e:
                                        print(f"[BOARD DELETE] Error deleting fixture {fixture}: {e}")
                        except Exception as e:
                            print(f"[BOARD DELETE] Error parsing fixtures: {e}")
                
                # Delete from database
                delete_design_board(user_id, board_name)
                print(f"[BOARD DELETE] Successfully deleted board '{board_name}' from database")
                flash("Board deleted successfully.", "success")
            except Exception as e:
                import traceback
                print(f"[BOARD DELETE ERROR] Failed to delete board '{board_name}': {str(e)}")
                print(traceback.format_exc())
                flash(f"Could not delete that board: {str(e)}", "error")

            return redirect(url_for("homeowner_saved_notes"))

    # ---------- GET: LIST & VIEW BOARDS ----------
    raw_boards_dict = get_design_boards_for_user(user_id) or {}
    # Convert dict to list of board names for template iteration
    boards = list(raw_boards_dict.keys()) if raw_boards_dict else []
    print(f"[DEBUG][SAVED NOTES] Raw boards dict: {raw_boards_dict}")
    print(f"[DEBUG][SAVED NOTES] Boards list: {boards}")
    
    board_details = {}
    for board_name in boards:
        try:
            details = get_design_board_details(user_id, board_name)
            if details:
                # Convert Row objects to dicts if needed
                if isinstance(details, list) and len(details) > 0:
                    first_detail = details[0]
                    if hasattr(first_detail, 'keys'):
                        board_details[board_name] = {
                            "project_name": board_name,
                            "photos": json.loads(first_detail.get('photos', '[]') or '[]') if first_detail.get('photos') else [],
                            "notes": [first_detail.get('details', '')] if first_detail.get('details') else [],
                            "files": json.loads(first_detail.get('files', '[]') or '[]') if first_detail.get('files') else [],
                            "color_palette": json.loads(first_detail.get('color_palette', '[]') or '[]') if first_detail.get('color_palette') else [],
                            "vision_statement": first_detail.get('vision_statement', ''),
                            "title": first_detail.get('title', ''),
                        }
                    else:
                        board_details[board_name] = {
                            "project_name": board_name,
                            "photos": [],
                            "notes": [],
                            "files": [],
                        }
                else:
                    board_details[board_name] = {
                        "project_name": board_name,
                        "photos": [],
                        "notes": [],
                        "files": [],
                    }
            else:
                board_details[board_name] = {
                    "project_name": board_name,
                    "photos": [],
                    "notes": [],
                    "files": [],
                }
        except Exception as e:
            print(f"[DEBUG][SAVED NOTES] Error getting details for board '{board_name}': {e}")
            import traceback
            print(traceback.format_exc())
            board_details[board_name] = {
                "project_name": board_name,
                "photos": [],
                "notes": [],
                "files": [],
            }

    selected_board = request.args.get("view")
    selected_details = board_details.get(selected_board) if selected_board else None

    return render_template(
        "homeowner/saved_notes.html",
        brand_name=FRONT_BRAND_NAME,
        boards=boards,
        board_details=board_details,
        selected_board=selected_board,
        selected_details=selected_details,
    )




@app.route("/homeowner/design-boards/<path:board_name>", methods=["GET"])
def homeowner_design_board_view(board_name):
    """Display a dedicated detail page for a single design board."""
    user_id = get_current_user_id()
    details_list = get_design_board_details(user_id, board_name)

    if not details_list:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    # Aggregate all photos, fixtures, and other data from all notes in this board
    all_photos = []
    all_fixtures = []
    all_files = []
    color_palette = []
    vision_statement = None
    title = None
    details_text = []
    
    for detail in details_list:
        detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
        
        # Collect photos from all notes
        photos_json = detail_dict.get('photos') or '[]'
        if photos_json:
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list):
                    all_photos.extend(photos)
            except Exception:
                pass
        
        # Collect fixtures from all notes
        fixtures_json = detail_dict.get('fixtures') or '[]'
        if fixtures_json:
            try:
                fixtures = json.loads(fixtures_json) if isinstance(fixtures_json, str) else fixtures_json
                if isinstance(fixtures, list):
                    all_fixtures.extend(fixtures)
            except Exception:
                pass
        
        # Collect files
        files_json = detail_dict.get('files') or '[]'
        if files_json:
            try:
                files = json.loads(files_json) if isinstance(files_json, str) else files_json
                if isinstance(files, list):
                    all_files.extend(files)
            except Exception:
                pass
        
        # Get color palette (from most recent note)
        color_palette_json = detail_dict.get('color_palette') or '[]'
        if color_palette_json and not color_palette:
            try:
                color_palette = json.loads(color_palette_json) if isinstance(color_palette_json, str) else color_palette_json
            except Exception:
                pass
        
        # Get vision statement (from most recent note)
        if not vision_statement and detail_dict.get('vision_statement'):
            vision_statement = detail_dict.get('vision_statement')
        
        # Get title (from most recent note)
        if not title and detail_dict.get('title'):
            title = detail_dict.get('title')
        
        # Collect details text (only unique, non-empty details)
        if detail_dict.get('details'):
            detail_text = detail_dict.get('details').strip()
            if detail_text and detail_text not in details_text:
                details_text.append(detail_text)
    
    # Remove duplicates while preserving order
    all_photos = list(dict.fromkeys(all_photos))
    all_fixtures = list(dict.fromkeys(all_fixtures))
    all_files = list(dict.fromkeys(all_files))
    
    # Combine all unique details with newlines for readability
    combined_details = '\n\n'.join(details_text) if details_text else None
    
    # Create aggregated details dict for template
    aggregated_details = {
        'photos': all_photos,
        'fixtures': all_fixtures,
        'files': all_files,
        'color_palette': color_palette if isinstance(color_palette, list) else [],
        'vision_statement': vision_statement,
        'title': title,
        'details': combined_details,
    }

    return render_template(
        "homeowner/board_detail.html",
        selected_board=board_name,
        selected_details=aggregated_details,
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/design-boards/<path:board_name>/download")
def homeowner_design_board_download(board_name):
    """Render a print-optimized view of a single board."""
    user_id = get_current_user_id()
    details_list = get_design_board_details(user_id, board_name)
    if not details_list:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    # Aggregate all photos, fixtures, and other data from all notes in this board
    # (same logic as homeowner_design_board_view)
    all_photos = []
    all_fixtures = []
    all_files = []
    color_palette = []
    vision_statement = None
    title = None
    details_text = []
    
    for detail in details_list:
        detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
        
        # Collect photos from all notes
        photos_json = detail_dict.get('photos') or '[]'
        if photos_json:
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list):
                    all_photos.extend(photos)
            except Exception:
                pass
        
        # Collect fixtures from all notes
        fixtures_json = detail_dict.get('fixtures') or '[]'
        if fixtures_json:
            try:
                fixtures = json.loads(fixtures_json) if isinstance(fixtures_json, str) else fixtures_json
                if isinstance(fixtures, list):
                    all_fixtures.extend(fixtures)
            except Exception:
                pass
        
        # Collect files
        files_json = detail_dict.get('files') or '[]'
        if files_json:
            try:
                files = json.loads(files_json) if isinstance(files_json, str) else files_json
                if isinstance(files, list):
                    all_files.extend(files)
            except Exception:
                pass
        
        # Get color palette (from most recent note)
        color_palette_json = detail_dict.get('color_palette') or '[]'
        if color_palette_json and not color_palette:
            try:
                color_palette = json.loads(color_palette_json) if isinstance(color_palette_json, str) else color_palette_json
            except Exception:
                pass
        
        # Get vision statement (from most recent note)
        if not vision_statement and detail_dict.get('vision_statement'):
            vision_statement = detail_dict.get('vision_statement')
        
        # Get title (from most recent note)
        if not title and detail_dict.get('title'):
            title = detail_dict.get('title')
        
        # Collect details text (only unique, non-empty details)
        if detail_dict.get('details'):
            detail_text = detail_dict.get('details').strip()
            if detail_text and detail_text not in details_text:
                details_text.append(detail_text)
    
    # Remove duplicates while preserving order
    all_photos = list(dict.fromkeys(all_photos))
    all_fixtures = list(dict.fromkeys(all_fixtures))
    all_files = list(dict.fromkeys(all_files))
    
    # Combine all unique details with newlines for readability
    combined_details = '\n\n'.join(details_text) if details_text else None
    
    # Create aggregated details dict for template
    aggregated_details = {
        'photos': all_photos,
        'fixtures': all_fixtures,
        'files': all_files,
        'color_palette': color_palette if isinstance(color_palette, list) else [],
        'vision_statement': vision_statement,
        'title': title,
        'details': combined_details,
        'notes': details_list,  # Include raw notes for the template
    }

    html = render_template(
        "homeowner/board_print.html",
        selected_board=board_name,
        selected_details=aggregated_details,
        brand_name=FRONT_BRAND_NAME,
    )

    try:
        from weasyprint import HTML

        pdf = HTML(string=html, base_url=str(BASE_DIR / "static")).write_pdf()
        safe_filename = board_name.replace("/", "_")
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}.pdf"'
            },
        )
    except ImportError:
        # WeasyPrint not installed - return HTML as fallback
        return html
    except Exception as e:
        # PDF generation failed - log error and return HTML
        import traceback
        print(f"[PDF DOWNLOAD ERROR] Failed to generate PDF: {str(e)}")
        print(traceback.format_exc())
        return html


@app.route("/homeowner/design-boards/<path:board_name>/duplicate", methods=["POST"])
def homeowner_design_board_duplicate(board_name):
    """Duplicate an existing board with a new name."""
    user_id = get_current_user_id()
    new_name = request.form.get("new_name", f"{board_name} (Copy)").strip()

    if not new_name:
        flash("New board name is required.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))

    try:
        duplicate_design_board(user_id, board_name, new_name)
        flash(f"✨ Board duplicated as '{new_name}'!", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=new_name))
    except Exception:
        flash("Could not duplicate board.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/design-boards/<path:board_name>/privacy", methods=["POST"])
def homeowner_design_board_privacy(board_name):
    """Toggle privacy settings for a board."""
    user_id = get_current_user_id()
    is_private = int(request.form.get("is_private", 0))

    shareable_link = None
    if not is_private:
        shareable_link = secrets.token_urlsafe(16)

    try:
        update_board_privacy(user_id, board_name, is_private, shareable_link)
        status = "private" if is_private else "shareable"
        flash(f"Board is now {status}.", "success")
    except Exception:
        flash("Could not update privacy settings.", "error")

    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/design-boards/<path:board_name>/template", methods=["POST"])
def homeowner_design_board_template(board_name):
    """Change the board template style."""
    user_id = get_current_user_id()
    template = request.form.get("template", "collage")

    if template not in ["collage", "grid", "editorial"]:
        template = "collage"

    try:
        update_board_template(user_id, board_name, template)
        flash(f"Board template changed to {template}.", "success")
    except Exception:
        flash("Could not update template.", "error")

    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/crop-photo", methods=["POST"])
def homeowner_crop_photo():
    """Crop a photo and replace the original."""
    try:
        user_id = get_current_user_id()
        board_name = request.form.get("board_name")
        original_path = request.form.get("original_path")
        cropped_file = request.files.get("cropped_image")

        if not all([board_name, original_path, cropped_file]):
            return jsonify({"success": False, "error": "Missing data"})

        # Verify user owns this board and photo exists
        details_list = get_design_board_details(user_id, board_name)
        if not details_list:
            return jsonify({"success": False, "error": "Board not found"})
        
        # Check if photo exists in any note in the board
        photo_found = False
        for detail in details_list:
            detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
            photos_json = detail_dict.get('photos') or '[]'
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list) and original_path in photos:
                    photo_found = True
                    break
            except Exception:
                pass
        
        if not photo_found:
            return jsonify({"success": False, "error": "Photo not found in board"})

        # Save cropped image over original
        file_path = BASE_DIR / "static" / original_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        cropped_file.save(file_path)

        return jsonify({"success": True})
    except Exception as e:
        import traceback
        print(f"Crop error: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


# ----- HOME TIMELINE & DOCUMENTS -----
@app.route("/homeowner/home-timeline", methods=["GET", "POST"])
def homeowner_home_timeline():
    user_id = get_current_user_id()

    if request.method == "POST":
        title = request.form.get("title")
        category = request.form.get("category")
        event_date = request.form.get("event_date")
        cost = request.form.get("cost")
        notes = request.form.get("notes")
        files = request.files.getlist("files")

        saved_files = []
        for f in files:
            if f.filename:
                filename = secure_filename(f.filename)
                filepath = UPLOAD_TIMELINE / filename
                f.save(filepath)
                saved_files.append(filename)

        add_timeline_event(user_id, event_date, title, category, cost, notes, saved_files)
        return redirect(url_for("homeowner_home_timeline"))

    events = list_timeline_events(user_id)
    return render_template(
        "homeowner/home_timeline.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


@app.route("/homeowner/home-timeline/delete/<int:event_id>")
def homeowner_timeline_delete(event_id):
    delete_timeline_event(event_id, get_current_user_id())
    return redirect(url_for("homeowner_home_timeline"))


@app.route("/homeowner/home-timeline/print")
def homeowner_timeline_print():
    events = list_timeline_events(get_current_user_id())
    return render_template(
        "homeowner/home_timeline_print.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


@app.route("/homeowner/documents/<int:doc_id>/view")
def homeowner_document_view(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    # If file is in R2, redirect to R2 URL
    if row.get("r2_key"):
        try:
            file_url = get_file_url_from_r2(row["r2_key"])
            return redirect(file_url)
        except Exception as e:
            flash(f"Could not retrieve file: {str(e)}", "error")
            return redirect(url_for("homeowner_upload_documents"))

    # Fallback to local file
    return send_from_directory(
        HOMEOWNER_DOCS_DIR, row["file_name"], as_attachment=False
    )


@app.route("/homeowner/documents/<int:doc_id>/replace", methods=["GET", "POST"])
def homeowner_document_replace(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(request.url)

        safe_name = secure_filename(file.filename)
        save_path = HOMEOWNER_DOCS_DIR / safe_name
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        file.save(save_path)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE homeowner_documents
            SET file_name = ?, uploaded_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                safe_name,
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                doc_id,
                user_id,
            ),
        )
        conn.commit()
        conn.close()

        flash("Document updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    return render_template(
        "homeowner/document_replace.html",
        document=row,
    )


@app.route("/homeowner/upload-documents", methods=["GET", "POST"])
def homeowner_upload_documents():
    user_id = get_current_user_id()
    docs = list_homeowner_documents(user_id)
    events = list_timeline_events(user_id)

    # DELETE FILE
    if request.method == "POST" and request.form.get("delete_id"):
        delete_id = request.form["delete_id"]
        delete_homeowner_document(delete_id)
        flash("Document removed.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # REATTACH / REUPLOAD
    if (
        request.method == "POST"
        and request.form.get("reattach_id")
        and request.files.get("file")
    ):
        doc_id = request.form["reattach_id"]
        new_file = request.files["file"]
        save_name = secure_filename(new_file.filename)
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        new_file.save(HOMEOWNER_DOCS_DIR / save_name)
        update_homeowner_document_file(doc_id, save_name)
        flash("File updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # NORMAL UPLOAD
    if request.method == "POST" and request.files.get("file"):
        file = request.files["file"]
        category = request.form.get("category", "Other")
        title = request.form.get("title", "").strip() or file.filename

        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(url_for("homeowner_upload_documents"))

        filename = secure_filename(file.filename)

        # If using R2, upload there; else save locally
        if is_r2_enabled() and R2_CLIENT:
            r2_key = f"homeowner_docs/{user_id}/{uuid4().hex}_{filename}"
            upload_file_to_r2(file, r2_key)
            stored_name = filename  # For DB reference, still keep original name
        else:
            HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
            save_path = HOMEOWNER_DOCS_DIR / filename
            file.save(save_path)
            r2_key = None
            stored_name = filename

        add_homeowner_document(
            user_id=user_id,
            title=title,
            category=category,
            file_name=stored_name,
            r2_key=r2_key,
        )
        flash("Document uploaded.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    return render_template(
        "homeowner/upload_documents.html",
        brand_name=FRONT_BRAND_NAME,
        documents=docs,
        events=events,
    )


# ----- VALUE & EQUITY -----


@app.route("/homeowner/value/equity-overview", methods=["GET", "POST"])
def homeowner_value_equity_overview():
    """Homebot-powered equity page - shows Homebot widget if agent/lender has configured it."""
    from database import get_homeowner_professionals, get_user_profile, get_user_by_id
    
    user = get_current_user()
    if not user:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))
    
    if user.get("role") != "homeowner":
        flash("This page is for homeowners only.", "error")
        return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
    
    homeowner_id = user["id"]
    
    # Handle POST requests for updating loan details
    if request.method == "POST":
        print(f"\n{'='*60}")
        print(f"[LOAN UPDATE] POST request received for user {homeowner_id}")
        print(f"[LOAN UPDATE] Form data keys: {list(request.form.keys())}")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
        print(f"{'='*60}\n")
        from database import get_primary_property, upsert_homeowner_snapshot_for_property
        
        # Get property ID
        primary_property = get_primary_property(homeowner_id)
        if not primary_property:
            flash("Please add a property first before updating loan details.", "error")
            return redirect(url_for("homeowner_value_equity_overview"))
        
        property_id = primary_property.get('id')
        
        # Parse form data - only update fields that are actually provided (not empty)
        def safe_float(val):
            if not val or val == "":
                return None
            try:
                return float(str(val).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                return None
        
        # Get form values - only update fields that have actual values (not empty)
        # Empty form fields should preserve existing data
        def get_form_value(field_name):
            val = request.form.get(field_name, "").strip()
            return val if val else None
        
        form_value_estimate = get_form_value("value_estimate")
        form_loan_balance = get_form_value("loan_balance")
        form_loan_rate = get_form_value("loan_rate")
        form_loan_payment = get_form_value("loan_payment")
        form_loan_term_years = get_form_value("loan_term_years")
        form_loan_start_date = get_form_value("loan_start_date")
        form_property_tax = get_form_value("property_tax_monthly")
        form_insurance = get_form_value("homeowners_insurance_monthly")
        form_pmi = get_form_value("pmi_monthly")
        
        # Convert to appropriate types, but only if value was provided
        # If None, the function will preserve existing data
        value_estimate = safe_float(form_value_estimate) if form_value_estimate else None
        loan_balance = safe_float(form_loan_balance) if form_loan_balance else None
        loan_rate = safe_float(form_loan_rate) if form_loan_rate else None
        loan_payment = safe_float(form_loan_payment) if form_loan_payment else None
        loan_term_years = safe_float(form_loan_term_years) if form_loan_term_years else None
        loan_start_date = form_loan_start_date if form_loan_start_date else None
        property_tax_monthly = safe_float(form_property_tax) if form_property_tax else None
        homeowners_insurance_monthly = safe_float(form_insurance) if form_insurance else None
        pmi_monthly = safe_float(form_pmi) if form_pmi else None
        
        # Update snapshot - function will preserve existing data for None values
        try:
            print(f"[LOAN UPDATE] Updating snapshot for user {homeowner_id}, property {property_id}")
            print(f"[LOAN UPDATE] Values: value={value_estimate}, balance={loan_balance}, rate={loan_rate}, payment={loan_payment}, term={loan_term_years}, start_date={loan_start_date}")
            print(f"[LOAN UPDATE] Additional: tax={property_tax_monthly}, insurance={homeowners_insurance_monthly}, PMI={pmi_monthly}")
            
            upsert_homeowner_snapshot_for_property(
                user_id=homeowner_id,
                property_id=property_id,
                value_estimate=value_estimate,
                loan_balance=loan_balance,
                loan_rate=loan_rate,
                loan_payment=loan_payment,
                loan_term_years=loan_term_years,
                loan_start_date=loan_start_date,
                property_tax_monthly=property_tax_monthly,
                homeowners_insurance_monthly=homeowners_insurance_monthly,
                pmi_monthly=pmi_monthly,
            )
            
            print(f"[LOAN UPDATE] Successfully updated snapshot")
            flash("Loan details updated successfully! Your equity numbers have been recalculated.", "success")
            return redirect(url_for("homeowner_value_equity_overview"))
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[LOAN UPDATE] ERROR: {str(e)}")
            print(error_trace)
            flash(f"Error updating loan details: {str(e)}", "error")
            # Continue to render the form so user can see the error
    
    # Get homeowner's professionals (agents and lenders)
    professionals = get_homeowner_professionals(homeowner_id)
    
    # Get market rates from lender (precedence) or agent, with defaults
    market_rates = {
        'va_rate_30yr': 6.1,
        'fha_rate_30yr': 6.1,
        'conventional_rate_30yr': 6.1
    }
    lender_profile = None
    agent_profile = None
    
    # Find lender first (lender takes precedence)
    for prof in professionals:
        prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
        prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
        prof_role = prof_dict.get('professional_role') or prof_dict.get('professional_type')
        if prof_id and prof_role == 'lender':
            lender_profile = get_user_profile(prof_id)
            if lender_profile:
                lender_dict = dict(lender_profile) if hasattr(lender_profile, 'keys') else lender_profile
                if lender_dict.get('va_rate_30yr'):
                    market_rates['va_rate_30yr'] = float(lender_dict.get('va_rate_30yr'))
                if lender_dict.get('fha_rate_30yr'):
                    market_rates['fha_rate_30yr'] = float(lender_dict.get('fha_rate_30yr'))
                if lender_dict.get('conventional_rate_30yr'):
                    market_rates['conventional_rate_30yr'] = float(lender_dict.get('conventional_rate_30yr'))
                break
    
    # If no lender rates, check agent
    if not lender_profile or (market_rates['va_rate_30yr'] == 6.1 and market_rates['fha_rate_30yr'] == 6.1 and market_rates['conventional_rate_30yr'] == 6.1):
        for prof in professionals:
            prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
            prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
            prof_role = prof_dict.get('professional_role') or prof_dict.get('professional_type')
            if prof_id and prof_role == 'agent':
                agent_profile = get_user_profile(prof_id)
                if agent_profile:
                    agent_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') else agent_profile
                    # Only use agent rates if lender rates weren't set
                    if not lender_profile:
                        if agent_dict.get('va_rate_30yr'):
                            market_rates['va_rate_30yr'] = float(agent_dict.get('va_rate_30yr'))
                        if agent_dict.get('fha_rate_30yr'):
                            market_rates['fha_rate_30yr'] = float(agent_dict.get('fha_rate_30yr'))
                        if agent_dict.get('conventional_rate_30yr'):
                            market_rates['conventional_rate_30yr'] = float(agent_dict.get('conventional_rate_30yr'))
                    break
    
    # Find the first professional (agent preferred, then lender) with a Homebot widget ID
    homebot_widget_id = None
    professional_info = None
    
    # Prefer agent over lender
    for prof in professionals:
        prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
        prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
        if prof_id:
            profile = get_user_profile(prof_id)
            if profile:
                profile_dict = dict(profile) if hasattr(profile, 'keys') else profile
                widget_id = profile_dict.get('homebot_widget_id')
                if widget_id:
                    # Clean the widget ID - remove any whitespace
                    widget_id = str(widget_id).strip()
                    # If widget_id contains HTML/embed code, extract just the ID
                    if '<' in widget_id or 'Homebot(' in widget_id:
                        # Try to extract the ID from embed code
                        import re
                        id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                        if id_match:
                            widget_id = id_match.group(1)
                            print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                    if widget_id:
                        homebot_widget_id = widget_id
                    professional_info = {
                        'name': prof_dict.get('name') or profile_dict.get('name'),
                        'email': prof_dict.get('email'),
                        'role': prof_dict.get('professional_role') or 'agent',
                        'brokerage_name': profile_dict.get('brokerage_name'),
                        'team_name': profile_dict.get('team_name'),
                        'professional_photo': profile_dict.get('professional_photo'),
                    }
                    # Prefer agent, so if we found an agent, break
                    if prof_dict.get('professional_role') == 'agent' or prof_dict.get('professional_type') == 'agent':
                        break
    
    # Fallback: check agent_id/lender_id columns if no professionals found
    if not homebot_widget_id:
        homeowner_user = get_user_by_id(homeowner_id)
        if homeowner_user:
            homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') else homeowner_user
            # Try agent first
            agent_id = homeowner_dict.get("agent_id")
            if agent_id:
                agent_profile = get_user_profile(agent_id)
                if agent_profile:
                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') else agent_profile
                    widget_id = profile_dict.get('homebot_widget_id')
                    if widget_id:
                        # Clean the widget ID - remove any whitespace
                        widget_id = str(widget_id).strip()
                        # If widget_id contains HTML/embed code, extract just the ID
                        if '<' in widget_id or 'Homebot(' in widget_id:
                            # Try to extract the ID from embed code
                            import re
                            id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                            if id_match:
                                widget_id = id_match.group(1)
                                print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                        if widget_id:
                            homebot_widget_id = widget_id
                        agent_user = get_user_by_id(agent_id)
                        if agent_user:
                            agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') else agent_user
                            professional_info = {
                                'name': agent_dict.get('name'),
                                'email': agent_dict.get('email'),
                                'role': 'agent',
                                'brokerage_name': profile_dict.get('brokerage_name'),
                                'team_name': profile_dict.get('team_name'),
                                'professional_photo': profile_dict.get('professional_photo'),
                            }
            # Try lender if no agent
            if not homebot_widget_id:
                lender_id = homeowner_dict.get("lender_id")
                if lender_id:
                    lender_profile = get_user_profile(lender_id)
                    if lender_profile:
                        profile_dict = dict(lender_profile) if hasattr(lender_profile, 'keys') else lender_profile
                        widget_id = profile_dict.get('homebot_widget_id')
                        if widget_id:
                            # Clean the widget ID - remove any whitespace
                            widget_id = str(widget_id).strip()
                            # If widget_id contains HTML/embed code, extract just the ID
                            if '<' in widget_id or 'Homebot(' in widget_id:
                                # Try to extract the ID from embed code
                                import re
                                id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                                if id_match:
                                    widget_id = id_match.group(1)
                                    print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                            if widget_id:
                                homebot_widget_id = widget_id
                            lender_user = get_user_by_id(lender_id)
                            if lender_user:
                                lender_dict = dict(lender_user) if hasattr(lender_user, 'keys') else lender_user
                                professional_info = {
                                    'name': lender_dict.get('name'),
                                    'email': lender_dict.get('email'),
                                    'role': 'lender',
                                    'brokerage_name': profile_dict.get('brokerage_name'),
                                    'team_name': profile_dict.get('team_name'),
                                    'professional_photo': profile_dict.get('professional_photo'),
                                }

    # Get homeowner's email and property address to pass to Homebot widget
    homeowner_data = {}
    homeowner_user = get_user_by_id(homeowner_id)
    if homeowner_user:
        homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') else homeowner_user
        homeowner_email = homeowner_dict.get('email')
        if homeowner_email:
            homeowner_data['email'] = homeowner_email
        
        # Get primary property address, or first property if no primary
        from database import get_primary_property, get_user_properties
        primary_property = get_primary_property(homeowner_id)
        if primary_property and primary_property.get('address'):
            homeowner_data['address'] = primary_property.get('address')
        else:
            # Fallback to first property if no primary
            all_properties = get_user_properties(homeowner_id)
            if all_properties and len(all_properties) > 0 and all_properties[0].get('address'):
                homeowner_data['address'] = all_properties[0].get('address')
    
    # Get all properties and current property
    from database import get_primary_property, get_homeowner_snapshot_for_property, get_snapshot_history, get_user_properties, get_property_by_id
    all_properties = get_user_properties(homeowner_id)
    primary_property = get_primary_property(homeowner_id)
    
    # If no properties exist, create a default one
    if not all_properties or len(all_properties) == 0:
        if not primary_property:
            # Create default property
            default_address = homeowner_data.get('address', 'My Home') if homeowner_data else 'My Home'
            property_id = add_property(homeowner_id, default_address, None, "primary")
            primary_property = get_property_by_id(property_id)
            all_properties = get_user_properties(homeowner_id)
    
    # Get current property - ensure it's a dict
    current_property = None
    if primary_property:
        current_property = dict(primary_property) if hasattr(primary_property, 'keys') and not isinstance(primary_property, dict) else primary_property
    elif all_properties and len(all_properties) > 0:
        first_prop = all_properties[0]
        current_property = dict(first_prop) if hasattr(first_prop, 'keys') and not isinstance(first_prop, dict) else first_prop
    
    # Get current property ID safely
    current_property_id = None
    if current_property:
        if isinstance(current_property, dict):
            current_property_id = current_property.get('id')
        elif hasattr(current_property, 'get'):
            current_property_id = current_property.get('id')
        elif hasattr(current_property, 'id'):
            current_property_id = current_property.id
    
    # Get homeowner snapshot data (synced from Homebot webhook)
    snapshot_data = None
    snapshot_history = []
    if current_property_id:
        try:
            snapshot_data = get_homeowner_snapshot_for_property(homeowner_id, current_property_id)
            # Convert to dict if it's a Row object
            if snapshot_data and hasattr(snapshot_data, 'keys') and not isinstance(snapshot_data, dict):
                snapshot_data = dict(snapshot_data)
            # Calculate equity if we have value and loan balance
            if snapshot_data and snapshot_data.get('value_estimate') and snapshot_data.get('loan_balance'):
                snapshot_data['equity_estimate'] = snapshot_data.get('value_estimate') - snapshot_data.get('loan_balance')
            # Get historical snapshots
            try:
                snapshot_history = get_snapshot_history(homeowner_id, current_property_id, limit=24)
            except Exception as e:
                print(f"[HOMEBOT] Error getting snapshot history: {e}")
                snapshot_history = []
        except Exception as e:
            print(f"[HOMEBOT] Error getting snapshot data: {e}")
            import traceback
            print(traceback.format_exc())
            snapshot_data = None
            snapshot_history = []
    
    # Debug logging
    print(f"[HOMEBOT] Widget ID found: {homebot_widget_id is not None}")
    if homebot_widget_id:
        print(f"[HOMEBOT] Widget ID value: {homebot_widget_id[:20]}... (length: {len(homebot_widget_id)})")
    print(f"[HOMEBOT] Professional Info: {professional_info}")
    print(f"[HOMEBOT] Homeowner Data: {homeowner_data}")
    print(f"[HOMEBOT] Snapshot Data: {snapshot_data}")
    print(f"[HOMEBOT] Properties: {len(all_properties) if all_properties else 0} total, current: {current_property_id}")
    
    # Ensure all variables are properly formatted for template
    # Convert all properties to dicts
    properties_list = []
    for prop in (all_properties or []):
        if hasattr(prop, 'keys') and not isinstance(prop, dict):
            properties_list.append(dict(prop))
        elif isinstance(prop, dict):
            properties_list.append(prop)
        else:
            properties_list.append(prop)
    
    # Ensure current_property is a dict
    if current_property and hasattr(current_property, 'keys') and not isinstance(current_property, dict):
        current_property = dict(current_property)
    elif not current_property:
        current_property = {}
    
    # Ensure snapshot_data is a dict
    if snapshot_data and hasattr(snapshot_data, 'keys') and not isinstance(snapshot_data, dict):
        snapshot_data = dict(snapshot_data)
    
    # Render Homebot-powered equity page
    try:
        response = make_response(render_template(
            "homeowner/value_equity_homebot.html",
            brand_name=FRONT_BRAND_NAME,
            homebot_widget_id=homebot_widget_id,
            professional_info=professional_info,
            homeowner_data=homeowner_data or {},
            market_rates=market_rates,
            snapshot=snapshot_data,
            snapshot_history=snapshot_history or [],
            properties=properties_list,
            current_property=current_property or {},
            current_property_id=current_property_id,
        ))
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[HOMEBOT] ERROR rendering template: {str(e)}")
        print(error_trace)
        flash(f"Error loading equity page: {str(e)}", "error")
        return redirect(url_for("homeowner_overview"))
    
    # Set CSP headers to allow Homebot iframe (only if widget is present)
    # VERY permissive CSP to ensure Homebot widget works fully (address autocomplete, form submission, etc.)
    if homebot_widget_id:
        response.headers['Content-Security-Policy'] = (
            "default-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://static.cloudflareinsights.com; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://maps.googleapis.com https://static.cloudflareinsights.com; "
            "frame-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com data: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://*.homebotapp.com https://*.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://*.homebotapp.com data:; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://static.cloudflareinsights.com https://mikasa.homebotapp.com wss: ws:; "
            "form-action 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.googleapis.com; "
            "frame-ancestors 'self'; "
            "worker-src 'self' blob: https://*.homebotapp.com; "
            "manifest-src 'self' https://*.homebotapp.com;"
        )
    
    return response


@app.route("/test-board-save")
def test_board_save():
    """Test route to verify board saving works."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    
    user_id = user.get("id")
    from database import add_design_board_note, get_design_boards_for_user
    
    try:
        # Try to create a test board
        test_board_name = f"TEST_BOARD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        board_id = add_design_board_note(
            user_id=user_id,
            project_name=test_board_name,
            title="Test Board",
            details="This is a test board",
            photos=[],
            files=[],
            vision_statement=None,
            color_palette=[],
            board_template="collage",
            label_style="sans-serif",
            is_private=0,
            fixtures=[],
        )
        
        # Verify it was created
        boards = get_design_boards_for_user(user_id)
        
        return jsonify({
            "success": True,
            "board_id": board_id,
            "board_name": test_board_name,
            "boards_found": list(boards.keys()),
            "test_board_in_list": test_board_name in boards
        })
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/test-homebot")
def test_homebot():
    """Minimal test page for Homebot widget - use this to verify widget works in isolation."""
    from database import get_homeowner_professionals, get_user_profile, get_user_by_id
    
    user = get_current_user()
    if not user:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))
    
    if user.get("role") != "homeowner":
        flash("This page is for homeowners only.", "error")
        return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
    
    homeowner_id = user["id"]
    
    # Get homeowner's professionals (agents and lenders)
    professionals = get_homeowner_professionals(homeowner_id)
    
    # Find the first professional (agent preferred, then lender) with a Homebot widget ID
    homebot_widget_id = None
    
    # Prefer agent over lender
    for prof in professionals:
        prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
        prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
        if prof_id:
            profile = get_user_profile(prof_id)
            if profile:
                profile_dict = dict(profile) if hasattr(profile, 'keys') else profile
                widget_id = profile_dict.get('homebot_widget_id')
                if widget_id:
                    widget_id = str(widget_id).strip()
                    if widget_id:
                        homebot_widget_id = widget_id
                        # Prefer agent, so if we found an agent, break
                        if prof_dict.get('professional_role') == 'agent' or prof_dict.get('professional_type') == 'agent':
                            break
    
    # Fallback: check agent_id/lender_id columns if no professionals found
    if not homebot_widget_id:
        homeowner_user = get_user_by_id(homeowner_id)
        if homeowner_user:
            homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') else homeowner_user
            # Try agent first
            agent_id = homeowner_dict.get("agent_id")
            if agent_id:
                agent_profile = get_user_profile(agent_id)
                if agent_profile:
                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') else agent_profile
                    widget_id = profile_dict.get('homebot_widget_id')
                    if widget_id:
                        widget_id = str(widget_id).strip()
                        if widget_id:
                            homebot_widget_id = widget_id
            # Try lender if no agent
            if not homebot_widget_id:
                lender_id = homeowner_dict.get("lender_id")
                if lender_id:
                    lender_profile = get_user_profile(lender_id)
                    if lender_profile:
                        profile_dict = dict(lender_profile) if hasattr(lender_profile, 'keys') else lender_profile
                        widget_id = profile_dict.get('homebot_widget_id')
                        if widget_id:
                            widget_id = str(widget_id).strip()
                            if widget_id:
                                homebot_widget_id = widget_id
    
    # Render test page with minimal CSP
    response = make_response(render_template(
        "test_homebot.html",
        homebot_widget_id=homebot_widget_id or '',
    ))
    
    # Very permissive CSP for testing
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com; "
        "frame-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://*.homebotapp.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com wss: ws:; "
        "form-action 'self' https://embed.homebotapp.com https://*.homebotapp.com;"
    )
    
    return response


@app.route("/homeowner/add-property", methods=["POST"])
def homeowner_add_property():
    """Add a new property for the homeowner."""
    user = get_current_user()
    if not user:
        flash("Please log in to add a property.", "warning")
        return redirect(url_for("login"))

    address = request.form.get("property_address", "").strip()
    if not address:
        flash("Property address is required.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    estimated_value = None
    value_str = request.form.get("estimated_value", "").strip()
    if value_str:
        try:
            estimated_value = float(value_str.replace(",", ""))
        except Exception:
            pass

    property_type = request.form.get("property_type", "primary").strip()

    property_id = add_property(user["id"], address, estimated_value, property_type)
    set_primary_property(user["id"], property_id)

    flash(f"Property '{address}' added successfully!", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


@app.route("/homeowner/switch-property", methods=["POST"])
def homeowner_switch_property():
    """Switch to a different property."""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    property_id = request.form.get("property_id")
    if not property_id:
        flash("No property selected.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    try:
        property_id = int(property_id)
    except Exception:
        flash("Invalid property ID.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("Property not found.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    set_primary_property(user["id"], property_id)

    flash(f"Switched to {prop['address']}", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


@app.route("/homeowner/update-property-address", methods=["POST"])
def homeowner_update_property_address():
    """Update the address of a property."""
    user = get_current_user()
    if not user:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))
    
    property_id = request.form.get("property_id")
    new_address = request.form.get("address", "").strip()
    
    if not property_id or not new_address:
        flash("Property ID and address are required.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    try:
        property_id = int(property_id)
    except Exception:
        flash("Invalid property ID.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Verify property belongs to user
    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("Property not found.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Update address
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE properties SET address = ? WHERE id = ? AND user_id = ?",
        (new_address, property_id, user["id"])
    )
    conn.commit()
    conn.close()
    
    flash(f"Address updated to {new_address}", "success")
    return redirect(url_for("homeowner_value_equity_overview"))


# ----- RENOVATION & IMPROVEMENT -----
@app.route("/homeowner/reno/planner", methods=["GET", "POST"])
def homeowner_reno_planner():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("project_name", "").strip()
        budget_raw = (
            request.form.get("project_budget", "").replace(",", "").strip()
        )
        status = request.form.get("project_status", "Planning").strip()
        category = request.form.get("project_category", "Other").strip()  # Get category, default to "Other"
        notes = request.form.get("project_notes", "").strip()

        # Convert budget to string (function expects string, not float)
        budget_str = budget_raw if budget_raw else ""

        if name:
            # Fix: Add category parameter and correct argument order
            # Function signature: user_id, name, category, status, budget, notes
            add_homeowner_project(user_id, name, category, status, budget_str, notes)
            flash("Project saved.", "success")

    projects = list_homeowner_projects(user_id) if user_id else []

    return render_template(
        "homeowner/reno_planner.html",
        brand_name=FRONT_BRAND_NAME,
        projects=projects,
    )


@app.route("/homeowner/reno/planner/project/<int:project_id>/edit", methods=["GET", "POST"])
def homeowner_reno_planner_edit_project(project_id):
    """Edit a renovation project."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        flash("Please log in to edit projects.", "error")
        return redirect(url_for("login", role="homeowner"))
    
    project = get_homeowner_project(project_id, user_id)
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("homeowner_reno_planner"))
    
    if request.method == "POST":
        name = request.form.get("project_name", "").strip()
        budget_raw = request.form.get("project_budget", "").replace(",", "").strip()
        status = request.form.get("project_status", "Planning").strip()
        category = request.form.get("project_category", "Other").strip()
        notes = request.form.get("project_notes", "").strip()
        
        budget_str = budget_raw if budget_raw else ""
        
        if name:
            update_homeowner_project(
                project_id=project_id,
                user_id=user_id,
                name=name,
                category=category,
                status=status,
                budget=budget_str,
                notes=notes,
            )
            flash("Project updated successfully.", "success")
            return redirect(url_for("homeowner_reno_planner"))
        else:
            flash("Project name is required.", "error")
    
    project_dict = dict(project) if hasattr(project, 'keys') else project
    return render_template(
        "homeowner/reno_planner_edit.html",
        project=project_dict,
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/reno/planner/project/<int:project_id>/delete", methods=["POST"])
def homeowner_reno_planner_delete_project(project_id):
    """Delete a renovation project."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    project = get_homeowner_project(project_id, user_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    
    try:
        delete_homeowner_project(project_id, user_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/homeowner/design-boards/note/<int:note_id>/edit", methods=["GET", "POST"])
def homeowner_edit_note(note_id):
    """Edit a note on a mood board."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        flash("Please log in to edit notes.", "error")
        return redirect(url_for("login", role="homeowner"))
    
    note = get_homeowner_note_by_id(note_id, user_id)
    if not note:
        flash("Note not found.", "error")
        return redirect(url_for("homeowner_saved_notes"))
    
    note_dict = dict(note) if hasattr(note, 'keys') else note
    board_name = note_dict.get("project_name")
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        details = request.form.get("details", "").strip()
        tags = request.form.get("tags", "").strip()
        
        update_homeowner_note(
            note_id=note_id,
            user_id=user_id,
            title=title if title else None,
            details=details if details else None,
            tags=tags if tags else None,
        )
        flash("Note updated successfully.", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))
    
    return render_template(
        "homeowner/edit_note.html",
        note=note_dict,
        board_name=board_name,
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/design-boards/note/<int:note_id>/delete", methods=["POST"])
def homeowner_delete_note(note_id):
    """Delete a note from a mood board."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    note = get_homeowner_note_by_id(note_id, user_id)
    if not note:
        return jsonify({"success": False, "error": "Note not found"}), 404
    
    note_dict = dict(note) if hasattr(note, 'keys') else note
    board_name = note_dict.get("project_name")
    
    try:
        delete_homeowner_note(note_id, user_id)
        return jsonify({"success": True, "board_name": board_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/homeowner/reno/material-cost", methods=["GET"])
def homeowner_reno_material_cost():
    """Material & Cost Estimator - linked to mood boards."""
    from database import get_design_boards_for_user
    user = get_current_user()
    user_id = user["id"] if user else None
    
    # Get list of mood board names for the dropdown
    board_names = []
    if user_id:
        boards = get_design_boards_for_user(user_id) or []
        board_names = [b for b in boards if b]  # Filter out None values
    
    return render_template(
        "homeowner/reno_material_cost.html",
        brand_name=FRONT_BRAND_NAME,
        board_names=board_names,
    )

@app.route("/agent", methods=["GET"])
def agent_dashboard():
    """Agent dashboard view."""
    user = get_current_user()
    
    if not user:
        flash("Please log in to access your dashboard.", "error")
        return redirect(url_for("login", role="agent"))
    
    # Check role - normalize for comparison
    user_role = str(user.get("role") or "").strip().lower()
    if user_role != "agent":
        flash("This page is for agents only.", "error")
        return redirect(url_for("login", role=user.get("role", "homeowner")))

    try:
        metrics = get_agent_dashboard_metrics(user["id"])
        transactions = get_agent_transactions(user["id"])
        
        # Ensure transactions are dicts (get_agent_transactions should already return dicts)
        if transactions:
            transactions_list = []
            for tx in transactions:
                if hasattr(tx, 'keys') and not isinstance(tx, dict):
                    transactions_list.append(dict(tx))
                else:
                    transactions_list.append(tx)
            transactions = transactions_list
    except Exception as e:
        import traceback
        print(f"Error in agent_dashboard: {traceback.format_exc()}")
        flash(f"Error loading dashboard: {str(e)}", "error")
        metrics = {"new_leads": 0, "active_transactions": 0, "followups_today": 0}
        transactions = []

    return render_template(
        "agent/dashboard.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        metrics=metrics,
        transactions=transactions,
    )

@app.route("/lender", methods=["GET"])
def lender_dashboard():
    """Lender dashboard view."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "lender":
            return redirect(url_for("login", role="lender"))

        try:
            metrics = get_lender_dashboard_metrics(user["id"])
        except Exception as e:
            import traceback
            print(f"Error getting lender metrics: {traceback.format_exc()}")
            metrics = {
                "new_applications": 0,
                "loans_in_process": 0,
                "nurture_contacts": 0,
            }
        
        # Convert Row objects to dicts if needed
        try:
            loans_raw = list_lender_loans(user["id"])
            loans = []
            for loan in loans_raw:
                if hasattr(loan, 'keys'):
                    loans.append(dict(loan))
                else:
                    loans.append(loan)
        except Exception as e:
            import traceback
            print(f"Error getting lender loans: {traceback.format_exc()}")
            loans = []
        
        try:
            borrowers_raw = list_lender_borrowers(user["id"])
            borrowers = []
            for borrower in borrowers_raw:
                if hasattr(borrower, 'keys'):
                    borrowers.append(dict(borrower))
                else:
                    borrowers.append(borrower)
        except Exception as e:
            import traceback
            print(f"Error getting lender borrowers: {traceback.format_exc()}")
            borrowers = []

        return render_template(
            "lender/dashboard.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            metrics=metrics,
            loans=loans,
            borrowers=borrowers,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in lender_dashboard: {error_trace}")
        flash(f"Error loading dashboard: {str(e)}", "error")
        return redirect(url_for("login", role="lender"))


# -------------------------------------------------
# AGENT ROUTES
# -------------------------------------------------
@app.route("/agent/crm", methods=["GET", "POST"])
def agent_crm():
    """Agent CRM - comprehensive contact management with automated emails."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        import traceback
        print(f"Error in agent_crm (user check): {traceback.format_exc()}")
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        print(f"\n=== POST REQUEST RECEIVED ===")
        print(f"Action: '{action}'")
        print(f"Form data keys: {list(request.form.keys())}")
        print(f"User ID: {user.get('id')}")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            stage = request.form.get("stage", "new").strip()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            property_value = request.form.get("property_value", "").strip()
            equity_estimate = request.form.get("equity_estimate", "").strip()
            
            print(f"Name: '{name}'")
            print(f"Email: '{email}'")
            print(f"Phone: '{phone}'")
            print(f"Stage: '{stage}'")
            
            if not name:
                print("ERROR: Name is required but empty")
                flash("Name is required!", "error")
                return redirect(url_for("agent_crm"))
            else:
                try:
                    prop_val = float(property_value) if property_value else None
                    equity_val = float(equity_estimate) if equity_estimate else None
                    print(f"Calling add_agent_contact with user_id={user['id']}, name='{name}'")
                    contact_id = add_agent_contact(
                        user["id"], name, email, phone, stage, email or phone, "",
                        birthday, home_anniversary, address, notes, tags,
                        property_address, prop_val, equity_val
                    )
                    print(f"SUCCESS: Contact added with ID {contact_id}")
                    
                    # If email provided, try to link to existing homeowner account
                    if email:
                        from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                        homeowner = get_user_by_email(email)
                        if homeowner and homeowner.get("role") == "homeowner":
                            # Create relationship
                            referral_code = get_or_create_referral_code(user["id"], "agent")
                            create_client_relationship(
                                homeowner_id=homeowner["id"],
                                professional_id=user["id"],
                                professional_role="agent",
                                referral_code=referral_code
                            )
                            flash(f"Contact added and linked to homeowner account ({email})!", "success")
                        else:
                            flash("Contact added successfully!", "success")
                    else:
                        flash("Contact added successfully!", "success")
                    return redirect(url_for("agent_crm"))
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    print(f"ERROR adding contact: {error_trace}")
                    flash(f"Error adding contact: {str(e)}", "error")
                    return redirect(url_for("agent_crm"))
        
        elif action == "update":
            contact_id = request.form.get("contact_id")
            if contact_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'stage', 'birthday', 
                            'home_anniversary', 'address', 'notes', 'tags',
                            'property_address', 'property_value', 'equity_estimate',
                            'auto_birthday', 'auto_anniversary',
                            'auto_seasonal', 'auto_equity', 'auto_holidays',
                            'equity_frequency']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['property_value', 'equity_estimate']:
                            try:
                                updates[field] = float(val) if val else None
                            except:
                                pass
                        else:
                            updates[field] = val if val else None
                
                try:
                    update_agent_contact(int(contact_id), user["id"], **updates)
                    flash("Contact updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating contact: {e}", "error")
                    import traceback
                    print(f"Error updating contact: {traceback.format_exc()}")
        
        elif action == "add_interaction":
            contact_id = request.form.get("contact_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if contact_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(contact_id), "agent_contact", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged successfully!", "success")
                except Exception as e:
                    flash(f"Error logging interaction: {e}", "error")
        
        elif action == "add_task":
            contact_id = request.form.get("contact_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if contact_id and title:
                try:
                    add_crm_task(
                        int(contact_id), "agent_contact", user["id"],
                        title, description, due_date or None, priority, reminder_date
                    )
                    flash("Task added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding task: {e}", "error")
        
        elif action == "update_task":
            task_id = request.form.get("task_id")
            status = request.form.get("status", "").strip()
            if task_id and status:
                try:
                    updates = {"status": status}
                    if status == "completed":
                        updates["completed_at"] = datetime.now().isoformat()
                    update_crm_task(int(task_id), user["id"], **updates)
                    flash("Task updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating task: {e}", "error")
        
        elif action == "delete_task":
            task_id = request.form.get("task_id")
            if task_id:
                try:
                    delete_crm_task(int(task_id), user["id"])
                    flash("Task deleted successfully!", "success")
                except Exception as e:
                    flash(f"Error deleting task: {e}", "error")
        
        elif action == "add_deal":
            contact_id = request.form.get("contact_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(contact_id), "agent_contact", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding deal: {e}", "error")
        
        elif action == "update_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    updates = {}
                    for field in ['deal_name', 'deal_type', 'property_address', 'stage',
                                'expected_close_date', 'actual_close_date', 'notes']:
                        val = request.form.get(field, "").strip()
                        if val:
                            updates[field] = val if val else None
                    
                    for field in ['deal_value', 'commission_rate', 'probability']:
                        val = request.form.get(field, "").strip()
                        if val:
                            try:
                                updates[field] = float(val) if field != 'probability' else int(val)
                            except:
                                pass
                    
                    if updates:
                        update_crm_deal(int(deal_id), user["id"], **updates)
                        flash("Deal updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating deal: {e}", "error")
        
        elif action == "delete_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    delete_crm_deal(int(deal_id), user["id"])
                    flash("Deal deleted successfully!", "success")
                except Exception as e:
                    flash(f"Error deleting deal: {e}", "error")
        
        elif action == "add_relationship":
            contact_id_1 = request.form.get("contact_id_1")
            contact_id_2 = request.form.get("contact_id_2")
            relationship_type = request.form.get("relationship_type", "other").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id_1 and contact_id_2:
                try:
                    result = add_crm_relationship(
                        int(contact_id_1), int(contact_id_2), "agent_contact",
                        user["id"], relationship_type, notes
                    )
                    if result:
                        flash("Relationship added successfully!", "success")
                    else:
                        flash("Relationship already exists!", "error")
                except Exception as e:
                    flash(f"Error adding relationship: {e}", "error")
        
        elif action == "bulk_action":
            contact_ids = request.form.getlist("contact_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if contact_ids and bulk_action_type:
                try:
                    for contact_id in contact_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            contact = get_agent_contact(int(contact_id), user["id"])
                            if contact:
                                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                                existing_tags = (contact_dict.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_agent_contact(int(contact_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_stage":
                            stage = request.form.get("bulk_stage", "").strip()
                            if stage:
                                update_agent_contact(int(contact_id), user["id"], stage=stage)
                    flash(f"Bulk action completed for {len(contact_ids)} contact(s)!", "success")
                except Exception as e:
                    flash(f"Error performing bulk action: {e}", "error")

    stage_filter = request.args.get("stage")
    search_query = request.args.get("search", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    sort_by = request.args.get("sort", "name")  # name, stage, last_touch, created_at
    
    # DEBUG: Log contact loading
    print(f"\n{'='*60}")
    print(f"AGENT CRM: Loading contacts for agent {user['id']}")
    print(f"  Stage filter: {stage_filter}")
    print(f"  Search query: {search_query}")
    print(f"  Tag filter: {tag_filter}")
    print(f"{'='*60}\n")
    
    try:
        contacts = list_agent_contacts(user["id"], stage_filter)
        print(f"AGENT CRM: Found {len(contacts)} contacts from database")
        
        # DEBUG: Log all contacts found
        for idx, contact in enumerate(contacts[:5]):  # Log first 5
            contact_dict = dict(contact) if hasattr(contact, 'keys') and not isinstance(contact, dict) else contact
            print(f"  Contact {idx+1}: {contact_dict.get('name')} ({contact_dict.get('email')}) - Stage: {contact_dict.get('stage')}")
        
        if len(contacts) > 5:
            print(f"  ... and {len(contacts) - 5} more contacts")
        # Convert contacts to dicts for JSON serialization in template
        # Handle None values and ensure all fields exist
        contacts_list = []
        for contact in contacts:
            try:
                # Convert sqlite3.Row to dict, handling missing columns gracefully
                # sqlite3.Row objects need to be converted to dict explicitly
                import sqlite3
                if isinstance(contact, sqlite3.Row):
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif hasattr(contact, 'keys') and not isinstance(contact, dict):
                    # It's a Row-like object
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif isinstance(contact, dict):
                    contact_dict = contact.copy()
                else:
                    # Fallback: try to convert
                    try:
                        contact_dict = dict(contact)
                    except:
                        contact_dict = {key: getattr(contact, key, None) for key in dir(contact) if not key.startswith('_')}
                
                # Ensure all expected fields exist with defaults
                expected_fields = {
                    'id': None, 'created_at': '', 'name': '', 'email': '', 'phone': '',
                    'stage': 'new', 'best_contact': '', 'last_touch': '', 'birthday': '',
                    'home_anniversary': '', 'address': '', 'notes': '', 'tags': '',
                    'property_address': '', 'property_value': None, 'equity_estimate': None,
                    'auto_birthday': 1, 'auto_anniversary': 1, 'auto_seasonal': 1,
                    'auto_equity': 1, 'auto_holidays': 1, 'equity_frequency': 'monthly'
                }
                for field, default in expected_fields.items():
                    if field not in contact_dict:
                        contact_dict[field] = default
                
                # Apply search filter
                if search_query:
                    search_lower = search_query.lower()
                    matches = (
                        search_lower in (contact_dict.get('name') or '').lower() or
                        search_lower in (contact_dict.get('email') or '').lower() or
                        search_lower in (contact_dict.get('phone') or '').lower() or
                        search_lower in (contact_dict.get('property_address') or '').lower() or
                        search_lower in (contact_dict.get('notes') or '').lower() or
                        search_lower in (contact_dict.get('tags') or '').lower()
                    )
                    if not matches:
                        continue
                
                # Apply tag filter
                if tag_filter:
                    contact_tags = (contact_dict.get('tags') or '').lower()
                    if tag_filter.lower() not in contact_tags:
                        continue
                
                # Fetch interaction count and history for this contact
                try:
                    interactions = list_crm_interactions(
                        contact_dict['id'], "agent_contact", user["id"], limit=50
                    )
                    contact_dict['interaction_count'] = len(interactions)
                    contact_dict['recent_interactions'] = [
                        dict(i) if hasattr(i, 'keys') else i for i in interactions[:3]
                    ]
                    contact_dict['all_interactions'] = [
                        dict(i) if hasattr(i, 'keys') else i for i in interactions
                    ]
                except Exception as e:
                    print(f"Error fetching interactions: {e}")
                    contact_dict['interaction_count'] = 0
                    contact_dict['recent_interactions'] = []
                    contact_dict['all_interactions'] = []
                
                # Fetch tasks for this contact
                try:
                    tasks = list_crm_tasks(user["id"], contact_dict['id'], "agent_contact", status="pending")
                    tasks_list = []
                    for t in tasks:
                        if hasattr(t, 'keys'):
                            tasks_list.append(dict(t))
                        else:
                            tasks_list.append(t)
                    contact_dict['pending_tasks'] = tasks_list
                    contact_dict['task_count'] = len(tasks_list)
                except Exception as e:
                    print(f"Error fetching tasks: {e}")
                    contact_dict['pending_tasks'] = []
                    contact_dict['task_count'] = 0
                
                # Fetch deals for this contact
                try:
                    deals = list_crm_deals(user["id"], contact_dict['id'], "agent_contact")
                    deals_list = []
                    for d in deals:
                        if hasattr(d, 'keys'):
                            deals_list.append(dict(d))
                        else:
                            deals_list.append(d)
                    contact_dict['deals'] = deals_list
                    contact_dict['deal_count'] = len(deals_list)
                    contact_dict['total_pipeline_value'] = sum([
                        (d.get('deal_value') if isinstance(d, dict) else (d['deal_value'] if 'deal_value' in d else 0)) or 0 
                        for d in deals_list
                    ])
                except Exception as e:
                    print(f"Error fetching deals for contact {contact_dict.get('id')}: {e}")
                    contact_dict['deals'] = []
                    contact_dict['deal_count'] = 0
                    contact_dict['total_pipeline_value'] = 0
                
                # Fetch relationships for this contact
                try:
                    relationships = list_crm_relationships(contact_dict['id'], "agent_contact", user["id"])
                    relationships_list = []
                    for r in relationships:
                        if hasattr(r, 'keys'):
                            relationships_list.append(dict(r))
                        else:
                            relationships_list.append(r)
                    contact_dict['relationships'] = relationships_list
                except Exception as e:
                    print(f"Error fetching relationships for contact {contact_dict.get('id')}: {e}")
                    contact_dict['relationships'] = []
                
                contacts_list.append(contact_dict)
            except Exception as e:
                import traceback
                print(f"Error converting contact: {traceback.format_exc()}")
                continue
        
        # Ensure all contacts are dicts before sorting/stats
        contacts_list_dicts = []
        for c in contacts_list:
            if isinstance(c, dict):
                contacts_list_dicts.append(c)
            elif hasattr(c, 'keys'):
                try:
                    import sqlite3
                    if isinstance(c, sqlite3.Row):
                        contacts_list_dicts.append({key: c[key] for key in c.keys()})
                    else:
                        contacts_list_dicts.append(dict(c))
                except Exception as e:
                    print(f"Error converting contact to dict: {e}")
                    continue
            else:
                print(f"Skipping invalid contact: {type(c)}")
                continue
        
        # Sort contacts
        if sort_by == "name":
            contacts_list_dicts.sort(key=lambda x: (x.get('name') or '').lower() if isinstance(x, dict) else '')
        elif sort_by == "stage":
            stage_order = {'new': 0, 'nurture': 1, 'active': 2, 'past': 3, 'sphere': 4}
            contacts_list_dicts.sort(key=lambda x: stage_order.get(x.get('stage', 'new') if isinstance(x, dict) else 'new', 5))
        elif sort_by == "last_touch":
            contacts_list_dicts.sort(key=lambda x: (x.get('last_touch') or '') if isinstance(x, dict) else '', reverse=True)
        elif sort_by == "created_at":
            contacts_list_dicts.sort(key=lambda x: (x.get('created_at') or '') if isinstance(x, dict) else '', reverse=True)
        
        # Calculate stats
        total_contacts = len(contacts_list_dicts)
        all_tasks = list_crm_tasks(user["id"], status="pending")
        all_deals_raw = list_crm_deals(user["id"])
        
        # Convert all_deals to dicts
        all_deals = []
        for d in all_deals_raw:
            if hasattr(d, 'keys'):
                all_deals.append(dict(d))
            else:
                all_deals.append(d)
        
        # Get follow-up threshold from user settings
        from database import get_user_by_id
        user_details = get_user_by_id(user["id"])
        if user_details and hasattr(user_details, 'keys'):
            user_details = dict(user_details)
        follow_up_days = user_details.get('follow_up_days', 30) if user_details and isinstance(user_details, dict) else 30
        
        # Get contacts needing follow-up
        try:
            from database import get_contacts_needing_followup
            contacts_needing_followup = get_contacts_needing_followup(user["id"], follow_up_days)
            needs_followup_count = len(contacts_needing_followup)
        except Exception as e:
            print(f"Error getting contacts needing followup: {e}")
            needs_followup_count = 0
        
        stats = {
            'total': total_contacts,
            'new': len([c for c in contacts_list_dicts if c.get('stage') == 'new']),
            'active': len([c for c in contacts_list_dicts if c.get('stage') == 'active']),
            'past': len([c for c in contacts_list_dicts if c.get('stage') == 'past']),
            'with_automation': len([c for c in contacts_list_dicts if any([
                c.get('auto_birthday'), c.get('auto_anniversary'),
                c.get('auto_seasonal'), c.get('auto_equity'), c.get('auto_holidays')
            ])]),
            'total_equity': sum([c.get('equity_estimate') or 0 for c in contacts_list_dicts]),
            'pending_tasks': len(all_tasks),
            'total_deals': len(all_deals),
            'pipeline_value': sum([(d.get('deal_value') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'expected_commission': sum([(d.get('expected_commission') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'needs_followup': needs_followup_count,
            'follow_up_days': follow_up_days,
        }
        
        # Get all unique tags
        all_tags = set()
        for contact in contacts_list_dicts:
            tags = contact.get('tags', '') or '' if isinstance(contact, dict) else ''
            if tags:
                all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
        all_tags = sorted(list(all_tags))
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error loading contacts: {error_trace}")
        flash(f"Error loading contacts: {e}", "error")
        contacts_list = []
        contacts_list_dicts = []  # Ensure this is defined even on error
        stats = {'total': 0, 'new': 0, 'active': 0, 'past': 0, 'with_automation': 0, 'total_equity': 0, 'pending_tasks': 0, 'total_deals': 0, 'pipeline_value': 0, 'expected_commission': 0, 'needs_followup': 0, 'follow_up_days': 30}
        all_tags = []
    
    # Get all pending tasks for dashboard
    try:
        all_pending_tasks = list_crm_tasks(user["id"], status="pending")
        upcoming_tasks = []
        for t in all_pending_tasks[:10]:
            if hasattr(t, 'keys'):
                upcoming_tasks.append(dict(t))
            else:
                upcoming_tasks.append(t)
    except Exception as e:
        print(f"Error fetching upcoming tasks: {e}")
        upcoming_tasks = []
    
    # Get email templates for quick actions
    try:
        email_templates = list_message_templates(user["id"], "agent", "email")
    except:
        email_templates = []
    
    try:
        return render_template(
            "agent/crm.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            contacts=contacts_list_dicts,  # Use the converted dicts list
            stage_filter=stage_filter,
            search_query=search_query,
            tag_filter=tag_filter,
            sort_by=sort_by,
            stats=stats,
            all_tags=all_tags,
            upcoming_tasks=upcoming_tasks,
            email_templates=email_templates,
        )
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"Error rendering template: {error_msg}")
        return f"Template Error: {e}<br><pre>{error_msg}</pre>", 500


@app.route("/agent/crm/import", methods=["GET", "POST"])
def agent_crm_import():
    """Agent CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please select a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please select a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                # Read file into pandas
                if filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                # Convert to list of dicts for preview
                data = df.to_dict('records')
                
                # Get column names for mapping
                columns = list(df.columns)
                
                # Store in session for import step
                session['crm_import_data'] = json.dumps(data, default=str)
                session['crm_import_columns'] = columns
                
                return render_template(
                    "agent/crm_import_preview.html",
                    brand_name=FRONT_BRAND_NAME,
                    user=user,
                    data=data[:10],  # Preview first 10 rows
                    total_rows=len(data),
                    columns=columns,
                    sample_data=data[0] if data else {},
                )
            except Exception as e:
                import traceback
                flash(f"Error reading file: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
        
        elif action == "import":
            # Actually import the data
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("No import data found. Please upload a file again.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'stage': request.form.get('map_stage', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'property_value': request.form.get('map_property_value', '').strip(),
                    'equity_estimate': request.form.get('map_equity', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                # Default stage if not mapped
                default_stage = request.form.get('default_stage', 'new').strip()
                
                # Import settings
                skip_duplicates = request.form.get('skip_duplicates') == 'on'
                duplicate_check = request.form.get('duplicate_check', 'email').strip()
                
                imported = 0
                skipped = 0
                errors = []
                
                for idx, row in enumerate(data):
                    try:
                        # Map columns to fields
                        name = str(row.get(mappings['name'], '')).strip() if mappings['name'] else ''
                        email = str(row.get(mappings['email'], '')).strip() if mappings['email'] else ''
                        phone = str(row.get(mappings['phone'], '')).strip() if mappings['phone'] else ''
                        stage = str(row.get(mappings['stage'], default_stage)).strip() if mappings['stage'] else default_stage
                        birthday = str(row.get(mappings['birthday'], '')).strip() if mappings['birthday'] else ''
                        home_anniversary = str(row.get(mappings['home_anniversary'], '')).strip() if mappings['home_anniversary'] else ''
                        address = str(row.get(mappings['address'], '')).strip() if mappings['address'] else ''
                        property_address = str(row.get(mappings['property_address'], '')).strip() if mappings['property_address'] else ''
                        notes = str(row.get(mappings['notes'], '')).strip() if mappings['notes'] else ''
                        tags = str(row.get(mappings['tags'], '')).strip() if mappings['tags'] else ''
                        
                        # Parse numeric values
                        try:
                            property_value = float(row.get(mappings['property_value'], 0)) if mappings['property_value'] and str(row.get(mappings['property_value'], '')).strip() else None
                        except:
                            property_value = None
                        
                        try:
                            equity_estimate = float(row.get(mappings['equity_estimate'], 0)) if mappings['equity_estimate'] and str(row.get(mappings['equity_estimate'], '')).strip() else None
                        except:
                            equity_estimate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Check for duplicates if enabled
                        if skip_duplicates:
                            existing_contacts = list_agent_contacts(user["id"])
                            is_duplicate = False
                            for existing in existing_contacts:
                                if duplicate_check == 'email' and email:
                                    if existing.get('email') and existing['email'].lower() == email.lower():
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'phone' and phone:
                                    if existing.get('phone') and existing['phone'] == phone:
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'name' and name:
                                    if existing.get('name') and existing['name'].lower() == name.lower():
                                        is_duplicate = True
                                        break
                            
                            if is_duplicate:
                                skipped += 1
                                continue
                        
                        # Add contact
                        add_agent_contact(
                            user["id"], name, email, phone, stage, email or phone, "",
                            birthday, home_anniversary, address, notes, tags,
                            property_address, property_value, equity_estimate
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                flash(f"Import complete! {imported} contacts imported, {skipped} skipped, {len(errors)} errors.", "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("agent_crm"))
            except Exception as e:
                import traceback
                flash(f"Error during import: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "agent/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/agent/transactions", methods=["GET", "POST"])
def agent_transactions():
    """Agent transactions - list and create transactions."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        property_address = request.form.get("property_address", "").strip()
        client_name = request.form.get("client_name", "").strip()
        side = request.form.get("side", "buyer").strip()
        stage = request.form.get("stage", "pre_contract").strip()
        close_date = request.form.get("close_date", "").strip() or None

        if property_address and client_name:
            try:
                create_transaction(
                    agent_id=user["id"],
                    property_address=property_address,
                    client_name=client_name,
                    side=side,
                    current_stage=stage,
                    target_close_date=close_date,
                    client_email=request.form.get("client_email", "").strip(),
                    client_phone=request.form.get("client_phone", "").strip(),
                    purchase_price=request.form.get("purchase_price", "").strip() or None,
                    notes=request.form.get("notes", "").strip(),
                )
                flash("Transaction created successfully!", "success")
            except Exception as e:
                flash(f"Error creating transaction: {e}", "error")

    # Get contact info if coming from CRM
    contact_id = request.args.get("contact_id")
    contact_info = None
    if contact_id:
        try:
            contact = get_agent_contact(int(contact_id), user["id"])
            if contact:
                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                contact_info = {
                    'name': contact_dict.get('name', '') if isinstance(contact_dict, dict) else (contact_dict['name'] if 'name' in contact_dict else ''),
                    'email': contact_dict.get('email', '') if isinstance(contact_dict, dict) else (contact_dict['email'] if 'email' in contact_dict else ''),
                    'phone': contact_dict.get('phone', '') if isinstance(contact_dict, dict) else (contact_dict['phone'] if 'phone' in contact_dict else ''),
                    'property_address': contact_dict.get('property_address', '') if isinstance(contact_dict, dict) else (contact_dict['property_address'] if 'property_address' in contact_dict else ''),
                }
        except:
            pass
    
    transactions = get_agent_transactions(user["id"])
    return render_template(
        "agent/transactions.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transactions=transactions,
        contact_info=contact_info,
    )


@app.route("/agent/transactions/<int:tx_id>", methods=["GET"])
def agent_transaction_detail(tx_id):
    """View transaction details."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("Transaction not found.", "error")
        return redirect(url_for("agent_transactions"))

    documents = get_transaction_documents(tx_id)
    participants = get_transaction_participants(tx_id)
    timeline = get_transaction_timeline(tx_id)
    doc_status = get_transaction_document_status(tx_id)

    return render_template(
        "agent/transaction_detail.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transaction=transaction,
        tx=transaction,  # Also provide as 'tx' for backward compatibility
        documents=documents,
        participants=participants,
        timeline=timeline,
        doc_status=doc_status,
    )


@app.route("/agent/transactions/<int:tx_id>/delete", methods=["POST"])
def agent_transaction_delete(tx_id):
    """Delete a transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if delete_transaction(tx_id, user["id"]):
        flash("Transaction deleted.", "success")
    else:
        flash("Could not delete transaction.", "error")

    return redirect(url_for("agent_transactions"))


@app.route("/agent/communications", methods=["GET", "POST"])
def agent_communications():
    """Agent communications - message templates."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        template_name = request.form.get("template_name", "").strip()
        template_content = request.form.get("template_content", "").strip()
        template_type = request.form.get("template_type", "email").strip()

        if template_name and template_content:
            try:
                add_message_template(user["id"], template_name, template_content, template_type)
                flash("Template saved!", "success")
            except Exception as e:
                flash(f"Error saving template: {e}", "error")

    templates = list_message_templates(user["id"])
    return render_template(
        "agent/communications.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@app.route("/agent/marketing", methods=["GET", "POST"])
def agent_marketing():
    """Agent marketing - marketing templates and campaigns."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        template_name = request.form.get("template_name", "").strip()
        template_content = request.form.get("template_content", "").strip()
        template_type = request.form.get("template_type", "social").strip()

        if template_name and template_content:
            try:
                add_marketing_template(user["id"], template_name, template_content, template_type)
                flash("Marketing template saved!", "success")
            except Exception as e:
                flash(f"Error saving template: {e}", "error")

    templates = list_marketing_templates(user["id"])
    return render_template(
        "agent/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@app.route("/agent/power-tools", methods=["GET"])
def agent_power_tools():
    """Agent power tools - advanced agent features."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    return render_template(
        "agent/power_tools.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/agent/referrals", methods=["GET", "POST"])
def agent_referrals():
    """Agent referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    try:
        from database import (
            get_referral_links_for_agent,
            create_referral_link,
            get_referral_stats,
            get_accessible_homeowners
        )
        
        # Handle POST - create new referral link
        if request.method == "POST":
            try:
                token = create_referral_link(agent_id=user["id"])
                flash("New referral link created!", "success")
                return redirect(url_for("agent_referrals"))
            except Exception as e:
                flash(f"Error creating referral link: {str(e)}", "error")
        
        # Get all referral links for this agent
        referral_links = get_referral_links_for_agent(user["id"])
        
        # If no links exist, create one automatically
        if not referral_links:
            try:
                token = create_referral_link(agent_id=user["id"])
                referral_links = get_referral_links_for_agent(user["id"])
            except Exception as e:
                print(f"Error auto-creating referral link: {e}")
        
        # Get stats
        try:
            stats = get_referral_stats(user["id"])
        except Exception as e:
            print(f"Error getting stats: {e}")
            stats = {'total_clients': 0, 'clients_this_month': 0}
        
        # Build referral URLs
        base_url = request.url_root.rstrip('/')
        referral_links_with_urls = []
        for link in referral_links:
            link_dict = dict(link) if hasattr(link, 'keys') else link
            link_dict['url'] = f"{base_url}/signup?role=homeowner&ref={link_dict['token']}"
            referral_links_with_urls.append(link_dict)
        
        # Use the first link as primary (for backward compatibility)
        primary_link = referral_links_with_urls[0] if referral_links_with_urls else None
        referral_url = primary_link['url'] if primary_link else None
        referral_code = primary_link['token'] if primary_link else None
        
        return render_template(
            "agent/referrals.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            referral_code=referral_code,
            referral_url=referral_url,
            referral_links=referral_links_with_urls,
            stats=stats,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in agent_referrals: {error_trace}")
        flash(f"Error loading referral page: {str(e)}", "error")
        return redirect(url_for("agent_dashboard"))


@app.route("/agent/vendors", methods=["GET", "POST"])
def agent_vendors():
    """Agent trusted vendors management."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from database import (
        create_trusted_vendor,
        get_trusted_vendors,
        update_trusted_vendor,
        delete_trusted_vendor
    )
    
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        
        if action == "create":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            contact_name = request.form.get("contact_name", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            email = request.form.get("email", "").strip().lower() or None
            website = request.form.get("website", "").strip() or None
            address = request.form.get("address", "").strip() or None
            notes = request.form.get("notes", "").strip() or None
            
            if not name or not category:
                flash("Name and category are required.", "error")
            else:
                try:
                    vendor_id = create_trusted_vendor(
                        agent_id=user["id"],
                        name=name,
                        category=category,
                        contact_name=contact_name,
                        phone=phone,
                        email=email,
                        website=website,
                        address=address,
                        notes=notes
                    )
                    flash(f"Vendor '{name}' added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding vendor: {str(e)}", "error")
        
        elif action == "update":
            vendor_id = request.form.get("vendor_id")
            if vendor_id:
                try:
                    vendor_id = int(vendor_id)
                    name = request.form.get("name", "").strip()
                    category = request.form.get("category", "").strip()
                    contact_name = request.form.get("contact_name", "").strip() or None
                    phone = request.form.get("phone", "").strip() or None
                    email = request.form.get("email", "").strip().lower() or None
                    website = request.form.get("website", "").strip() or None
                    address = request.form.get("address", "").strip() or None
                    notes = request.form.get("notes", "").strip() or None
                    
                    if update_trusted_vendor(
                        vendor_id=vendor_id,
                        name=name,
                        category=category,
                        contact_name=contact_name,
                        phone=phone,
                        email=email,
                        website=website,
                        address=address,
                        notes=notes
                    ):
                        flash("Vendor updated successfully!", "success")
                    else:
                        flash("Error updating vendor.", "error")
                except (ValueError, Exception) as e:
                    flash(f"Error updating vendor: {str(e)}", "error")
        
        elif action == "delete":
            vendor_id = request.form.get("vendor_id")
            if vendor_id:
                try:
                    vendor_id = int(vendor_id)
                    if delete_trusted_vendor(vendor_id):
                        flash("Vendor removed successfully.", "success")
                    else:
                        flash("Error removing vendor.", "error")
                except (ValueError, Exception) as e:
                    flash(f"Error removing vendor: {str(e)}", "error")
        
        return redirect(url_for("agent_vendors"))
    
    # Get all vendors
    vendors_raw = get_trusted_vendors(user["id"])
    vendors = []
    for vendor in vendors_raw:
        if hasattr(vendor, 'keys'):
            vendors.append(dict(vendor))
        else:
            vendors.append(vendor)
    
    # Group by category
    vendors_by_category = {}
    categories = set()
    for vendor in vendors:
        cat = vendor.get("category", "Other")
        categories.add(cat)
        if cat not in vendors_by_category:
            vendors_by_category[cat] = []
        vendors_by_category[cat].append(vendor)
    
    return render_template(
        "agent/vendors.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        vendors=vendors,
        vendors_by_category=vendors_by_category,
        categories=sorted(categories),
    )


@app.route("/agent/settings/profile", methods=["GET", "POST"])
def agent_settings_profile():
    """Agent settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            print(f"\n{'='*60}")
            print(f"AGENT PROFILE SAVE: Starting profile update for user {user['id']}")
            print(f"{'='*60}\n")
            
            # Handle file uploads using consolidated helper
            professional_photo = handle_profile_file_upload("professional_photo", folder="profiles", role_prefix="AGENT ")
            brokerage_logo = handle_profile_file_upload("brokerage_logo", folder="profiles", role_prefix="AGENT ")
            
            # Preserve existing photos/logos if not uploading new ones
            professional_photo, brokerage_logo = preserve_existing_profile_media(
                user["id"], professional_photo, brokerage_logo
            )
            
            print(f"AGENT PROFILE: About to save - photo={professional_photo}, logo={brokerage_logo}")
            
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="agent",
                professional_photo=professional_photo,
                brokerage_logo=brokerage_logo,
                team_name=request.form.get("team_name", "").strip() or None,
                brokerage_name=request.form.get("brokerage_name", "").strip() or None,
                website_url=request.form.get("website_url", "").strip() or None,
                facebook_url=request.form.get("facebook_url", "").strip() or None,
                instagram_url=request.form.get("instagram_url", "").strip() or None,
                linkedin_url=request.form.get("linkedin_url", "").strip() or None,
                twitter_url=request.form.get("twitter_url", "").strip() or None,
                youtube_url=request.form.get("youtube_url", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                call_button_enabled=1 if request.form.get("call_button_enabled") == "on" else 0,
                schedule_button_enabled=1 if request.form.get("schedule_button_enabled") == "on" else 0,
                schedule_url=request.form.get("schedule_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
                homebot_widget_id=request.form.get("homebot_widget_id", "").strip() or None,
                va_rate_30yr=float(request.form.get("va_rate_30yr")) if request.form.get("va_rate_30yr") else None,
                fha_rate_30yr=float(request.form.get("fha_rate_30yr")) if request.form.get("fha_rate_30yr") else None,
                conventional_rate_30yr=float(request.form.get("conventional_rate_30yr")) if request.form.get("conventional_rate_30yr") else None,
            )
            print(f"AGENT PROFILE: Profile saved successfully with ID {profile_id}")
            print(f"{'='*60}\n")
            flash("Profile updated successfully! Your information and photos have been saved.", "success")
            return redirect(url_for("agent_settings_profile"))
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"\n{'='*60}")
            print(f"AGENT PROFILE ERROR: {str(e)}")
            print(f"{'='*60}")
            print(error_trace)
            print(f"{'='*60}\n")
            flash(f"Error updating profile: {str(e)}. Please check the console for details and try again.", "error")
            # Continue to render the form so user can see the error and try again
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})
    
    return render_template(
        "agent/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
    )


# -------------------------------------------------
# LENDER ROUTES
# -------------------------------------------------
@app.route("/lender/crm", methods=["GET", "POST"])
def lender_crm():
    """Lender CRM - comprehensive borrower management with automated emails."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        action = request.form.get("action", "add")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            status = request.form.get("status", "prospect").strip()
            loan_type = request.form.get("loan_type", "").strip()
            target_payment = request.form.get("target_payment", "").strip()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            loan_amount = request.form.get("loan_amount", "").strip()
            loan_rate = request.form.get("loan_rate", "").strip()
            
            try:
                loan_amt = float(loan_amount) if loan_amount else None
                rate = float(loan_rate) if loan_rate else None
                borrower_id = add_lender_borrower(
                    user["id"], name, status, loan_type, target_payment, "",
                    email, phone, birthday, home_anniversary, address, notes, tags,
                    property_address, loan_amt, rate
                )
                
                # If email provided, try to link to existing homeowner account
                if email:
                    from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                    homeowner = get_user_by_email(email)
                    if homeowner and homeowner.get("role") == "homeowner":
                        # Create relationship
                        referral_code = get_or_create_referral_code(user["id"], "lender")
                        create_client_relationship(
                            homeowner_id=homeowner["id"],
                            professional_id=user["id"],
                            professional_role="lender",
                            referral_code=referral_code
                        )
                        flash(f"Borrower added and linked to homeowner account ({email})!", "success")
                    else:
                        flash("Borrower added successfully!", "success")
                else:
                    flash("Borrower added successfully!", "success")
            except Exception as e:
                flash(f"Error adding borrower: {e}", "error")
        
        elif action == "update":
            borrower_id = request.form.get("borrower_id")
            if borrower_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'status', 'loan_type', 
                            'target_payment', 'birthday', 'home_anniversary', 
                            'address', 'notes', 'tags', 'property_address',
                            'loan_amount', 'loan_rate', 'auto_birthday', 
                            'auto_anniversary', 'auto_seasonal', 'auto_equity',
                            'auto_holidays', 'equity_frequency']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['loan_amount', 'loan_rate']:
                            try:
                                updates[field] = float(val) if val else None
                            except:
                                pass
                        else:
                            updates[field] = val if val else None
                
                try:
                    update_lender_borrower(int(borrower_id), user["id"], **updates)
                    flash("Borrower updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating borrower: {e}", "error")
        
        elif action == "add_interaction":
            borrower_id = request.form.get("borrower_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if borrower_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(borrower_id), "lender_borrower", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged successfully!", "success")
                except Exception as e:
                    flash(f"Error logging interaction: {e}", "error")
        
        elif action == "add_task":
            borrower_id = request.form.get("borrower_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if borrower_id and title:
                try:
                    add_crm_task(
                        int(borrower_id), "lender_borrower", user["id"],
                        title, description, due_date or None, priority, reminder_date
                    )
                    flash("Task added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding task: {e}", "error")
        
        elif action == "update_task":
            task_id = request.form.get("task_id")
            status = request.form.get("status", "").strip()
            if task_id and status:
                try:
                    updates = {"status": status}
                    if status == "completed":
                        updates["completed_at"] = datetime.now().isoformat()
                    update_crm_task(int(task_id), user["id"], **updates)
                    flash("Task updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating task: {e}", "error")
        
        elif action == "add_deal":
            borrower_id = request.form.get("borrower_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if borrower_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(borrower_id), "lender_borrower", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding deal: {e}", "error")
        
        elif action == "bulk_action":
            borrower_ids = request.form.getlist("borrower_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if borrower_ids and bulk_action_type:
                try:
                    for borrower_id in borrower_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            borrower = get_lender_borrower(int(borrower_id), user["id"])
                            if borrower:
                                existing_tags = (borrower.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_lender_borrower(int(borrower_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_status":
                            status = request.form.get("bulk_status", "").strip()
                            if status:
                                update_lender_borrower(int(borrower_id), user["id"], status=status)
                    flash(f"Bulk action completed for {len(borrower_ids)} borrower(s)!", "success")
                except Exception as e:
                    flash(f"Error performing bulk action: {e}", "error")
        
        elif action == "update_followup_days":
            follow_up_days = request.form.get("follow_up_days", "30").strip()
            try:
                days = int(follow_up_days)
                if 1 <= days <= 365:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET follow_up_days = ? WHERE id = ?",
                        (days, user["id"])
                    )
                    conn.commit()
                    conn.close()
                    flash(f"Follow-up reminder set to {days} days!", "success")
                else:
                    flash("Please enter a number between 1 and 365.", "error")
            except ValueError:
                flash("Invalid number. Please enter a number between 1 and 365.", "error")

    status_filter = request.args.get("status")
    borrowers = list_lender_borrowers(user["id"], status_filter)
    
    # Convert borrowers to dicts and enrich with tasks/deals
    borrowers_list = []
    for borrower in borrowers:
        try:
            borrower_dict = dict(borrower)
            
            # Fetch interaction count
            try:
                interactions = list_crm_interactions(
                    borrower_dict['id'], "lender_borrower", user["id"], limit=50
                )
                borrower_dict['interaction_count'] = len(interactions)
                borrower_dict['recent_interactions'] = [dict(i) for i in interactions[:3]]
            except:
                borrower_dict['interaction_count'] = 0
                borrower_dict['recent_interactions'] = []
            
            # Fetch tasks
            try:
                tasks = list_crm_tasks(user["id"], borrower_dict['id'], "lender_borrower", status="pending")
                borrower_dict['pending_tasks'] = [dict(t) for t in tasks]
                borrower_dict['task_count'] = len(tasks)
            except:
                borrower_dict['pending_tasks'] = []
                borrower_dict['task_count'] = 0
            
            # Fetch deals
            try:
                deals = list_crm_deals(user["id"], borrower_dict['id'], "lender_borrower")
                borrower_dict['deals'] = [dict(d) for d in deals]
                borrower_dict['deal_count'] = len(deals)
                borrower_dict['total_pipeline_value'] = sum([d.get('deal_value') or 0 for d in deals])
            except:
                borrower_dict['deals'] = []
                borrower_dict['deal_count'] = 0
                borrower_dict['total_pipeline_value'] = 0
            
            borrowers_list.append(borrower_dict)
        except:
            continue
    
    # Calculate stats
    all_tasks = list_crm_tasks(user["id"], status="pending")
    all_deals = list_crm_deals(user["id"])
    
    # Get follow-up threshold from user settings
    from database import get_user_by_id
    user_details = get_user_by_id(user["id"])
    follow_up_days = user_details.get('follow_up_days', 30) if user_details else 30
    
    # Get borrowers needing follow-up
    try:
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=follow_up_days)
        cutoff_iso = cutoff_date.isoformat()
        
        cur.execute("""
            SELECT DISTINCT lb.id
            FROM lender_borrowers lb
            LEFT JOIN crm_interactions ci ON ci.contact_id = lb.id 
                AND ci.contact_type = 'lender_borrower' 
                AND ci.professional_user_id = lb.lender_user_id
            WHERE lb.lender_user_id = ?
            AND (
                COALESCE(
                    (SELECT MAX(ci2.interaction_date) 
                     FROM crm_interactions ci2 
                     WHERE ci2.contact_id = lb.id 
                     AND ci2.contact_type = 'lender_borrower' 
                     AND ci2.professional_user_id = lb.lender_user_id),
                    lb.last_touch,
                    lb.created_at
                ) < ? OR
                COALESCE(
                    (SELECT MAX(ci3.interaction_date) 
                     FROM crm_interactions ci3 
                     WHERE ci3.contact_id = lb.id 
                     AND ci3.contact_type = 'lender_borrower' 
                     AND ci3.professional_user_id = lb.lender_user_id),
                    lb.last_touch
                ) IS NULL
            )
        """, (user["id"], cutoff_iso))
        needs_followup_count = len(cur.fetchall())
        conn.close()
    except Exception as e:
        print(f"Error getting borrowers needing followup: {e}")
        needs_followup_count = 0
    
    stats = {
        'total': len(borrowers_list),
        'prospect': len([b for b in borrowers_list if b.get('status') == 'prospect']),
        'preapproval': len([b for b in borrowers_list if b.get('status') == 'preapproval']),
        'in_process': len([b for b in borrowers_list if b.get('status') == 'in_process']),
        'closed': len([b for b in borrowers_list if b.get('status') == 'closed']),
        'pending_tasks': len(all_tasks),
        'total_deals': len(all_deals),
        'pipeline_value': sum([d.get('deal_value') or 0 for d in all_deals]),
        'expected_commission': sum([d.get('expected_commission') or 0 for d in all_deals]),
        'needs_followup': needs_followup_count,
        'follow_up_days': follow_up_days,
        'with_automation': len([b for b in borrowers_list if any([
            b.get('auto_birthday'), b.get('auto_anniversary'),
            b.get('auto_seasonal'), b.get('auto_equity'), b.get('auto_holidays')
        ])]),
    }
    
    # Get all unique tags
    all_tags = set()
    for borrower in borrowers_list:
        tags = borrower.get('tags', '') or ''
        if tags:
            all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
    all_tags = sorted(list(all_tags))
    
    # Get upcoming tasks
    try:
        upcoming_tasks = [dict(t) for t in all_tasks[:10]]
    except:
        upcoming_tasks = []
    
    return render_template(
        "lender/crm.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrowers=borrowers_list,
        status_filter=status_filter,
        stats=stats,
        all_tags=all_tags,
        upcoming_tasks=upcoming_tasks,
    )


@app.route("/lender/crm/import", methods=["GET", "POST"])
def lender_crm_import():
    """Lender CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "lender":
            return redirect(url_for("login", role="lender"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please select a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please select a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file.", "error")
                return redirect(url_for("lender_crm_import"))
            
            try:
                # Read file into pandas
                if filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                # Convert to list of dicts for preview
                data = df.to_dict('records')
                
                # Get column names for mapping
                columns = list(df.columns)
                
                # Store in session for import step
                session['crm_import_data'] = json.dumps(data, default=str)
                session['crm_import_columns'] = columns
                
                return render_template(
                    "lender/crm_import_preview.html",
                    brand_name=FRONT_BRAND_NAME,
                    user=user,
                    data=data[:10],  # Preview first 10 rows
                    total_rows=len(data),
                    columns=columns,
                    sample_data=data[0] if data else {},
                )
            except Exception as e:
                import traceback
                flash(f"Error reading file: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("lender_crm_import"))
        
        elif action == "import":
            # Actually import the data
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("No import data found. Please upload a file again.", "error")
                return redirect(url_for("lender_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'status': request.form.get('map_status', '').strip(),
                    'loan_type': request.form.get('map_loan_type', '').strip(),
                    'target_payment': request.form.get('map_target_payment', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'loan_amount': request.form.get('map_loan_amount', '').strip(),
                    'loan_rate': request.form.get('map_loan_rate', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                # Default status if not mapped
                default_status = request.form.get('default_status', 'prospect').strip()
                
                # Import settings
                skip_duplicates = request.form.get('skip_duplicates') == 'on'
                duplicate_check = request.form.get('duplicate_check', 'email').strip()
                
                imported = 0
                skipped = 0
                errors = []
                
                for idx, row in enumerate(data):
                    try:
                        # Map columns to fields
                        name = str(row.get(mappings['name'], '')).strip() if mappings['name'] else ''
                        email = str(row.get(mappings['email'], '')).strip() if mappings['email'] else ''
                        phone = str(row.get(mappings['phone'], '')).strip() if mappings['phone'] else ''
                        status = str(row.get(mappings['status'], default_status)).strip() if mappings['status'] else default_status
                        loan_type = str(row.get(mappings['loan_type'], '')).strip() if mappings['loan_type'] else ''
                        target_payment = str(row.get(mappings['target_payment'], '')).strip() if mappings['target_payment'] else ''
                        birthday = str(row.get(mappings['birthday'], '')).strip() if mappings['birthday'] else ''
                        home_anniversary = str(row.get(mappings['home_anniversary'], '')).strip() if mappings['home_anniversary'] else ''
                        address = str(row.get(mappings['address'], '')).strip() if mappings['address'] else ''
                        property_address = str(row.get(mappings['property_address'], '')).strip() if mappings['property_address'] else ''
                        notes = str(row.get(mappings['notes'], '')).strip() if mappings['notes'] else ''
                        tags = str(row.get(mappings['tags'], '')).strip() if mappings['tags'] else ''
                        
                        # Parse numeric values
                        try:
                            loan_amount = float(row.get(mappings['loan_amount'], 0)) if mappings['loan_amount'] and str(row.get(mappings['loan_amount'], '')).strip() else None
                        except:
                            loan_amount = None
                        
                        try:
                            loan_rate = float(row.get(mappings['loan_rate'], 0)) if mappings['loan_rate'] and str(row.get(mappings['loan_rate'], '')).strip() else None
                        except:
                            loan_rate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Check for duplicates if enabled
                        if skip_duplicates:
                            existing_borrowers = list_lender_borrowers(user["id"])
                            is_duplicate = False
                            for existing in existing_borrowers:
                                if duplicate_check == 'email' and email:
                                    if existing.get('email') and existing['email'].lower() == email.lower():
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'phone' and phone:
                                    if existing.get('phone') and existing['phone'] == phone:
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'name' and name:
                                    if existing.get('name') and existing['name'].lower() == name.lower():
                                        is_duplicate = True
                                        break
                            
                            if is_duplicate:
                                skipped += 1
                                continue
                        
                        # Add borrower
                        add_lender_borrower(
                            user["id"], name, status, loan_type, target_payment, "",
                            email, phone, birthday, home_anniversary, address, notes, tags,
                            property_address, loan_amount, loan_rate
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                flash(f"Import complete! {imported} borrowers imported, {skipped} skipped, {len(errors)} errors.", "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("lender_crm"))
            except Exception as e:
                import traceback
                flash(f"Error during import: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("lender_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "lender/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/loans", methods=["GET", "POST"])
def lender_loans():
    """Lender loans management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        borrower_name = request.form.get("borrower_name", "").strip()
        loan_amount = request.form.get("loan_amount", "").strip()
        loan_type = request.form.get("loan_type", "conventional").strip()
        status = request.form.get("status", "preapproval").strip()

        if borrower_name and loan_amount:
            try:
                add_lender_loan(user["id"], borrower_name, loan_amount, loan_type, status)
                flash("Loan added successfully!", "success")
            except Exception as e:
                flash(f"Error adding loan: {e}", "error")

    loans = list_lender_loans(user["id"])
    return render_template(
        "lender/loans.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        loans=loans,
    )


@app.route("/lender/marketing", methods=["GET"])
def lender_marketing():
    """Lender marketing tools."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/messages", methods=["GET"])
def lender_messages():
    """Lender messages."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/messages.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/roles", methods=["GET"])
def lender_roles():
    """Lender roles and partners."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/roles.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/documents", methods=["GET"])
def lender_documents():
    """Lender documents."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/documents.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/power-suite", methods=["GET"])
def lender_power_suite():
    """Lender power suite."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/power_suite.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/referrals", methods=["GET", "POST"])
def lender_referrals():
    """Lender referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    try:
        from database import (
            get_referral_links_for_lender,
            create_referral_link,
            get_referral_stats,
            get_accessible_homeowners
        )
        
        # Handle POST - create new referral link
        if request.method == "POST":
            try:
                token = create_referral_link(lender_id=user["id"])
                flash("New referral link created!", "success")
                return redirect(url_for("lender_referrals"))
            except Exception as e:
                flash(f"Error creating referral link: {str(e)}", "error")
        
        # Get all referral links for this lender
        referral_links = get_referral_links_for_lender(user["id"])
        
        # If no links exist, create one automatically
        if not referral_links:
            try:
                token = create_referral_link(lender_id=user["id"])
                referral_links = get_referral_links_for_lender(user["id"])
            except Exception as e:
                print(f"Error auto-creating referral link: {e}")
        
        # Get stats
        try:
            stats = get_referral_stats(user["id"])
        except Exception as e:
            print(f"Error getting stats: {e}")
            stats = {'total_clients': 0, 'clients_this_month': 0}
        
        # Build referral URLs
        base_url = request.url_root.rstrip('/')
        referral_links_with_urls = []
        for link in referral_links:
            link_dict = dict(link) if hasattr(link, 'keys') else link
            link_dict['url'] = f"{base_url}/signup?role=homeowner&ref={link_dict['token']}"
            referral_links_with_urls.append(link_dict)
        
        # Use the first link as primary (for backward compatibility)
        primary_link = referral_links_with_urls[0] if referral_links_with_urls else None
        referral_url = primary_link['url'] if primary_link else None
        referral_code = primary_link['token'] if primary_link else None
        
        return render_template(
            "lender/referrals.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            referral_code=referral_code,
            referral_url=referral_url,
            referral_links=referral_links_with_urls,
            stats=stats,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in lender_referrals: {error_trace}")
        flash(f"Error loading referral page: {str(e)}", "error")
        return redirect(url_for("lender_dashboard"))


@app.route("/lender/settings/profile", methods=["GET", "POST"])
def lender_settings_profile():
    """Lender settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            # Handle file uploads using consolidated helper
            professional_photo = handle_profile_file_upload("professional_photo", folder="profiles", role_prefix="LENDER ")
            brokerage_logo = handle_profile_file_upload("brokerage_logo", folder="profiles", role_prefix="LENDER ")
            
            # Preserve existing photos/logos if not uploading new ones
            professional_photo, brokerage_logo = preserve_existing_profile_media(
                user["id"], professional_photo, brokerage_logo
            )
            
            # Get form data
            print(f"LENDER PROFILE: About to save profile with photo={professional_photo}, logo={brokerage_logo}")
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="lender",
                professional_photo=professional_photo,
                brokerage_logo=brokerage_logo,
                team_name=request.form.get("team_name", "").strip() or None,
                brokerage_name=request.form.get("brokerage_name", "").strip() or None,
                website_url=request.form.get("website_url", "").strip() or None,
                facebook_url=request.form.get("facebook_url", "").strip() or None,
                instagram_url=request.form.get("instagram_url", "").strip() or None,
                linkedin_url=request.form.get("linkedin_url", "").strip() or None,
                twitter_url=request.form.get("twitter_url", "").strip() or None,
                youtube_url=request.form.get("youtube_url", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                call_button_enabled=1 if request.form.get("call_button_enabled") == "on" else 0,
                schedule_button_enabled=1 if request.form.get("schedule_button_enabled") == "on" else 0,
                schedule_url=request.form.get("schedule_url", "").strip() or None,
                application_url=request.form.get("application_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                nmls_number=request.form.get("nmls_number", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
                homebot_widget_id=request.form.get("homebot_widget_id", "").strip() or None,
                va_rate_30yr=float(request.form.get("va_rate_30yr")) if request.form.get("va_rate_30yr") else None,
                fha_rate_30yr=float(request.form.get("fha_rate_30yr")) if request.form.get("fha_rate_30yr") else None,
                conventional_rate_30yr=float(request.form.get("conventional_rate_30yr")) if request.form.get("conventional_rate_30yr") else None,
            )
            flash("Profile updated successfully!", "success")
            return redirect(url_for("lender_settings_profile"))
        except Exception as e:
            import traceback
            print(f"Error updating profile: {traceback.format_exc()}")
            flash(f"Error updating profile: {str(e)}", "error")
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})
    
    return render_template(
        "lender/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
    )


# -------------------------------------------------
# HOMEOWNER ROUTES (Missing)
# -------------------------------------------------
@app.route("/homeowner/reno/roi-guide", methods=["GET"])
def homeowner_reno_roi_guide():
    """Renovation ROI guide."""
    return render_template(
        "homeowner/reno_roi_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/plan-my-move", methods=["GET", "POST"])
def homeowner_next_plan_move():
    """Plan my move - next home planning questionnaire."""
    import json
    user = get_current_user()
    if request.method == "POST":
        # Collect all questionnaire data
        questionnaire_data = {
            # Personal Information
            "legal_name": request.form.get("legal_name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "birthday": request.form.get("birthday", "").strip(),
            # Home Purchase Basics
            "preapproved": request.form.get("preapproved", "").strip(),
            "timeline": request.form.get("timeline", "").strip(),
            "budget": request.form.get("budget", "").strip(),
            "beds_baths": request.form.get("beds_baths", "").strip(),
            "must_haves": request.form.get("must_haves", "").strip(),
            "areas": request.form.get("areas", "").strip(),
            # Property Preferences
            "floor_plan": request.form.get("floor_plan", "").strip(),
            "important_items": request.form.get("important_items", "").strip(),
            "garage_specifics": request.form.get("garage_specifics", "").strip(),
            "requirements": request.form.get("requirements", "").strip(),
            "home_type": request.form.get("home_type", "").strip(),
            "construction_type": request.form.get("construction_type", "").strip(),
            "condition": request.form.get("condition", "").strip(),
            "lot_size": request.form.get("lot_size", "").strip(),
            "architectural_style": request.form.get("architectural_style", "").strip(),
            # Location & Lifestyle
            "school_districts": request.form.get("school_districts", "").strip(),
            "transportation": request.form.get("transportation", "").strip(),
            "contact_method": request.form.get("contact_method", "").strip(),
            # Additional Information
            "dealbreakers": request.form.get("dealbreakers", "").strip(),
            "feeling": request.form.get("feeling", "").strip(),
            "other_info": request.form.get("other_info", "").strip(),
        }
        
        # Map to database fields (existing structure)
        timeline = questionnaire_data.get("timeline", "")
        budget_range = questionnaire_data.get("budget", "")
        location_preferences = questionnaire_data.get("areas", "")
        property_type_preferences = f"{questionnaire_data.get('home_type', '')} | {questionnaire_data.get('construction_type', '')} | {questionnaire_data.get('condition', '')}".strip(" |")
        must_haves = questionnaire_data.get("must_haves", "")
        nice_to_haves = f"{questionnaire_data.get('important_items', '')} | {questionnaire_data.get('architectural_style', '')}".strip(" |")
        concerns = questionnaire_data.get("dealbreakers", "")
        # Store all detailed data in notes as JSON
        notes = json.dumps(questionnaire_data, indent=2)
        
        if user:
            upsert_next_move_plan(
                user["id"],
                timeline=timeline,
                budget_range=budget_range,
                location_preferences=location_preferences,
                property_type_preferences=property_type_preferences,
                must_haves=must_haves,
                nice_to_haves=nice_to_haves,
                concerns=concerns,
                notes=notes,
            )
            flash("Your home buyer questionnaire has been saved!", "success")

    plan = get_next_move_plan(user["id"]) if user else None
    # Parse JSON notes if present
    if plan and hasattr(plan, 'notes') and plan.notes:
        try:
            plan_dict = dict(plan) if hasattr(plan, 'keys') else plan
            parsed_notes = json.loads(plan_dict.get('notes', '{}'))
            # Merge parsed data back into plan for template access
            if isinstance(plan_dict, dict):
                plan_dict.update(parsed_notes)
                plan = type('obj', (object,), plan_dict)
        except:
            pass
    
    return render_template(
        "homeowner/next_plan_move.html",
        brand_name=FRONT_BRAND_NAME,
        plan=plan,
    )


@app.route("/homeowner/next/buy-sell-guidance", methods=["GET"])
def homeowner_next_buy_sell_guidance():
    """Buy and sell guidance."""
    return render_template(
        "homeowner/next_buy_sell_guidance.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/loan-paths", methods=["GET"])
def homeowner_next_loan_paths():
    """Loan paths guidance."""
    return render_template(
        "homeowner/next_loan_paths.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/affordability", methods=["GET"])
def homeowner_next_affordability():
    """Affordability calculator."""
    return render_template(
        "homeowner/next_affordability.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/maintenance-guide", methods=["GET"])
def homeowner_care_maintenance_guide():
    """Home maintenance guide."""
    return render_template(
        "homeowner/care_maintenance_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/seasonal-checklists", methods=["GET"])
def homeowner_care_seasonal_checklists():
    """Seasonal maintenance checklists."""
    return render_template(
        "homeowner/care_seasonal_checklists.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/home-protection", methods=["GET"])
def homeowner_care_home_protection():
    """Home protection guide."""
    return render_template(
        "homeowner/care_home_protection.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/warranty-log", methods=["GET", "POST"])
def homeowner_care_warranty_log():
    """Warranty log - add, view, and delete warranty items."""
    from database import get_current_user, add_warranty_log_item, list_warranty_log_items, delete_warranty_log_item
    from datetime import datetime
    
    user = get_current_user()
    if not user:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))
    
    if user.get("role") != "homeowner":
        flash("This page is for homeowners only.", "error")
        return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
    
    homeowner_id = user["id"]
    
    # Handle POST requests
    if request.method == "POST":
        # Handle delete
        if request.form.get("delete_id"):
            item_id = int(request.form.get("delete_id"))
            if delete_warranty_log_item(item_id, homeowner_id):
                flash("Warranty item deleted successfully.", "success")
            else:
                flash("Error deleting warranty item.", "error")
            return redirect(url_for("homeowner_care_warranty_log"))
        
        # Handle add new item
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "").strip()
        
        if not item_name or not category:
            flash("Item name and category are required.", "error")
            return redirect(url_for("homeowner_care_warranty_log"))
        
        purchase_date = request.form.get("purchase_date") or None
        warranty_start = request.form.get("warranty_start") or None
        warranty_expiry = request.form.get("warranty_expiry") or None
        warranty_provider = request.form.get("warranty_provider", "").strip() or None
        warranty_number = request.form.get("warranty_number", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        
        try:
            add_warranty_log_item(
                user_id=homeowner_id,
                item_name=item_name,
                category=category,
                purchase_date=purchase_date,
                warranty_start=warranty_start,
                warranty_expiry=warranty_expiry,
                warranty_provider=warranty_provider,
                warranty_number=warranty_number,
                notes=notes
            )
            flash("Warranty item added successfully!", "success")
        except Exception as e:
            print(f"[WARRANTY LOG] Error adding item: {e}")
            import traceback
            traceback.print_exc()
            flash(f"Error adding warranty item: {str(e)}", "error")
        
        return redirect(url_for("homeowner_care_warranty_log"))
    
    # GET request - display items
    warranty_items = list_warranty_log_items(homeowner_id)
    
    return render_template(
        "homeowner/care_warranty_log.html",
        brand_name=FRONT_BRAND_NAME,
        warranty_items=warranty_items,
        now=datetime.now()
    )


@app.route("/homeowner/care/energy-savings", methods=["GET"])
def homeowner_care_energy_savings():
    """Energy savings guide."""
    return render_template(
        "homeowner/care_energy_savings.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/ask-question", methods=["GET", "POST"])
def homeowner_support_ask_question():
    """Ask a question."""
    user = get_current_user()
    if request.method == "POST":
        topic = request.form.get("topic", "").strip() or None
        question = request.form.get("question", "").strip()
        if question and user:
            add_homeowner_question(user["id"], topic or "General", question)
            flash("Question submitted! We'll get back to you soon.", "success")
            return redirect(url_for("homeowner_support_ask_question"))
        elif not question:
            flash("Please enter your question.", "error")

    return render_template(
        "homeowner/support_ask_question.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/chat-human", methods=["GET"])
def homeowner_support_chat_human():
    """Chat with human support."""
    return render_template(
        "homeowner/support_chat_human.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/schedule-chat", methods=["GET"])
def homeowner_support_schedule_chat():
    """Schedule a chat."""
    return render_template(
        "homeowner/support_schedule_chat.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/resources", methods=["GET"])
def homeowner_support_resources():
    """Support resources."""
    return render_template(
        "homeowner/support_resources.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/meet-team", methods=["GET"])
def homeowner_support_meet_team():
    """Meet the team."""
    return render_template(
        "homeowner/support_meet_team.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ---------------- HOMEBOT WEBHOOK ----------------
@app.route("/api/homebot/webhook", methods=["POST"])
def homebot_webhook():
    """
    Webhook endpoint for Homebot to send homeowner data updates.
    When a homeowner links their account in Homebot, this endpoint receives
    their loan and property information and updates the YLYH database.
    """
    from database import (
        get_user_by_email, 
        get_primary_property,
        get_user_properties,
        get_property_by_id,
        upsert_homeowner_snapshot_for_property,
        add_property,
        get_connection
    )
    
    try:
        # Get JSON data from Homebot
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        # Homebot typically sends: email, address, loan_balance, loan_rate, 
        # loan_payment, home_value, etc.
        email = data.get("email") or data.get("homeowner_email")
        if not email:
            return jsonify({"error": "Email is required"}), 400
        
        # Find homeowner by email
        homeowner = get_user_by_email(email.lower().strip())
        if not homeowner:
            # Homeowner doesn't exist in YLYH yet - log for manual review
            print(f"HOMEBOT WEBHOOK: Homeowner with email {email} not found in YLYH")
            return jsonify({
                "error": "Homeowner not found",
                "message": "Homeowner must have a YLYH account first"
            }), 404
        
        if homeowner.get("role") != "homeowner":
            return jsonify({"error": "User is not a homeowner"}), 400
        
        homeowner_id = homeowner["id"]
        
        # Get or create property
        property_address = data.get("address") or data.get("property_address") or "My Home"
        properties = get_user_properties(homeowner_id)
        current_property = get_primary_property(homeowner_id)
        
        if not current_property:
            # Create property if it doesn't exist
            property_id = add_property(homeowner_id, property_address, None, "primary")
            current_property = get_property_by_id(property_id)
        else:
            property_id = current_property["id"]
        
        # Extract loan and property data from Homebot
        # Homebot field names may vary, so we check multiple possibilities
        home_value = (
            data.get("home_value") or 
            data.get("current_value") or 
            data.get("property_value") or
            data.get("estimated_value")
        )
        
        loan_balance = (
            data.get("loan_balance") or 
            data.get("mortgage_balance") or
            data.get("outstanding_balance")
        )
        
        loan_rate = (
            data.get("loan_rate") or 
            data.get("interest_rate") or
            data.get("mortgage_rate")
        )
        
        loan_payment = (
            data.get("loan_payment") or 
            data.get("monthly_payment") or
            data.get("mortgage_payment")
        )
        
        loan_term_years = data.get("loan_term_years") or data.get("term_years")
        loan_start_date = data.get("loan_start_date") or data.get("origination_date")
        
        # Convert string numbers to floats
        def safe_float(val):
            if val is None or val == "":
                return None
            try:
                return float(str(val).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                return None
        
        # Update homeowner snapshot with Homebot data
        from datetime import datetime
        import time
        
        # Mark data as synced from Homebot
        upsert_homeowner_snapshot_for_property(
            user_id=homeowner_id,
            property_id=property_id,
            value_estimate=safe_float(home_value),
            loan_balance=safe_float(loan_balance),
            loan_rate=safe_float(loan_rate),
            loan_payment=safe_float(loan_payment),
            loan_term_years=safe_float(loan_term_years),
            loan_start_date=loan_start_date,
        )
        
        # Mark data source as Homebot
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """UPDATE homeowner_snapshots 
               SET value_refresh_source = 'Homebot',
                   last_value_refresh = ?
               WHERE user_id = ? AND property_id = ?""",
            (datetime.now().isoformat(), homeowner_id, property_id)
        )
        conn.commit()
        conn.close()
        
        # Update property estimated value if provided
        if home_value:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE properties SET estimated_value = ? WHERE id = ?",
                (safe_float(home_value), property_id),
            )
            conn.commit()
            conn.close()
        
        print(f"HOMEBOT WEBHOOK: Successfully updated homeowner {homeowner_id} (email: {email})")
        
        return jsonify({
            "success": True,
            "message": "Homeowner data updated successfully",
            "homeowner_id": homeowner_id,
            "property_id": property_id
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"HOMEBOT WEBHOOK ERROR: {str(e)}")
        print(error_trace)
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500


# ---------------- DEVELOPMENT SERVER ----------------
if __name__ == "__main__":
    # Only runs when executing directly with Python (not with gunicorn)
    # Gunicorn will import the app and won't execute this block
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,  # Enable debug mode for development
        use_reloader=False,  # Disable reloader on Windows to avoid import issues
    )

