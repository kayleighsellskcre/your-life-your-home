#!/usr/bin/env python3
"""
Script to add luxury layouts CSS to all lender marketing templates
"""

LUXURY_CSS = '''
        /* ============================================
           DESIGNER LUXURY LAYOUTS - Magazine Quality
           ============================================ */
        
        /* Magazine Editorial Layout - Asymmetric */
        .layout-magazine {
            display: block !important;
            padding: 0.75in !important;
            position: relative;
        }
        
        .magazine-hero {
            width: 100%;
            height: 5.5in;
            object-fit: cover;
            border-radius: 0;
            margin-bottom: 0.4in;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
        }
        
        .magazine-inset {
            position: absolute;
            bottom: 1.5in;
            right: 1in;
            width: 2.5in;
            height: 2in;
            object-fit: cover;
            border: 6px solid white;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
            z-index: 10;
        }
        
        .magazine-text-block {
            background: rgba(255, 255, 255, 0.95);
            padding: 0.5in;
            margin-top: -0.6in;
            position: relative;
            z-index: 5;
            border-top: 3px solid var(--accent-color);
        }
        
        /* Luxury Showcase Layout */
        .layout-showcase {
            display: grid !important;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: auto 1fr auto;
            gap: 0.3in;
            padding: 0.6in !important;
        }
        
        .showcase-hero {
            grid-column: 1 / -1;
            width: 100%;
            height: 4.5in;
            object-fit: cover;
            border-radius: 8px;
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.18);
        }
        
        .showcase-secondary {
            width: 100%;
            aspect-ratio: 4/3;
            object-fit: cover;
            border-radius: 6px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
        }
        
        .showcase-text {
            grid-column: 1 / -1;
            text-align: center;
            padding: 0.4in 0.6in;
            background: linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(248,246,240,0.95) 100%);
            border-radius: 10px;
        }
        
        /* Modern Elegance Layout - Overlapping */
        .layout-modern {
            display: block !important;
            padding: 0.8in 1in !important;
            position: relative;
        }
        
        .modern-primary {
            width: 6in;
            height: 4.5in;
            object-fit: cover;
            border-radius: 0;
            box-shadow: 0 15px 45px rgba(0, 0, 0, 0.22);
            margin-left: 0.5in;
        }
        
        .modern-overlay {
            position: absolute;
            top: 3.5in;
            left: 0.8in;
            width: 3in;
            height: 2.5in;
            object-fit: cover;
            border: 8px solid white;
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.28);
            z-index: 10;
        }
        
        .modern-text-zone {
            margin-top: 1.2in;
            padding: 0.5in;
            background: white;
            border-left: 4px solid var(--accent-color);
        }
        
        /* Editorial Portfolio Layout - Angular */
        .layout-editorial {
            display: grid !important;
            grid-template-columns: 2.8in 1fr;
            grid-template-rows: 3.5in auto 1fr;
            gap: 0.25in;
            padding: 0.7in !important;
        }
        
        .editorial-tall {
            grid-row: 1 / 3;
            width: 100%;
            height: 100%;
            object-fit: cover;
            clip-path: polygon(0 0, 100% 0, 100% 95%, 0 100%);
            box-shadow: 0 12px 38px rgba(0, 0, 0, 0.2);
        }
        
        .editorial-wide {
            grid-column: 2;
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 6px;
            box-shadow: 0 8px 28px rgba(0, 0, 0, 0.15);
        }
        
        .editorial-text {
            grid-column: 1 / -1;
            padding: 0.4in;
            background: linear-gradient(135deg, rgba(var(--primary-rgb, 107, 106, 69), 0.08) 0%, rgba(var(--accent-rgb, 200, 180, 151), 0.08) 100%);
            border-radius: 8px;
        }
        
        /* Premium Collection Layout - Multi-Photo Spread */
        .layout-collection {
            display: grid !important;
            grid-template-columns: repeat(3, 1fr);
            grid-template-rows: 2.5in 2in auto;
            gap: 0.2in;
            padding: 0.6in !important;
        }
        
        .collection-featured {
            grid-column: 1 / 3;
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 8px 0 0 8px;
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.18);
        }
        
        .collection-side {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 0 8px 8px 0;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
        }
        
        .collection-secondary {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 6px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
        }
        
        .collection-text {
            grid-column: 1 / -1;
            text-align: center;
            padding: 0.3in 0.4in;
            background: white;
            border-top: 2px solid var(--accent-color);
        }
        
'''

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
    
    # Find the insertion point (before .print-button)
    marker = '.print-button {'
    if marker in content:
        content = content.replace(marker, LUXURY_CSS + marker, 1)
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'[OK] Added luxury layouts CSS to {template_path}')
    else:
        print(f'[WARN] Could not find marker in {template_path}')

print('\n[DONE] All lender templates updated with CSS.')

