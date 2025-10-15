import polars as pl
from datetime import datetime
import pytz
import names
from typing import Optional, Literal
from azure.storage.blob import BlobServiceClient
from io import BytesIO
from pathlib import Path

"""
Define any global constants:
"""

# get the timezone of nyc
nyc = pytz.timezone("America/New_York")

# to start all data will go through the cemetery container
container = "cemetery"

"""
Define any global methods:
"""

def load_local_credential(path:str) -> str:
    """
    Given a link to a txt file, load the credentials stored there.

    Intended for development as deployment will require the user to provide
    the connection string
    """

    return Path(path).read_text()

def establish_connection(connection_str:str) -> BlobServiceClient:
    """
    Given an Azure connection string, establish a connection to Azure and return the 
    blob service client

    Inputs:
        connection_str [str]: string to a valid azure blob storage instance

    Returns:
        a blob service client instance that can be used to load files
    """

    return BlobServiceClient.from_connection_string(connection_str)

def load_blob(service_client: BlobServiceClient, container:str, path:str) -> pl.DataFrame:
    """
    Given an Azure blob service client, a container, and a path to a parquet file,
    load the corresponding polars dataframe.
    """

    # define the location to the blob
    blob_location = service_client.get_blob_client(
        container=container,
        blob=path
    )

    return pl.read_parquet(blob_location.download_blob().readall())

def write_blob(service_client: BlobServiceClient, container:str, path:str, dataframe: pl.DataFrame) -> None:
    """
    Given an Azure blob service client, a container, and a path to a parquet file,
    write a corresponding polars dataframe.
    """

    # define the location to the blob
    blob_location = service_client.get_blob_client(
        container=container,
        blob=path
    )

    # create a location in memory to write our parquet to 
    buffer = BytesIO()

    # write the dataframe to the buffer
    dataframe.write_parquet(buffer)

    # Seek the bytes, starting from the start of the buffer
    buffer.seek(0)

    parquet_bytes = buffer.getvalue()

    # upload the parquet bytes to the blob
    blob_location.upload_blob(parquet_bytes, overwrite = True)



class hive:
    """
    Pythonic representation of a hive

    Attributes:
        owner [str]: the name of the owner of the hive
        retired [bool]: whether or not the hive is retired
        ID [str]: unique identifier for the hive
        position [int]: left to right position of the hive
        notes [DataFrame]: polars dataframe of all of the notes that reference the hive

    """

    """
    Attributes:
    """
    def __init__(self, ID: str, owner: Optional[str] = None, retired: Optional[bool] = None,
                  position: Optional[int] = None, notes:Optional[pl.DataFrame] = None):
        
        self.owner = owner
        self.retired = retired
        self.ID = ID
        self.position = position
        self.notes = notes


    
    """
    Methods:
    """
    def save(self) -> pl.DataFrame:
        """
        Returns the hive as a polars dataframe
        """

        return pl.DataFrame(
            {
                "hive ID": self.ID,
                "retired": self.retired,
                "owner": self.owner,
                "position": self.position,
                "timestamp": datetime.now(nyc)

            },
            schema=
            {
                "hive ID": pl.String,
                "retired": pl.Boolean,
                "owner": pl.String,
                "position": pl.Int64,
                "timestamp": pl.Datetime

            }
        )
    
    def load(self, hive_dataframe: pl.DataFrame) -> None:
        """
        Given the overall hive dataframe, extract the latest parameters that match 
        the hive ID
        """

        # select the latest hive entry
        latest = hive_dataframe.filter(pl.col("hive ID").eq(self.ID)
                                       ).filter(
                                           pl.col("timestamp").eq(pl.col("timestamp").max())
                                       ).row(0, named=True)
        
        self.retired = latest["retired"]
        self.owner = latest["owner"]
        self.position = latest["position"]

    def create_note(self, nature: str, note: str) -> pl.DataFrame:
        """
        Given a nature and note, return a dataframe that also includes the ID and level
        """

        return pl.DataFrame(
            {
                "ID": self.ID,
                "level": "hive",
                "nature": nature,
                "note": note,
                "timestamp": datetime.now(nyc)
            },
            schema=
            {
                "ID": pl.String,
                "level":  pl.String,
                "nature": pl.String,
                "note":  pl.String,
                "timestamp": pl.Datetime

            }
        )
    
    def load_notes(self, notes: pl.DataFrame) -> None:
        """
        Given the overall notes dataframe, select the notes relevant to this hive.
        """

        self.notes = notes.filter(pl.col("ID").eq(self.ID))
    
    def retire(self) -> None:
        """
        Reverses the current retired status
        """

        self.retired = not self.retired
    
    def change_ID(self, ID: str, hive_dataframe: pl.DataFrame) -> None:
        """
        Given a new ID, change the current ID.

        This requires the overall hive dataframe to update all prior entries
        """

        revised_dataframe = hive_dataframe.with_columns(
            pl.when(pl.col("hive ID").eq(self.ID)
                    ).then(ID
                           ).otherwise(pl.col("hive ID")).alias("hive ID")
        )

        self.ID = ID

        return revised_dataframe
    
    def change_position(self, position: int) -> None:
        """
        Given a new position, change the current position.
        """

        self.position = position
    

class box:
    """
    Pythonic representation of a box

    Attributes:
        hive [hive]: the hive that the box is within
        ID [str]: unique identifier of the box
        position [int]: position of the box in the vertical stack 1 is the bottom
        max_frames [int]: the max frames a box can hold, typically 8 or 10
        notes [DataFrame]: note dataframe relevant to this box

    
    """

    """
    Attributes:
    """
    def __init__(self,  ID: str, hive: Optional[hive] = None,
                  position: Optional[int] = None, max_frames: Optional[int] = None,
                    notes:Optional[pl.DataFrame] = None):

        self.hive = hive
        self.ID = ID
        self.position = position
        self.max_frames = max_frames
        self.notes = notes
    
    """
    Methods:
    """

    def save(self) -> pl.DataFrame:
        """
        Returns the box as a polars dataframe
        """

        return pl.DataFrame(
            {
                "hive ID": self.hive.ID,
                "box ID": self.ID,
                "position": self.position,
                "max frames": self.max_frames,
                "timestamp": datetime.now()

            },
            schema=
            {
                "hive ID": pl.String,
                "box ID": pl.String,
                "position": pl.Int64,
                "max frames": pl.Int64,
                "timestamp": pl.Datetime

            }
        )
    
    def load(self, box_dataframe: pl.DataFrame, hives: dict) -> None:
        """
        Given the overall box dataframe and the dictionary of hives, extract the latest parameters that match 
        the box ID
        """

        # select the latest box entry
        latest = box_dataframe.filter(pl.col("box ID").eq(self.ID)
                                       ).filter(
                                           pl.col("timestamp").eq(pl.col("timestamp").max())
                                       ).row(0, named=True)
        
        self.hive = hives[latest["hive ID"]]
        self.max_frames = latest["max frames"]
        self.position = latest["position"]

    def create_note(self, nature: str, note: str) -> pl.DataFrame:
        """
        Given a nature and note, return a dataframe that also includes the ID and level
        """

        return pl.DataFrame(
            {
                "ID": self.ID,
                "level": "box",
                "nature": nature,
                "note": note,
                "timestamp": datetime.now(nyc)
            },
            schema=
            {
                "ID": pl.String,
                "level":  pl.String,
                "nature": pl.String,
                "note":  pl.String,
                "timestamp": pl.Datetime

            }
        )
    
    def load_notes(self, notes: pl.DataFrame) -> None:
        """
        Given the overall notes dataframe, select the notes relevant to this box.
        """

        self.notes = notes.filter(pl.col("ID").eq(self.ID))

    def change_ID(self, ID: str, box_dataframe: pl.DataFrame) -> None:
        """
        Given a new ID, change the current ID.

        This requires the overall hive dataframe to update all prior entries
        """

        revised_dataframe = box_dataframe.with_columns(
            pl.when(pl.col("box ID").eq(self.ID)
                    ).then(ID
                           ).otherwise(pl.col("box ID")).alias("box ID")
        )

        self.ID = ID

        return revised_dataframe
    
    def change_position(self, position: int) -> None:
        """
        Given a new position, change the current position.
        """

        self.position = position


class frame:
    """
    Pythonic representation of a frame

    Attributes:
        box [box]: the box that the frame is within
        ID [str]: unique identifier of the frame
        position [int]: position of the box left to right from the perspective of person standing behind the hive, starts at 1
        measurements [DataFrame]: measurement dataframe relevant to this frame
        notes [DataFrame]: note dataframe relevant to this box

    
    """

    """
    Attributes:
    """
    def __init__(self,  ID: str, box: Optional[box] = None,
                  position: Optional[int] = None, measurements:Optional[pl.DataFrame] = None,
                    notes:Optional[pl.DataFrame] = None):

        self.box = box
        self.ID = ID
        self.position = position
        self.measurements = measurements
        self.notes = notes
    
    """
    Methods:
    """
    def save(self) -> pl.DataFrame:
        """
        Returns the frame as a polars dataframe
        """

        return pl.DataFrame(
            {
                "box ID": self.box.ID,
                "frame ID": self.ID,
                "position": self.position,
                "timestamp": datetime.now()

            },
            schema=
            {
                "box ID": pl.String,
                "frame ID": pl.String,
                "position": pl.Int64,
                "timestamp": pl.Datetime,

            }
        )
    
    def load(self, frame_dataframe: pl.DataFrame, boxes: dict) -> None:
        """
        Given the overall frame dataframe and the dictionary of boxes, extract the latest parameters that match 
        the frame ID
        """

        # select the latest box entry
        latest = frame_dataframe.filter(pl.col("frame ID").eq(self.ID)
                                       ).filter(
                                           pl.col("timestamp").eq(pl.col("timestamp").max())
                                       ).row(0, named=True)
        
        self.box = boxes[latest["box ID"]]
        self.position = latest["position"]

    def create_note(self, nature: str, note: str) -> pl.DataFrame:
        """
        Given a nature and note, return a dataframe that also includes the ID and level
        """

        return pl.DataFrame(
            {
                "ID": self.ID,
                "level": "frame",
                "nature": nature,
                "note": note,
                "timestamp": datetime.now(nyc)
            },
            schema=
            {
                "ID": pl.String,
                "level":  pl.String,
                "nature": pl.String,
                "note":  pl.String,
                "timestamp": pl.Datetime

            }
        )
    
    def load_notes(self, notes: pl.DataFrame) -> None:
        """
        Given the overall notes dataframe, select the notes relevant to this frame.
        """

        self.notes = notes.filter(pl.col("ID").eq(self.ID))

    def create_measurement(self, side:Literal["left", "right"], bees:int,
                           empty_cells:int, drone_cells:int,
                           capped_brood_cells:int, uncapped_brood_cells:int, 
                           capped_honey_cells:int, uncapped_honey_cells:int,
                           pollen_cells:int, queen_cells:int) -> pl.DataFrame:
        """
        Given the relative, 0-10 measurements from the user, where 0 is
        none at all and 10 is covering the entire frame, record a measurement
        of what the frame's cells is made of
        """

        return pl.DataFrame(
            {
                "ID": self.ID,
                "side": side,
                "bees": bees,
                "empty cells": empty_cells,
                "done cells": drone_cells,
                "capped brood cells": capped_brood_cells,
                "uncapped brood cells": uncapped_brood_cells,
                "capped honey cells": capped_honey_cells,
                "uncapped honey cells": uncapped_honey_cells,
                "pollen cells": pollen_cells,
                "queen cells": queen_cells,
                "timestamp": datetime.now(nyc)
            },
            schema=
            {
                "ID": pl.String,
                "side": pl.String,
                "bees": pl.Int64,
                "empty cells": pl.Int64,
                "done cells": pl.Int64,
                "capped brood cells": pl.Int64,
                "uncapped brood cells": pl.Int64,
                "capped honey cells": pl.Int64,
                "uncapped honey cells": pl.Int64,
                "pollen cells": pl.Int64,
                "queen cells": pl.Int64,
                "timestamp": pl.Datetime,

            }
        )
    
    def load_measurements(self, measurements: pl.DataFrame) -> None:
        """
        Given the overall measurements dataframe, select the measurements relevant to this frame.
        """

        self.measurements = measurements.filter(pl.col("ID").eq(self.ID))

    def change_ID(self, ID: str, frame_dataframe: pl.DataFrame) -> None:
        """
        Given a new ID, change the current ID.

        This requires the overall frame dataframe to update all prior entries
        """

        revised_dataframe = frame_dataframe.with_columns(
            pl.when(pl.col("frame ID").eq(self.ID)
                    ).then(ID
                           ).otherwise(pl.col("frame ID")).alias("frame ID")
        )

        self.ID = ID

        return revised_dataframe
    
    def change_position(self, position: int) -> None:
        """
        Given a new position, change the current position.
        """

        self.position = position



if __name__ == "__main__":
    pass

    # # make connection
    # blob = establish_connection(load_local_credential("blank.txt"))

    # # make a hive
    # test_hive = hive(
    #     "test hive",
    #     "test owner",
    #     False,
    #     1
    # )

    # hive_note = test_hive.create_note("upkeep", "created new hive to test functionality of software")

    # # make box
    # test_box = box(
    #     "test box",
    #     test_hive,
    #     1,
    #     8
    # )

    # box_note = test_box.create_note("upkeep", "created a new box to test functionality")

    # # make a test frame
    # test_frame = frame(
    #     "test frame",
    #     test_box,
    #     position=1
    # )

    # frame_note = test_frame.create_note("upkeep", "created a new frame to test functionality")

    # measurements = test_frame.create_measurement(
    #     "left",
    #     7,
    #     1,
    #     4,
    #     0,
    #     1,
    #     9,
    #     4,
    #     0,
    #     0
    # )

    # notes = pl.concat([hive_note, box_note, frame_note])

    # # upload the data

    # write_blob(blob, container, "hives.parquet", test_hive.save())
    # write_blob(blob, container, "boxes.parquet", test_box.save())
    # write_blob(blob, container, "frames.parquet", test_frame.save())
    # write_blob(blob, container, "measurements.parquet", measurements)
    # write_blob(blob, container, "notes.parquet", notes)

