#--------------------------------------------------------------------------------------------------------------
#    Dependencies
#--------------------------------------------------------------------------------------------------------------

import sys
import time

#--------------------------------------------------------------------------------------------------------------
#    Functions
#--------------------------------------------------------------------------------------------------------------

def wait(duration=0.1):
    "Waits a specified time."
    time.sleep(duration)

def clear():
    "Clears the console."
    print("\033[H\033[J", flush=False)

def hide_cursor():
    "Hides the console cursor."
    sys.stdout.write("\033[?25l")

def show_cursor():
    "Unhides the console cursor."
    sys.stdout.write("\033[?25h")

#--------------------------------------------------------------------------------------------------------------
#     Semi-useless string-variable converter
#--------------------------------------------------------------------------------------------------------------

#? these just make it and .1% easier and faster to use templates because you don't need to use quotes... yay! micro laziness!
flammable = 'flammable'
igniter = 'igniter'
breakable = 'breakable'
fragile = 'fragile'
breaker = 'breaker'
throwable = 'throwable'
openable = 'openable'
readable = 'readable'

# Joke is, this will probably get annoying to use once the list gets long.
# Oh well, fun for now. 

#--------------------------------------------------------------------------------------------------------------
#    End of
#--------------------------------------------------------------------------------------------------------------