#--------------------------------------------------------------------------------------------------------------
#     Imports
#--------------------------------------------------------------------------------------------------------------

#---------------------------------------------------
#     External
#---------------------------------------------------

from dataclasses import dataclass

#---------------------------------------------------
#     Local
#---------------------------------------------------

from .simplify import *
from .objects import *
from .types import Event

#--------------------------------------------------------------------------------------------------------------
#     Interactions
#--------------------------------------------------------------------------------------------------------------

#-----------------------------------------------------------------------
#     Event helpers (C2: handlers return an Event instead of printing)
#-----------------------------------------------------------------------

def _name(entry):
    return entry.object.properties.name if entry else None

def _event(action_set, action, ok, message, changed=None):
    return Event(action=action, ok=ok, target=_name(action_set.target),
                 instrument=_name(action_set.instrument), changed=changed or {}, message=message)

def _fail(action_set, action, message="nothing happens"):
    return _event(action_set, action, False, message)

def _not_visible(action_set, action):
    return _fail(action_set, action, f"You can't see {_name(action_set.target)} here.")

#-----------------------------------------------------------------------
#     Flammability related stuff
#-----------------------------------------------------------------------

def ignite(action_set):
    """
    Ignites the target. With no instrument the target must be an 'igniter' (a match strikes itself).
    With an instrument, the target must be 'flammable' and the instrument an igniter/flammable that is on fire.
    """
    a = 'ignite'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object; tname = target.properties.name
    if not action_set.instrument:
        if igniter in target.attributes:
            if target.states.on_fire == False:
                target.states.on_fire = True
                return _event(action_set, a, True, f"{tname} was successfully ignited. {tname} is now on fire.",
                              {f"{tname}.on_fire": True})
            return _event(action_set, a, True, f"{tname} was already ignited.")
        return _fail(action_set, a, f"{tname} can't be lit on its own.")
    instrument = action_set.instrument.object; iname = instrument.properties.name
    if flammable not in target.attributes and igniter not in target.attributes:
        return _fail(action_set, a, f"{tname} won't burn.")
    if igniter not in instrument.attributes and flammable not in instrument.attributes:
        return _fail(action_set, a, f"{iname} can't light anything.")
    if target.states.on_fire == True:
        return _event(action_set, a, True, f"{tname} was already on fire.")
    if getattr(instrument.states, 'on_fire', False) != True:
        return _fail(action_set, a, f"{tname} could not be ignited; {iname} is not burning.")
    target.states.on_fire = True
    return _event(action_set, a, True,
                  f"{tname} was successfully ignited by {iname}. {tname} is now on fire.",
                  {f"{tname}.on_fire": True})

def extinguish(action_set):
    "Puts out a target that is on fire."
    a = 'extinguish'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object; tname = target.properties.name
    if (flammable in target.attributes or igniter in target.attributes) and target.states.on_fire == True:
        target.states.on_fire = False
        return _event(action_set, a, True, f"{tname} was successfully extinguished.", {f"{tname}.on_fire": False})
    return _fail(action_set, a, f"{tname} is not on fire.")

#-----------------------------------------------------------------------
#     Open state related stuff
#-----------------------------------------------------------------------

def _set_open(action_set, a, value):
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object; tname = target.properties.name
    word = 'open' if value else 'closed'
    if openable not in target.attributes:
        return _fail(action_set, a, f"{tname} can't be {'opened' if value else 'closed'}.")
    if target.states.open == value:
        return _event(action_set, a, True, f"{tname} was already {word}.")
    target.states.open = value
    return _event(action_set, a, True, f"{tname} is now {word}.", {f"{tname}.open": value})

def open(action_set):
    return _set_open(action_set, 'open', True)

def close(action_set):
    return _set_open(action_set, 'close', False)

#-----------------------------------------------------------------------
#     Reading related stuff
#-----------------------------------------------------------------------

def read(action_set):
    a = 'read'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object; tname = target.properties.name
    if readable in target.attributes:
        return _event(action_set, a, True, f"You look at {tname}. It says:\n{target.text}")
    return _fail(action_set, a, f"There is nothing written on {tname}.")

#-----------------------------------------------------------------------
#     Broken state related stuff
#-----------------------------------------------------------------------

def _break(action_set, a, target, message):
    tname = target.properties.name
    if target.states.broken == True:
        return _event(action_set, a, True, f"{tname} was already broken.")
    target.states.broken = True
    return _event(action_set, a, True, message, {f"{tname}.broken": True})

def break_object(action_set):
    """
    Breaks the target. Without an instrument it must be 'fragile'. With an instrument the target must be
    'breakable' and the instrument a 'breaker', or the instrument throwable/heavy enough to smash a fragile target.
    """
    a = 'break_object'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object; tname = target.properties.name
    if not action_set.instrument:
        if fragile in target.attributes:
            return _break(action_set, a, target, f"{tname} is now broken.")
        return _fail(action_set, a, f"Could not break {tname}.")
    instrument = action_set.instrument.object; iname = instrument.properties.name
    if breakable in target.attributes and (breaker in instrument.attributes
                                           or (fragile in target.attributes and throwable in instrument.attributes)):
        return _break(action_set, a, target, f"{tname} was successfully broken using {iname}.")
    return _fail(action_set, a, f"Could not break {tname} with {iname}.")

def throw(action_set):
    """
    Throws one object at another. The parser may put the thrown thing in either slot
    ("throw rock at window" -> target=rock, instrument=window in the legacy SRL), so pick the throwable one.
    """
    a = 'throw'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    t = action_set.target.object
    i = action_set.instrument.object if action_set.instrument else None
    if i is None:
        if throwable in t.attributes:
            return _event(action_set, a, True, f"{t.properties.name} was thrown. It lands nearby.")
        return _fail(action_set, a, f"{t.properties.name} can't be thrown.")
    if throwable in t.attributes and throwable not in i.attributes:
        thrown, hit = t, i
    elif throwable in i.attributes:
        thrown, hit = i, t
    else:
        return _fail(action_set, a, f"{t.properties.name} can't be thrown.")
    hname = hit.properties.name; tname = thrown.properties.name
    if breakable in hit.attributes:
        if hit.states.broken == True:
            return _event(action_set, a, True, f"{tname} was thrown at {hname}, but it was already broken.")
        hit.states.broken = True
        return _event(action_set, a, True, f"{tname} was thrown at {hname}. {hname} is now broken.",
                      {f"{hname}.broken": True})
    return _event(action_set, a, True, f"{tname} was thrown at {hname}. It bounces off.")

#-----------------------------------------------------------------------
#     Examine
#-----------------------------------------------------------------------

def examine(action_set):
    a = 'examine'
    if not action_set.target:
        return _fail(action_set, a)
    if not check_visibility(action_set):
        return _not_visible(action_set, a)
    target = action_set.target.object
    lines = [f"{target.properties.name}", f"Description: {target.properties.description}", "States:"]
    lines += [f" - {k.title()}: {v}" for k, v in vars(target.states).items()]
    return _event(action_set, a, True, "\n".join(lines))

#-----------------------------------------------------------------------
#     Check visibility
#-----------------------------------------------------------------------

def check_visibility(action_set):
    if action_set.target:
        target = action_set.target.object
        if target.states.visible == False:
            return False
        parent = target.properties.parent
        if parent is not None and openable in getattr(parent, 'attributes', []):
            if getattr(parent.states, 'open', True) == False:
                return False
    return True

#--------------------------------------------------------------------------------------------------------------
#     Interaction Reference List
#--------------------------------------------------------------------------------------------------------------

INTERACTIONS = {
    'ignite':ignite,
    'extinguish':extinguish,
    'open':open,
    'close':close,
    'read':read,
    'break_object':break_object,
    'throw':throw,
    'examine':examine,
}

interaction_list = {**INTERACTIONS, 'break':break_object}  # legacy name

def run(action_sets):
    "Runs each ActionSet in order and returns one Event per action. Unknown actions do nothing."
    events = []
    for action_set in action_sets:
        handler = INTERACTIONS.get(action_set.action)
        if handler is None:
            events.append(_fail(action_set, action_set.action, "nothing happens"))
        else:
            events.append(handler(action_set))
    return events

#--------------------------------------------------------------------------------------------------------------
#     End of
#--------------------------------------------------------------------------------------------------------------
