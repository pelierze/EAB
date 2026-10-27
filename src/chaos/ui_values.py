"""Language-neutral exploration selections and legacy preset migration."""

RANK_PRIORITIES = (1, 2, 3, 4, None)
DEFAULT_PRIORITIES = {'warrior': 1, 'thief': 2, 'knight': 3, 'soul_weaver': None}
LEGACY_RANK_PRIORITIES = {'1순위': 1, '2순위': 2, '3순위': 3, '4순위': 4, '제외': None}


def priority_index(value):
    """Decode a stored number/null, or an older Korean preset's label."""
    if isinstance(value, str) and value in LEGACY_RANK_PRIORITIES:
        value = LEGACY_RANK_PRIORITIES[value]
    if value is None:
        return 4
    if type(value) is int and value in (1, 2, 3, 4):
        return value - 1
    raise ValueError('Invalid exploration rank priority')


def selected_priority(combo):
    """Read a readonly combobox by index, never by its translated label."""
    index = combo.current()
    if type(index) is not int or not 0 <= index < len(RANK_PRIORITIES):
        raise ValueError('Select a rank-up priority for each class.')
    return RANK_PRIORITIES[index]
