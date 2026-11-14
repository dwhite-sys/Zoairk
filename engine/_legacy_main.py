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

from interactions import *
from objects import *
from simplify import *
from ailess_srl import *

#-----------------------------------------------
#! Use the docs below this point your own risk. 
#-----------------------------------------------

#* They were written by Copilot, and I didn't do a check over to make sure they're accurate.
#* It seems to largely know what it's talking about, but I don't have enough experience with it to know if if it's fully reliable.
#* I don't typically write docs to begin with anyway (bad habit), so it's better than nothing.

#* I did, however, write all the comments and the code. You can tell because it's like 75% half coherent ramblings an AI wouldn't do.

#--------------------------------------------------------------------------------------------------------------
#     Setting related stuff
#--------------------------------------------------------------------------------------------------------------

#---------------------------------------------------
#     ObjectContainer class
#---------------------------------------------------

# An ObjectContainer is a list of objects that can be interacted with.
# It has embedded functions to find, add, move, and remove objects.
# This keeps things easy.

class ObjectContainer:
    def __init__(self, objects:list=[]):
        self.contents = objects
        for object in self.contents:
            if object.__class__ == GameObject or object.__class__ == GameContainer:
                object.properties.parent = self

    def find_object(self, obj):
        find = self.contents.index(obj)
        if find:
            if find.__class__ == GameObject or find.__class__ == GameContainer:
                return find
        return False
    
    def add_object(self, obj):
        if obj.__class__ == GameObject or obj.__class__ == GameContainer:
            self.contents.append(obj)
            obj.properties.parent = self

    def move_to(self, obj, new_parent):
        if obj.__class__ == GameObject or obj.__class__ == GameContainer:
            self.contents.pop(obj.properties.name)
            new_parent.objects.append(obj)
            obj.properties.parent = new_parent

    def remove_object(self, obj):
        if obj.__class__ == GameObject or obj.__class__ == GameContainer:
            self.contents.pop(obj.properties.name)

#---------------------------------------------------
#     SettingEvent
#---------------------------------------------------

# A SettingEvent is a pair of functions - a check function, and a function be be executed.
# Optionally, it has an internal state that can be checked and updated by the functions.

class SetttingEvent:
    """
    A class to represent a setting event in a state machine.
    Attributes:
    -----------
    name : str
        The name of the event. Why does it need one? It helps keep track when being initialized in a setting.
    function : callable
        The function to be executed when the event is triggered.
    check_function : callable
        The function to check if the event should be triggered.
    state : bool, optional
        The state of the event, default is False.
    parent : object, optional
        The parent object of the event, default is None.
    Methods:
    --------
    refresh():
        Checks the condition using check_function and executes the function if the condition is met.
    """
    def __init__(self, name:str, function, check_function, state=False):
        # State can be anything, it's updated by the function and checked by both functions.
        self.name = name
        self.function = function
        self.check = check_function
        self.state = state
        self.parent = None

    def refresh(self):
        if self.check(self, self.parent):
            self.function(self, self.parent)

#---------------------------------------------------
#     The actual setting
#---------------------------------------------------

# The setting is the room or area the player is in.
# It has a name, description, objects, and events. The object list is a list of GameObjects and GameContainers.
# The events are a list of SettingEvents, which are pairs of checking/execution functions.

class Setting(ObjectContainer):
    """
    A class to represent a setting in the game, which contains objects and events.
    Attributes:
    -----------
    name : str
        The name of the setting (default is "Room").
    description : str
        A brief description of the setting (default is "Description").
    objects : list
        A list of objects contained in the setting.
    room_events : list[SettingEvent]
        A list of events associated with the setting.
    current_states : dict
        A dictionary to store the current states of the objects in the setting.
    events : dict
        A dictionary to store the events by their names.
    Methods:
    --------
    refresh_events():
        Refreshes the events in the setting if any object's state has changed.
    """
    def __init__(self, name:str="Room", description:str="Description", objects:list=[], room_events:list[SetttingEvent]=[]):
        super().__init__(objects)
        self.name = name
        self.current_states = {}
        for object in objects:
            if object.__class__ == GameObject or object.__class__ == GameContainer:
                self.current_states[object.properties.name] = object.states.__dict__

        self.description = description
        self.room_events = room_events
        self.events = {}
        for event in room_events:
            self.events[event.name] = event
            event.parent = self
            
    def refresh_events(self):
        any_changed = False
        for object in self.contents:
            if self.current_states[object.properties.name] != object.states:
                any_changed = True
            else:
                print(f"{self.current_states[object.properties.name]} and {object.states} are the same.")
        if any_changed:
            for event in self.room_events:
                event.refresh()

#---------------------------------------------------
#     Setting functions
#---------------------------------------------------

def check_mailbox(self, parent):
    if 'mailbox' in [object.properties.name.lower() for object in parent.contents]:
        index = [object.properties.name.lower() for object in parent.contents].index('mailbox')
        if parent.contents[index].states.open and self.state == False:
            self.state = True
            return True

def celebrate_opening_mailbox(self, parent):
    print("Yay! You opened the mailbox!")
    wait()
    print('.', end='', flush=True)
    wait()
    print('.', end='', flush=True)
    wait()
    print('.')
    wait(0.25)
    print("Setting function over.")

#---------------------------------------------------
#     Setting initialization
#---------------------------------------------------

start_area = Setting(
    name = "Start Area", 
    description = "A lawn type deal.", 
    objects = [
        GameObject("Stick", templates=[flammable, fragile]),
        GameObject("Match", templates=[igniter]),
        GameObject("Rock", templates=[throwable]),
        GameObject("Window", templates=[breakable]),
        GameContainer("Mailbox", templates=[flammable, breakable], contents=[
            GameObject("Note", templates=[readable]),
        ]),
    ], 
    room_events = [
        SetttingEvent("Reaction to mailbox being opened", celebrate_opening_mailbox, check_mailbox),
    ]
)


# Lua ruined me. I occasionally forget indexes start at 0 in like, literally everything else.
# Not that it makes sense to start at 0, but it's standard, I guess.
start_area.contents[4].contents[0].text = "This is a note. Insert useful informational text here."

# Change the text of the function and the text to something not ominous. 
# This works for now, but still.

#---------------------------------------------------
#     Setting the current area
#---------------------------------------------------

current_area = start_area

#---------------------------------------------------
#     Get Visibility
#---------------------------------------------------

def get_visible(objects:list[GameObject|GameContainer]):
    object_list = []
    for object in objects:
        if object.__class__ == GameObject:
            if object.states.visible == True:
                object_list.append(object)
        elif object.__class__ == GameContainer:
            if object.states.visible == True:
                object_list.append(object)
                if 'openable' in object.attributes:
                    if object.states.open == True:
                        children = get_visible(object.contents)
                        for child in children:
                            object_list.append(child)
                else:
                    children = get_visible(object.contents)
                    for child in children:
                        object_list.append(child)
    
    return object_list

#--------------------------------------------------------------------------------------------------------------
#     Main loop
#--------------------------------------------------------------------------------------------------------------

while True:
    user_input = input("> ")
    if user_input != "exit":
        #TODO Change this to printed_any and make a check for it under interactions. 
        passed_any = process_srl(user_input, get_visible(start_area.contents), interaction_list)
        if passed_any:
            print()
    start_area.refresh_events()

# Test 
#--------------------------------------------------------------------------------------------------------------
#    End of
#--------------------------------------------------------------------------------------------------------------