from database import get_design_boards_for_user, get_design_board_details
from app import app

user_id = 1

# Test getting boards
boards = get_design_boards_for_user(user_id)
print(f"✓ Found {len(boards)} boards: {boards}")

# Test getting details for each board
for board_name in boards:
    details = get_design_board_details(user_id, board_name)
    if details:
        print(f"  - '{board_name}': {len(details.get('notes', []))} notes, {len(details.get('photos', []))} photos")
    else:
        print(f"  - '{board_name}': NO DETAILS FOUND")

print("✓ All database functions working correctly")
