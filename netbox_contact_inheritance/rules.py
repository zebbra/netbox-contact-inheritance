"""
Pure inheritance rules, free of Django imports so they can be tested without NetBox.

Every object in the hierarchy has a level. An assignment made on a source object reaches a target
object below it if the target's level is not deeper than the assignment's inherit depth.
"""

# Hierarchy levels from top to bottom. Region and site group are parallel branches above a site.
LEVEL_RANK = {
    'region': 0,
    'sitegroup': 0,
    'site': 1,
    'location': 2,
    'rack': 3,
    'device': 4,
}

# Values of the inherit depth choice: how far down an assignment reaches.
DEPTH_NONE = 'none'
DEPTH_CHOICES = ('none', 'site', 'location', 'rack', 'device')
DEFAULT_DEPTH = 'device'

PRIORITY_ORDER = {'primary': 0, 'secondary': 1, 'tertiary': 2, '': 3, None: 3, 'inactive': 4}


def normalize_depth(value, default=DEFAULT_DEPTH):
    if value in DEPTH_CHOICES:
        return value
    return default


def reaches(target_level, depth, inherited=True):
    """
    Return True if an assignment with the given inherit depth applies to a target at target_level.
    Direct assignments (inherited=False) always apply.
    """
    if not inherited:
        return True
    if depth == DEPTH_NONE:
        return False
    return LEVEL_RANK[target_level] <= LEVEL_RANK[depth]


def pick_nearest(candidates):
    """
    Keep the nearest candidate per (contact, role).

    candidates: iterable of dicts with at least 'contact', 'role' and 'distance' keys.
    Returns the kept candidates ordered by priority, then distance.
    """
    nearest = {}
    for c in candidates:
        key = (c['contact'], c['role'])
        if key not in nearest or c['distance'] < nearest[key]['distance']:
            nearest[key] = c
    return sorted(
        nearest.values(),
        key=lambda c: (PRIORITY_ORDER.get(c.get('priority'), 3), c['distance'], str(c.get('sort_name', ''))),
    )
