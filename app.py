from beeframe import *
from shiny.express import ui, render, input
from shiny.ui import page_navbar
from shiny import reactive
from typing import Literal
import re

# """
# Global Variables
# """


# create a placeholder to store the blob service client
blob_client = None

# create a global variable to store the bee related data
hives = dict[str, hive]
hives = hives()
boxes = dict[str, box]
boxes = boxes()
frames = dict[str, frame]
frames = frames()
notes = pl.DataFrame()
measurements = pl.DataFrame()

# """
# Reactive Values
# """

# create reactive value to track when a new hive has been added
hive_added = reactive.value(False)

# create a reactive value to track when the hives had been updated
hives_selection_updated = reactive.value(True)




# """
# Non-Shiny App Helper Functions
# """

def populate_note(ob: hive | box | frame) -> None:
    # Populates the notes of the hive, box, or frame
    global notes

    ob.load_notes(notes)

def populate_measurement(ob: frame) -> None:
    # populate the frame measurements
    global measurements

    ob.load_measurements(measurements)

def load_dfs(choice: Literal["notes", "measurements", "all"]) -> None:
    # given a choice, load the notes or measurements
    global blob_client
    global notes
    global measurements
    global hives
    global boxes
    global frames

    if choice == "notes":
        notes = load_blob(blob_client, "cemetery", "notes.parquet")
        # populate the notes of the dicts
        [h.load_notes(notes) for h in hives.values()]
        [b.load_notes(notes) for b in boxes.values()]
        [f.load_notes(notes) for f in frames.values()]
    elif choice == "measurements":
        measurements = load_blob(blob_client, "cemetery", "measurements.parquet")

        # populate the measurements
        [f.load_measurements(measurements) for f in frames.values()]
    elif choice == "all":
        notes = load_blob(blob_client, "cemetery", "notes.parquet")

        # populate the notes of the dicts
        [h.load_notes(notes) for h in hives.values()]
        [b.load_notes(notes) for b in boxes.values()]
        [f.load_notes(notes) for f in frames.values()]

        measurements = load_blob(blob_client, "cemetery", "measurements.parquet")

        # populate the measurements
        [f.load_measurements(measurements) for f in frames.values()]

def load_dict(choice: Literal["hives", "boxes", "frames", "all"], name:str = None) -> None:
    # given a dictionary and path, load the global hives, boxes, or frames
    global blob_client
    global hives
    global boxes
    global frames

    # if the user provides a name, load only that specific hive, box, or frame

    if choice == "hives":
        # load the cloud parquet
        df = load_blob(blob_client, "cemetery", "hives.parquet")

        # find the IDs if the name is none
        if name is None:
            IDs = df.unique("hive ID")["hive ID"].to_list()
        else:
            IDs = [name]

        for h in IDs:
            temp_hive = hive(h)

            temp_hive.load(df)

            hives[h] = temp_hive
    elif choice == "boxes":

        df = load_blob(blob_client, "cemetery", "boxes.parquet")

        # find the IDs
        if name is None:
            IDs = df.unique("box ID")["box ID"].to_list()
        else:
            IDs = [name]

        for b in IDs:
            temp_box = box(b)

            temp_box.load(df, hives)

            boxes[b] = temp_box
    elif choice == "frames":

        df = load_blob(blob_client, "cemetery", "frames.parquet")

        # find the IDs
        if name is None:
            IDs = df.unique("frame ID")["frame ID"].to_list()
        else:
            IDs = [name]

        for f in IDs:
            temp_frame = frame(f)

            temp_frame.load(df, boxes)

            frames[f] = temp_frame
    elif choice == "all":
        df = load_blob(blob_client, "cemetery", "hives.parquet")

        # find the IDs, in this we will always want to load everything
        IDs = df.unique("hive ID")["hive ID"].to_list()

        for h in IDs:
            temp_hive = hive(h)

            temp_hive.load(df)

            hives[h] = temp_hive
        
        df = load_blob(blob_client, "cemetery", "boxes.parquet")

        # find the IDs
        IDs = df.unique("box ID")["box ID"].to_list()

        for b in IDs:
            temp_box = box(b)

            temp_box.load(df, hives)

            boxes[b] = temp_box
        
        df = load_blob(blob_client, "cemetery", "frames.parquet")

        # find the IDs
        IDs = df.unique("frame ID")["frame ID"].to_list()

        for f in IDs:
            temp_frame = frame(f)

            temp_frame.load(df, boxes)

            frames[f] = temp_frame

def push_dict(choice: Literal["hives", "boxes", "frames", "all"], name:str = None) -> None:
    # given a specific hive, box, or frame
    # push the latest version of it with its notes and measurements
    # if the name is provided, only push the speicic hive, frame, or box

    global blob_client
    global hives

    if choice == "hives":
        # if the user choose the hive
        # load the hives df and notes df

        df = load_blob(blob_client, "cemetery", "hives.parquet")

        # find the IDs if the name is none
        if name is None:
            IDs = list(hives.keys())
        else:
            IDs = [name]

        # define a list to store all of the hives
        h_dfs = []
        
        # loop through each ID and retrieve the parquet representation
        for h in IDs:
            h_dfs.append(hives[h].save())

        # concat the dataframes
        h_dfs = pl.concat(h_dfs)

        # join with the azure blob
        h_dfs = pl.concat([h_dfs, df])

        h_dfs = h_dfs.filter( # choose the latest data entries, for every unique value pair
                                           pl.col("timestamp").eq(pl.col("timestamp").max(
                                           ).over([col for col in h_dfs.columns if col != "timestamp"])
                                           )
                                       ).unique()
        
        # push the latest data
        write_blob(blob_client, "cemetery", "hives.parquet", h_dfs)

            


# TODO: define functions that will push and pull from the cloud
# TODO: Figure out how to represent retired/deleted data

# """
# Main Page Setup
# """

# tell the ui to try to fill the usable space
ui.page_opts(fillable=True)

# define a sidebar where new hives can be created
with ui.sidebar(open="closed", bg="#f8f8f8"):  

    # have a button for whether to show the retired hives
    ui.input_switch("switch_retired", "Retired Hives", False)  

    # create the selection options
    ui.input_select("select_hive", "Select a Hive", [])
    ui.input_select("select_box", "Select a Box", [])
    ui.input_select("select_frame", "Select a Frame", [])

    # Create the universal action buttons
    ui.input_action_button("create_hive", "Create New Hive")
    ui.input_action_button("create_box", "Create New Box")
    ui.input_action_button("create_frame", "Create New Frame")

# """
# Azure connection code
# """

# At the start of the runtime, prompt the user to provide a valid connection string to Azure
m = ui.modal(  
        ui.input_text_area("connection_str",
                  "",
                  width="100%",
                   placeholder="Please Provide an Azure Connection String"),
        ui.div(
        ui.input_action_button("connection_str_submit",
                           "Submit"), style="text-align: center;"
    ),
    easy_close=False,  
    footer=None,  
    )  

ui.modal_show(m)



# """
# Tabs UI
# """

with ui.navset_tab(id="tabs"):
    # define the hive UI that changes to match the hive the user has selected
    with ui.nav_panel("Hive"):
        with ui.card():
            ui.card_header("Parameters")

            # reactively populate with the current hive's notes
            @render.data_frame
            def hive_param_df():
                global hives

                # if the hive exists, return its notes
                if input["select_hive"]() in list(hives.keys()):
                    return render.DataGrid(hives[input["select_hive"]()].save().drop("timestamp"))


        with ui.card():
            ui.card_header("Notes")

            # reactively populate with the current hive's notes
            @render.data_frame
            def hive_note_df():
                global hives

                # if the hive exists, return its notes
                if input["select_hive"]() in list(hives.keys()):
                    if hives[input["select_hive"]()].notes is not None:
                        return render.DataGrid(hives[input["select_hive"]()].notes, filters=True)
                    else:
                        return render.DataGrid(pl.DataFrame({"No Notes": "No notes have been created"}))

        with ui.card():
            ui.card_header("Actions")

            ui.input_action_button("hive_create_note", "Create Note")
            ui.input_action_button("hive_change_position", "Change Position")
            ui.input_action_button("hive_change_ID", "Change Name")
            ui.input_action_button("hive_retire", "Retire or Unretire")
            ui.input_action_button("hive_change_owner", "Change Owner")


    with ui.nav_panel("Box"):
        with ui.card():
            "Panel B content"

    with ui.nav_panel("Frame"):
        with ui.card():
            "Panel C content"
        





# """
# Reactive Actions
# """

# """
# Connection Functionality
# """

@reactive.effect
@reactive.event(input.connection_str_submit)
def connect():
    # initiate the global variable to store 
    # the credentials at
    global blob_client
    global notes
    global measurements
    global hives
    global boxes
    global frames

    
    # TODO: Reinstate
    # # gather the value from the connection_str text box
    # connection_str = input.connection_str().strip()


    # TODO REMOVE WHEN PUSHED
    connection_str = load_local_credential("blank.txt")


    # attempt to establish the connection
    blob_client = establish_connection(connection_str)

    

    # attempt to establish the connection,
    # if it errors than it means it is an invalid connection str
    try:
        # attempt to establish the connection
        blob_client = establish_connection(connection_str)

        # remove the connection ui
        ui.remove_ui("#connection_str_submit_holder")

        # create a temporary message to stop further action
        m = ui.modal(  
            ui.div(
        "Connected! Loading data 🐝", style="text-align: center;"
    ),  
        easy_close=False,  
        footer=None,  
        )  

        ui.modal_show(m)

        # load the data
        load_dict("all")
        load_dfs("all")

        # update the hive choices
        ui.update_select(
        "select_hive",
        choices=[h for h in list(hives.keys()) if not hives[h].retired],

        )

        # remove the connection ui
        ui.remove_ui("#connection_str_submit_holder")


        ui.modal_remove()

    except:
        ui.notification_show("Invalid connection string or no internet connection, please retry", duration=5)


# """
# Hive Functions
# """

@reactive.effect
@reactive.event(hive_added, input.switch_retired)
def update_hive_selection():
    # whenever the user adds a new hive
    # update the box choices
    global hives


    # if the input switch is switched on select only hives that have been retired
    if input.switch_retired():
        ui.update_select(
        "select_hive",
        choices=[h for h in list(hives.keys()) if hives[h].retired],

        )
    else:
        ui.update_select(
        "select_hive",
        choices=[h for h in list(hives.keys()) if not hives[h].retired],

        )
    
    # designate the reactive value indicating that the hives were done updating
    hives_selection_updated.set(not hives_selection_updated.get())

@reactive.effect
@reactive.event(input.hive_retire)
def retire_hive():
    # handle the user clicking the retire hive button 

    global hives

    status = hives[input.select_hive()].retired

    if status:
        change = "not retired"
    else:
        change = "retired"

    m = ui.modal(ui.div(
    ui.input_action_button("retire_hive_submit", "Confirm"),
    ui.input_action_button("retire_hive_cancel", "Cancel"), style="text-align: center;"
    ),
    title=ui.div(f"You are changing '{input.select_hive()}' to '{change}'", style="align: center;"
    ),  
    easy_close=False,  
    footer=None,  
    )

    ui.modal_show(m)

@reactive.effect
@reactive.event(input.retire_hive_submit)
def process_retire_hive():
    # if the user hits submit update the data
    global hives

    # update the dict value to its inverse
    hives[input.select_hive()].retired = not hives[input.select_hive()].retired

    # push the update
    push_dict("hives", input.select_hive())

    # update the hive selection
    hive_added.set(not hive_added.get())

    ui.modal_remove()

@reactive.effect
@reactive.event(input.retire_hive_cancel)
def process_retire_hive_cancel():
    ui.modal_remove()
    


@reactive.effect
@reactive.event(input.create_hive)
def create_hive():
    # load the global variable
    global blob_client
    global hives
    global boxes
    global frames

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
    title=ui.div("New Hive Parameters", style="text-align: center;"
    ),  
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
    global hives
    global boxes
    global frames


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

            # push the new data
            push_dict("hives", name)

            # indicate that the global variable has been updated
            hive_added.set(not hive_added.get())

            # remove the popup
            ui.modal_remove() 


# """
# Box Functions
# """

@reactive.effect
@reactive.event(input.select_hive, hives_selection_updated)
def update_box_selection():
    # whenever the user selects a new box select the new hive
    # update the box choices
    global boxes


    ui.update_select(
    "select_box",
    choices=[box for box in list(boxes.keys()) if boxes[box].hive.ID == input.select_hive()],

    )




