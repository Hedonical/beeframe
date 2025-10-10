import polars as pl
from datetime import datetime
import pytz
import names
from typing import Optional

# get the timezone of nyc
nyc = pytz.timezone("America/New_York")

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


if __name__ == "__main__":
    # create a new hive

    # load the notes
    note_df = pl.read_parquet("note.parquet")

    # load the hives
    hive_df = pl.read_parquet("hive.parquet")

    test_hive = hive("test hive")

    test_hive.load(hive_df)

    print(test_hive.save())

    test_hive.load_notes(note_df)

    print(test_hive.notes)


    # test_hive = hive("test hive",
    #                  "cemetary",
    #                  False,
    #                  1)
    
    # test_hive.change_position(2)

    # test_hive.retire()


    # test_hive.create_note("queen", "queen bee spotted dancing on top of hive")
    
    # test_hive.save()
