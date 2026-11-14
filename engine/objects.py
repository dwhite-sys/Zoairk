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

#--------------------------------------------------------------------------------------------------------------
#     Template initializations
#--------------------------------------------------------------------------------------------------------------

#---------------------------------------------------
#     Flammability related stuff
#---------------------------------------------------


def init_flammable(instance): # An example of what the templates actually make happen.
    "Sets up all the needed attributes of a flammable object."
    instance.attributes.append(flammable)
    instance.states.on_fire = False

def init_igniter(instance):
    "Sets up all the needed attributes of an igniter object."
    instance.attributes.append(igniter)
    instance.states.on_fire = False

#---------------------------------------------------
#     Open state related stuff
#---------------------------------------------------

def init_openable(instance):
    "Sets up all the needed attributes of an igniter object."
    instance.attributes.append(openable)
    instance.states.open = False

#---------------------------------------------------
#     Broken state related stuff
#---------------------------------------------------

def init_breakable(instance):
    "Sets up all the needed attributes of a breakable object."
    # Ensure fragile or anything else hasn't made breakable first
    if breakable not in instance.attributes:
        instance.attributes.append(breakable)
    instance.states.broken = False

def init_fragile(instance):
    "Sets up all the needed attributes of a fragile object."
    # Ensure broken is present if broken is nown't added
    if breakable not in instance.attributes:
        instance.attributes.append(breakable)
        instance.states.broken = False
    instance.attributes.append(fragile)

def init_throwable(instance):
    "Sets up all the needed attributes of a throwable object."
    instance.attributes.append(throwable)

#---------------------------------------------------
#     Readability related stuff
#---------------------------------------------------

def init_readable(instance):
    "Sets up all the needed attributes of a readable object."
    instance.attributes.append(readable)
    instance.text = "This object is not readable."

#---------------------------------------------------
#     List for the template parser
#---------------------------------------------------

Templates = {
    'flammable':init_flammable,
    'igniter':init_igniter,
    'breakable':init_breakable,
    'fragile':init_fragile,
    'throwable':init_throwable,
    'openable':init_openable,
    'readable':init_readable,
}

#--------------------------------------------------------------------------------------------------------------
#     Dataclasses
#--------------------------------------------------------------------------------------------------------------

# Properties (universal across all objects, not meant to be appended to)
@dataclass
class Properties:
    name:str="Name"
    description:str="Description"
    weight:float=5
    worth:float=0
    parent=None

# Baseline states
@dataclass
class States:
    visible:bool=True

# Baseline interactions (custom ones currently not supported)
# 100% vestigial, but might be useful later. 
# Finally adding the ROBLOX style .parent attribute (or property) will make this kind of thing easy(er). It likely wouldn't be vestigial anymore.

def examine():
    pass

@dataclass
class Interactions:
    examine = examine

#--------------------------------------------------------------------------------------------------------------
#     Object Class
#--------------------------------------------------------------------------------------------------------------

# Onto objects and interaction logic.
class GameObject:
    """
    A class to represent a game object with various properties, attributes, templates, states, and interactions.

    Attributes:
        properties (Properties): The properties of the game object. Defaults to a new Properties instance.
        attributes (list): The attributes of the game object. Defaults to an empty list.
        interactions (Interactions): The interactions of the game object. Defaults to a new Interactions instance.
        states (States): The states of the game object. Defaults to a new States instance.

    Args:
        name (str): The name of the game object.
        properties (Properties, optional): A dictionary of properties for the game object. Defaults to None.
        attributes (list, optional): A list of attributes for the game object. Defaults to None.
        templates (list, optional): A list of templates to apply to the game object. Defaults to None.
        states (States, optional): The states of the game object. Defaults to None.
        interactions (Interactions, optional): The interactions of the game object. Defaults to None. 
    """
    def __init__(self, name, properties:Properties=None, attributes:list=None, templates:list=None, states:States=None, interactions:Interactions=None, ):
        self.properties = properties if properties else Properties(name) if name else Properties()
        self.attributes = attributes if attributes else []
        self.interactions = interactions if interactions else Interactions()
        self.states = states if states else States()
        if templates:
            for template in templates:
                if template.lower() in Templates:
                    Templates[template.lower()](self)

#--------------------------------------------------------------------------------------------------------------
#     Container Class
#--------------------------------------------------------------------------------------------------------------
# Made container its own class because it allows intellesense to pick up on its attributes and methods.

# | The point of the variable below is so the IDE doesn't complain or refuse to run the code,
# v since technically it's not defined otherwise.                     
GameContainer = GameObject

class GameContainer(GameObject):
    """
    A class representing a container in the game which can hold other game objects. Inherits from GameObject.

    Attributes:
        name (str): The name of the game container.
        properties (Properties, optional): The properties of the game container. Defaults to None.
        attributes (list, optional): The attributes of the game container. Defaults to None.
        templates (list, optional): The templates associated with the game container. Defaults to None.
        states (States, optional): The states of the game container. Defaults to None.
        interactions (Interactions, optional): The interactions available for the game container. Defaults to None.
        contents (list): A list to hold the contents of the game container.

    Methods:
        __init__(name, properties=None, attributes=None, templates=None, states=None, interactions=None):
            Initializes a new instance of the GameContainer class.
    """
    def __init__(self, name, properties:Properties=None, attributes:list=None, templates:list=None, states:States=None, interactions:Interactions=None, contents:list=[]):
        templates.append(openable)
        super().__init__(name, properties, attributes, templates, states, interactions)
        self.contents = []
        self.attributes.append(openable)
        for object in contents:
            if object.__class__ == GameObject or object.__class__ == GameContainer:
                self.contents.append(object)
                object.properties.parent = self

    def add(self, object:GameObject|GameContainer):
        "Adds an object to the container."
        self.contents.append(object)
        object.properties.parent = self


#--------------------------------------------------------------------------------------------------------------
#     End of
#--------------------------------------------------------------------------------------------------------------