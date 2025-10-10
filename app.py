from beeframe import *
from shiny.express import ui, render
import re


# tell the ui to try to fill the usable space
ui.page_opts(fillable=True)

# define a sidebar where new hives can be created
with ui.sidebar(open="closed", bg="#f8f8f8"):  
    ui.input_action_button("create_hive", "Create New Hive")

hive_id = "test hive 1"


# define our main page to be composed on tabs
with ui.navset_pill(id="tab"):

    with ui.nav_panel("Active"):

        with ui.accordion():


            with ui.accordion_panel("Hive 1"):
 

                # create two cards for the notes and actions relevant to the hive
                with ui.layout_columns():  
                    with ui.card(): 
                        # render the notes for this particular object
                        @render.data_frame
                        def _():
                            return render.DataGrid()

                    with ui.card():
                        ui.input_action_button(
                            re.sub(" ", "_", hive_id) + "_retire",
                            "Retire or Unretire"
                        )
            
                with ui.accordion():

                    with ui.accordion_panel("Box 1"):
                        # create two cards for the notes and actions relevant to the hive
                        with ui.layout_columns():  
                            with ui.card(): 
                                "Notes"

                            with ui.card():
                                "Actions"
                    
                        with ui.accordion():

                            with ui.accordion_panel("Frame 1"):
                                # create two cards for the notes and actions relevant to the hive
                                with ui.layout_columns():  
                                    with ui.card(): 
                                        "Notes"

                                    with ui.card():
                                        "Actions"
                        

    
    # define the tab where all retired hives are contained
    with ui.nav_panel("Retired"):
        "Where Retired hives go"

    
