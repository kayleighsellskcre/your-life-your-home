#!/usr/bin/env python3
"""
Script to add luxury layout HTML to all lender marketing templates
Adapts agent fields to lender fields: price -> loan_amount, property_address -> borrower_name
"""

# Read the agent just-listed template to extract layout structure
with open('templates/agent/marketing_templates/just-listed_flyer.html', 'r', encoding='utf-8') as f:
    agent_content = f.read()

# Extract all layout HTML blocks
start_marker = "{% if layout_style == 'magazine' and property_photos and property_photos|length > 0 %}"
end_marker = "{% else %}\n    <!-- Standard Layouts: Classic, Hero, Gallery, Minimal -->"

start_idx = agent_content.find(start_marker)
end_idx = agent_content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("[ERROR] Could not find layout markers!")
    exit(1)

agent_layouts_html = agent_content[start_idx:end_idx].rstrip()

# Adapt for lenders: replace agent-specific fields with lender fields
lender_layouts_html = agent_layouts_html.replace("{{ price or '$799,000' }}", "{{ loan_amount or '$350,000' }}")
lender_layouts_html = lender_layouts_html.replace("{{ property_address or transaction.property_address or '123 Main Street' }}", "{{ borrower_name or 'Your Client' }}")

# Change "Just Listed" to template-appropriate defaults (will be overridden by actual headline)
lender_layouts_html = lender_layouts_html.replace("{{ headline or 'Just Listed' }}", "{{ headline or 'Pre-Approval Ready' }}")
lender_layouts_html = lender_layouts_html.replace("{{ subtext or 'Luxury Living Awaits' }}", "{{ subtext or 'Let\\'s Make It Happen' }}")

print(f"[INFO] Prepared {len(lender_layouts_html)} chars of adapted lender layout HTML\n")

templates = [
    'templates/lender/marketing_templates/pre-approval_flyer.html',
    'templates/lender/marketing_templates/closing_flyer.html',
    'templates/lender/marketing_templates/rate-announcement_flyer.html',
    'templates/lender/marketing_templates/refinance_flyer.html',
    'templates/lender/marketing_templates/education_flyer.html',
    'templates/lender/marketing_templates/agent-thank-you_flyer.html',
]

for template_path in templates:
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find where to insert (after decorative-header or print button)
    insert_marker = '<div class="decorative-header"></div>'
    insert_point = content.find(insert_marker)
    
    if insert_point == -1:
        insert_marker = '<button class="print-button" onclick="window.print()">🖨️ Print to PDF</button>'
        insert_point = content.find(insert_marker)
        if insert_point == -1:
            print(f'[WARN] Could not find insertion point in {template_path}')
            continue
    
    insert_point += len(insert_marker)
    
    # Check if already has luxury layouts
    if "layout_style == 'magazine'" in content:
        print(f'[SKIP] {template_path} already has luxury layouts')
        continue
    
    # Insert the adapted lender layout HTML
    new_content = content[:insert_point] + "\n    \n    " + lender_layouts_html + "\n    " + content[insert_point:]
    
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f'[OK] Added all luxury layouts HTML to {template_path}')

print('\n[DONE] All lender templates updated with luxury layout HTML!')

