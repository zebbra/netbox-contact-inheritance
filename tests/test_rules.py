import importlib.util
from pathlib import Path

# Load rules.py directly so the tests run without NetBox installed
_spec = importlib.util.spec_from_file_location(
    'rules', Path(__file__).parent.parent / 'netbox_contact_inheritance' / 'rules.py'
)
rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rules)


def test_direct_always_applies():
    assert rules.reaches('device', 'none', inherited=False)
    assert rules.reaches('device', 'site', inherited=False)


def test_none_blocks_inheritance():
    assert not rules.reaches('site', 'none')
    assert not rules.reaches('region', 'none')


def test_depth_limits_levels():
    assert rules.reaches('site', 'location')
    assert rules.reaches('location', 'location')
    assert not rules.reaches('rack', 'location')
    assert not rules.reaches('device', 'location')
    assert rules.reaches('device', 'device')


def test_nested_parent_reaches_child_of_same_level():
    # parent region to child region, parent location to child location
    assert rules.reaches('region', 'site')
    assert rules.reaches('location', 'location')
    assert not rules.reaches('location', 'site')


def test_normalize_depth():
    assert rules.normalize_depth('rack') == 'rack'
    assert rules.normalize_depth(None) == 'device'
    assert rules.normalize_depth('', 'site') == 'site'
    assert rules.normalize_depth('bogus') == 'device'


def c(contact, role, distance, priority=''):
    return {'contact': contact, 'role': role, 'distance': distance, 'priority': priority}


def test_pick_nearest_keeps_closest_per_contact_and_role():
    kept = rules.pick_nearest([c(1, 1, 3), c(1, 1, 1), c(1, 2, 3)])
    assert sorted((k['contact'], k['role'], k['distance']) for k in kept) == [(1, 1, 1), (1, 2, 3)]


def test_pick_nearest_orders_by_priority_then_distance():
    kept = rules.pick_nearest([c(1, 1, 0, 'secondary'), c(2, 1, 4, 'primary'), c(3, 1, 1, '')])
    assert [k['contact'] for k in kept] == [2, 1, 3]
