"""Inventories for players and NPCs: take, drop, put in/take from containers, give. The state machine
enforces the rules; the model only names the objects."""
from __future__ import annotations

from .types import Event

MAX_LIFT = 20      # heavier objects (a statue, the mailbox) cannot be picked up
MAX_CARRY = 25     # total weight a player can carry


def _w(o) -> float:
    return float(getattr(o.properties, "weight", 5) or 0)


def _detach(world, obj) -> None:
    """Remove obj from wherever it is in the current room (floor or a container)."""
    if obj in world.current.objects:
        world.current.objects.remove(obj)
        return
    for o in world.current.objects:
        if obj in getattr(o, "contents", []):
            o.contents.remove(obj)
            return


def take(world, inv: list, obj, source=None) -> Event:
    name = obj.properties.name
    if obj in inv:
        return Event("take", False, name, None, {}, f"You already have the {name}.")
    if _w(obj) > MAX_LIFT:
        return Event("take", False, name, None, {}, f"The {name} is far too heavy to pick up.")
    if sum(_w(i) for i in inv) + _w(obj) > MAX_CARRY:
        return Event("take", False, name, None, {}, f"You can't carry the {name} as well; your hands are full.")
    if source is not None and hasattr(source, "contents") and not getattr(source.states, "open", True):
        return Event("take", False, name, None, {}, f"The {source.properties.name} is closed.")
    _detach(world, obj)
    inv.append(obj)
    src = f" from the {source.properties.name}" if source is not None and hasattr(source, "contents") else ""
    return Event("take", True, name, source.properties.name if src else None, {f"{name}.held": True},
                 f"You take the {name}{src}.")


def drop(world, inv: list, obj) -> Event:
    name = obj.properties.name
    if obj not in inv:
        return Event("drop", False, name, None, {}, f"You aren't carrying the {name}.")
    inv.remove(obj)
    world.current.objects.append(obj)
    return Event("drop", True, name, None, {f"{name}.held": False}, f"You drop the {name}.")


def put(world, inv: list, obj, container) -> Event:
    name = obj.properties.name
    if container is None or not hasattr(container, "contents"):
        return Event("put", False, name, None, {}, f"You can't put things in that.")
    cname = container.properties.name
    if not getattr(container.states, "open", True):
        return Event("put", False, name, cname, {}, f"The {cname} is closed.")
    if obj in inv:
        inv.remove(obj)
    else:
        if _w(obj) > MAX_LIFT:
            return Event("put", False, name, cname, {}, f"The {name} is far too heavy to move.")
        _detach(world, obj)
    container.contents.append(obj)
    return Event("put", True, name, cname, {f"{name}.in": cname}, f"You put the {name} in the {cname}.")


def give(inv: list, obj, npc) -> Event:
    name = obj.properties.name
    if obj not in inv:
        return Event("give", False, name, None, {}, f"You aren't carrying the {name}.")
    inv.remove(obj)
    npc.inventory.append(obj)
    return Event("give", True, name, npc.label, {f"{name}.owner": npc.name}, f"You give the {name} to {npc.label}.")
