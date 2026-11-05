# Fixtures & Furniture Feature for Mood Boards

## Overview
The mood board system now supports uploading **fixtures and furniture items** that appear as overlay elements strategically positioned around your photo collage. This creates a more dynamic, editorial-style presentation perfect for interior design boards.

## How It Works

### 1. Upload Fixtures
When creating or editing a mood board, you'll see a new upload section:
- **"Add Fixtures & Furniture"** - Upload images of furniture, lighting, hardware, or decor items
- These images are stored separately from regular inspiration photos
- They appear as floating overlay elements on the mood board

### 2. Background Removal
The system uses CSS blend modes to help remove white/light backgrounds from fixture images:
- Works best with product images on white backgrounds
- Uses `mix-blend-mode: multiply` for automatic background blending
- For advanced background removal, see the **Optional Background Removal Tool** below

### 3. Strategic Positioning
Fixtures are automatically positioned around the photo collage:
- First fixture: top-left, rotated -8°
- Second fixture: top-right, rotated +6°
- Third fixture: bottom-left, rotated +4°
- Fourth fixture: bottom-right, rotated -5°
- Additional fixtures: positioned at mid-height on sides

CSS automatically handles:
- Drop shadows for depth
- Hover effects (scale and enhanced shadows)
- Responsive sizing (140px - 200px widths)
- Slight rotations for organic feel

## Usage Guide

### Creating a New Board with Fixtures
1. Go to **Design Boards** page
2. Fill out board name and details
3. Upload inspiration photos in the **"Add Photos"** section
4. Upload furniture/fixture images in the **"Add Fixtures & Furniture"** section
5. Click **Create Board**

### Adding Fixtures to Existing Board
1. Open any mood board
2. Click the **"+ Add Photos"** button in the top action bar
3. In the modal, scroll to **"Add Fixtures/Furniture"** section
4. Select fixture images and submit

### Best Practices for Fixture Images
✅ **Recommended:**
- Product photos on white or light backgrounds
- High-resolution images (at least 800px width)
- PNG format with transparency (if available)
- Isolated furniture/decor items (not room scenes)

❌ **Avoid:**
- Dark backgrounds
- Busy/patterned backgrounds
- Low-resolution images
- Multiple items in one photo

## Optional: Advanced Background Removal

For professional-quality background removal, you can use the included Python script:

### Setup
```powershell
# Install required libraries
pip install rembg pillow
```

### Usage
```powershell
# Remove background from a single image
python scripts/remove_background.py input_chair.jpg output_chair.png

# Process multiple images
python scripts/remove_background.py fixture1.jpg fixture1_nobg.png
python scripts/remove_background.py light.jpg light_nobg.png
```

The script:
- Uses AI-based background removal (rembg library)
- Outputs PNG images with transparency
- Automatically handles various image formats
- Provides clear success/error messages

### Workflow with Background Removal
1. Upload fixture images to your computer
2. Run `remove_background.py` on each fixture image
3. Upload the processed PNG files to your mood board
4. Result: Clean fixture overlays with perfect transparency

## Database Schema
The system stores fixtures in the `homeowner_notes` table:
```sql
fixtures TEXT -- JSON array of fixture image paths
```

Example stored data:
```json
["uploads/design_boards/abc123_fixture_chair.png", "uploads/design_boards/def456_fixture_lamp.png"]
```

## Technical Details

### CSS Classes
- `.fixtures-layer` - Absolute positioned container for all fixtures
- `.fixture-item` - Individual fixture with drop shadow and hover effects
- `.fixture-item:nth-child(n)` - Strategic positioning for up to 6 fixtures

### File Naming Convention
Fixture images are saved with `_fixture_` in the filename:
```
{uuid}_fixture_{original_filename}
```

Example: `4a7b3c2d_fixture_modern_chair.png`

### Frontend Display
The board detail page checks for fixtures and renders them:
```jinja2
{% if selected_details.fixtures and selected_details.fixtures|length > 0 %}
  <div class="fixtures-layer">
    {% for fixture in selected_details.fixtures %}
      <div class="fixture-item">
        <img src="{{ url_for('static', filename=fixture) }}" />
      </div>
    {% endfor %}
  </div>
{% endif %}
```

### Backend Processing
In `app.py`, fixture uploads are handled similarly to photos:
```python
# Process uploaded fixtures
saved_fixtures = []
fixture_files = request.files.getlist("board_fixtures")
for f in fixture_files:
    # ... save with _fixture_ prefix
    saved_fixtures.append(rel_path)

# Store in database
add_design_board_note(..., fixtures=saved_fixtures)
```

## Examples & Use Cases

### Interior Design Boards
- Add furniture pieces around room inspiration photos
- Overlay lighting fixtures next to lighting mood images
- Position hardware/fixtures near detail shots

### Product Curation
- Create editorial-style product presentations
- Show multiple furniture options around a room concept
- Build "shopping list" boards with curated items

### Style Guides
- Combine room photos with specific product recommendations
- Create visual shopping guides for clients
- Build cohesive design presentations

## Troubleshooting

**Fixtures don't appear:**
- Check browser console for image loading errors
- Verify fixtures are uploaded successfully (check database)
- Ensure fixture images are valid image files

**Background not removed:**
- Use the optional `remove_background.py` script for clean results
- Or manually edit images to have transparent backgrounds
- Ensure images are on white/light backgrounds for CSS blend mode to work

**Fixtures overlap photos:**
- This is intentional for editorial style
- Adjust by re-uploading with different fixture selections
- Future enhancement: drag-and-drop repositioning (not yet implemented)

**Too many fixtures:**
- CSS handles up to 6 fixtures elegantly
- Beyond 6, fixtures may overlap awkwardly
- Consider creating multiple boards for different fixture groups

## Future Enhancements
Potential improvements for this feature:
- [ ] Drag-and-drop repositioning of fixtures
- [ ] Custom rotation angles
- [ ] Size adjustment controls
- [ ] Layering/z-index controls
- [ ] Built-in background removal (server-side)
- [ ] Fixture labels/annotations
- [ ] Export as PDF with fixtures

## Support
For issues or questions about the fixtures feature:
1. Check fixture images are valid and properly formatted
2. Verify uploads completed successfully
3. Review browser console for JavaScript errors
4. Check database for fixture data: `SELECT fixtures FROM homeowner_notes WHERE project_name = 'BoardName'`
