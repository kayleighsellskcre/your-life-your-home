from database import add_design_board_note, get_design_boards_for_user

add_design_board_note(1, 'TestBoard', 'TB Title', 'TB details', ['uploads/design_boards/a.jpg'], [])
print('boards:', get_design_boards_for_user(1))
