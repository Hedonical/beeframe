from beeframe import *
from shiny.express import ui, render, input
from shiny import reactive
from typing import Literal
import re

# """
# Global Variables
# """


# create a placeholder to store the blob service client
blob_client = None

# create a global variable to store the bee related data
hives = {}
boxes = {}
frames = {}
notes = pl.DataFrame()


# """
# Non-Shiny App Helper Functions
# """

def load_dict(choice: Literal["hives", "boxes", "frames"]) -> None:
    # given a dictionary and path, load the global hives, boxes, or frames
    global blob_client
    global hives
    global boxes
    global frames

    # initiate the proper global variable
    if choice == "hives":

        df = load_blob(blob_client, "cemetery", "hives.parquet")

        # find the IDs
        IDs = df.unique("hive ID")["hive ID"].to_list()

        for h in IDs:
            temp_hive = hive(h)

            temp_hive.load(df)

            hives[h] = temp_hive
    elif choice == "boxes":

        df = load_blob(blob_client, "cemetery", "boxes.parquet")

        # find the IDs
        IDs = df.unique("box ID")["box ID"].to_list()

        for b in IDs:
            temp_box = box(b)

            temp_box.load(df, hives)

            boxes[b] = temp_box
    elif choice == "frames":

        df = load_blob(blob_client, "cemetery", "frames.parquet")

        # find the IDs
        IDs = df.unique("frame ID")["frame ID"].to_list()

        for f in IDs:
            temp_frame = frame(f)

            temp_frame.load(df, boxes)

            frames[f] = temp_frame





# """
# Main Page Setup
# """

# tell the ui to try to fill the usable space
ui.page_opts(fillable=True)

# define a sidebar where new hives can be created
with ui.sidebar(open="closed", bg="#f8f8f8"):  
    ui.input_action_button("create_hive", "Create New Hive")

# """
# Azure connection code
# """

with ui.div(id="connection_str_submit_holder"):
    with ui.card():
        ui.input_action_button("connection_str_submit",
                           "Submit"),
        ui.input_text_area("connection_str",
                  "",
                  width="100%",
                   placeholder="Please Provide an Azure Connection String")


# """
# Main UI code
# """

def make_card(title, text):
    # Build a fragment containing one card
    frag = ui.div()
    with frag:
        with ui.card():
            ui.card_header(title)
            ui.p(text)
    return frag

with ui.accordion(id="Hives"):
    pass

ui.insert_accordion_panel(
    "Hives",
    "test hive",
    make_card("test hive", "example test")
)


# """
# Reactive Actions
# """

@reactive.effect
@reactive.event(input.connection_str_submit)
def connect():
    # initiate the global variable to store 
    # the credentials at
    global blob_client

    # gather the value from the connection_str text box
    connection_str = input.connection_str().strip()


    # attempt to establish the connection,
    # if it errors than it means it is an invalid connection str
    try:
        # attempt to establish the connection
        blob_client = establish_connection(connection_str)

        # remove the connection ui
        ui.remove_ui("#connection_str_submit_holder")

        # create a temporary message to stop further action
        m = ui.modal(  
        "Connected! Loading data 🐝",  
        easy_close=False,  
        footer=None,  
        )  

        ui.modal_show(m)

        load_dict("hives")
        load_dict("boxes")
        load_dict("frames")

        ui.modal_remove()

    except:
        # if it fails, do not remove the ui
        # create a message notifying the user
        m = ui.modal(  
        "Connection Failed. Please check your internet connection or your entered string",  
        easy_close=True,  
        footer=None,  
        )  

        ui.modal_show(m)

@reactive.effect
@reactive.event(input.create_hive)
def create_hive():
    # load the global variable
    global blob_client
    global hives
    global boxes
    global frames

    # creates a new hive if the user is logged in, otherwise
    # returns an error message

    if blob_client is None:
        m = ui.modal(  
        "Please connect to the persistent storage first.",  
        easy_close=True,  
        footer=None,  
        )  

        ui.modal_show(m)
    else:
        # if the connection has been established
        # make a new hive

        # request the parameters from the user
        # to make a hive class
        m = ui.modal(  
        ui.input_text("new_hive_owner", "Owner:"),
        ui.input_text("new_hive_ID", "ID:", placeholder="Leave Blank if you want Auto-Generated"),
        ui.input_numeric("new_hive_position", "Position:", 1, min=1, step=1),
        ui.input_action_button("new_hive_submit", "Submit"),
        ui.input_action_button("new_hive_cancel", "Cancel"),
        title="New Hive Parameters",  
        easy_close=False,  
        footer=None,  
        )  
        ui.modal_show(m)

@reactive.effect
@reactive.event(input.new_hive_cancel)
def process_cancel_hive():
    # remove the popup
    ui.modal_remove() 

    

@reactive.effect
@reactive.event(input.new_hive_submit)
def process_create_hive():


    # process the create new hive pop up
    
    # if owner is an empty string, do nothing
    if input.new_hive_owner().strip() == "":
        # create a dissapearing message
        ui.notification_show("Owner cannot be empty, please enter", duration=5)
    else:
        # otherwise proceed

        

        # combine the keys of all of the IDs
        IDs = list(hives.keys()) + list(boxes.keys()) + list(frames.keys())

        if input.new_hive_ID().strip() == "":
            # if the string is empty, produce a new name
            name = names.get_full_name()

            # keep on retrying if the name already exists
            while name in IDs:
                name = names.get_full_name()
        else:
            name = input.new_hive_ID().strip()

        # if the string is an exist ID, alert the user
        if name in IDs:
            ui.notification_show("ID already exists, please change", duration=5)

        else:
            
            # otherwise proceed in making the class
            hives[name] = hive(
                ID=name,
                owner=input.new_hive_owner().strip(),
                retired=False,
                position=input.new_hive_position()
            )

            # remove the popup
            ui.modal_remove() 