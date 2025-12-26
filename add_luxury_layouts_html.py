#!/usr/bin/env python3
"""
Script to add luxury layout HTML to all agent marketing templates
"""

# Read the just-listed template to extract ALL new layout HTML (magazine through split)
with open('templates/agent/marketing_templates/just-listed_flyer.html', 'r', encoding='utf-8') as f:
    source_content = f.read()

# Extract all layout HTML blocks (magazine, showcase, modern, editorial, collection, split)
start_marker = "{% if layout_style == 'magazine' and property_photos and property_photos|length > 0 %}"
end_marker = "{% else %}\n    <!-- Standard Layouts: Classic, Hero, Gallery, Minimal -->"

start_idx = source_content.find(start_marker)
end_idx = source_content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("[ERROR] Could not find layout markers in just-listed template!")
    print(f"start_idx: {start_idx}, end_idx: {end_idx}")
    exit(1)

# Extract and keep proper indentation
all_layouts_html = source_content[start_idx:end_idx].rstrip()

print(f"[INFO] Extracted {len(all_layouts_html)} chars of layout HTML\n")

# List of templates to update
templates = [
    'templates/agent/marketing_templates/coming-soon_flyer.html',
    'templates/agent/marketing_templates/open-house_flyer.html',
    'templates/agent/marketing_templates/price-reduction_flyer.html',
    'templates/agent/marketing_templates/under-contract_flyer.html',
    'templates/agent/marketing_templates/back-on-market_flyer.html',
    'templates/agent/marketing_templates/sold_flyer.html',
    'templates/agent/marketing_templates/just-listed_postcard.html',
]

for template_path in templates:
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find where to insert (after <div class="decorative-header"></div> OR after print button)
    insert_marker = '<div class="decorative-header"></div>'
    insert_point = content.find(insert_marker)
    
    if insert_point == -1:
        # Try alternate: after print button
        insert_marker = '<button class="print-button" onclick="window.print()">🖨️ Print to PDF</button>'
        insert_point = content.find(insert_marker)
        if insert_point == -1:
            print(f'[WARN] Could not find insertion point in {template_path}')
            continue
    
    # Move past the marker and newline
    insert_point += len(insert_marker)
    
    # Check if luxury layouts already exist
    if "layout_style == 'magazine'" in content:
        print(f'[SKIP] {template_path} already has luxury layouts')
        continue
    
    # Insert the layout HTML block after the header
    new_content = content[:insert_point] + "\n    \n    " + all_layouts_html + "\n    " + content[insert_point:]
    
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f'[OK] Added all luxury layouts HTML to {template_path}')

print('\n[DONE] All templates updated with luxury layout HTML!')


